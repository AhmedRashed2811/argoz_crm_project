from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.leads.models import LeadStage, LeadStageHistory
from apps.sla.models import SLADefinition, LeadSLAInstance
from apps.distribution.services.distribution import DistributionService
from apps.audit.services.audit import AuditService
from apps.notifications.services.notifications import NotificationService


# ---------------------------------------------------------------------------
# Stage behaviour constants (Doc 2 Section 3.1.1, table)
# ---------------------------------------------------------------------------
# Maps stage codes to how SLA expiry should be handled.
STAGE_EXPIRY_BEHAVIOUR = {
    'fresh':          {'distribution': 'automatic', 'reminder': True},
    'interested':     {'distribution': 'per_policy', 'reminder': True},
    'not_interested': {'distribution': 'none',      'reminder': False, 'deactivate': True},
    'follow_up':      {'distribution': 'manual',    'reminder': True},
    'followup':       {'distribution': 'manual',    'reminder': True},
    'meeting':        {'distribution': 'manual',    'reminder': True},
    'not_reached':    {'distribution': 'automatic', 'reminder': True},
    'frozen':         {'distribution': 'automatic', 'reminder': True, 'frozen_reactivation': True},
}


class SLAService:
    @staticmethod
    def _duration(definition: SLADefinition):
        if definition.duration_unit == 'minutes':
            return timedelta(minutes=definition.duration_value)
        if definition.duration_unit == 'days':
            return timedelta(days=definition.duration_value)
        return timedelta(hours=definition.duration_value)

    @classmethod
    def resolve_definition(cls, lead):
        from apps.sla.selectors import resolve_sla_definition
        return resolve_sla_definition(lead)

    @classmethod
    def start_for_lead(cls, lead, assignment=None):
        """Start a new SLA instance for the lead and create associated reminders."""
        definition = cls.resolve_definition(lead)
        if not definition or not lead.current_stage:
            return None
        starts_at = timezone.now()
        # A lead must have only one active SLA clock at a time.  New assignment
        # or stage SLA start cancels previous active clocks without deleting
        # their history.
        LeadSLAInstance.objects.filter(lead=lead, status='active').update(
            status='cancelled', processed_at=starts_at, updated_at=starts_at,
        )
        sla_duration = cls._duration(definition)
        due_at = starts_at + sla_duration
        instance = LeadSLAInstance.objects.create(
            lead=lead,
            assignment=assignment,
            stage=lead.current_stage,
            starts_at=starts_at,
            due_at=due_at,
            policy_snapshot={
                'definition_id': str(definition.id),
                'duration_value': definition.duration_value,
                'duration_unit': definition.duration_unit,
                'breach_action': definition.breach_action,
                'expiry_strategy_code': definition.expiry_strategy_code,
            },
        )
        # --- Create reminders per the reminder_config schedule ---
        cls._create_sla_reminders(lead, instance, definition, due_at)
        
        # Link this SLA instance to the active AssignmentAttempt
        from apps.distribution.models import AssignmentAttempt
        active_attempt = lead.assignment_attempts.filter(status='active').first()
        if active_attempt:
            # Preserve AssignmentAttempt.due_at when retry/team escalation created it
            # from retry_attempt_window.  The SLA due time and retry attempt due
            # time can be different policy concepts.
            active_attempt.sla_instance = instance
            active_attempt.save(update_fields=['sla_instance', 'updated_at'])
            
        return instance

    @classmethod
    def _create_sla_reminders(cls, lead, sla_instance, definition, due_at):
        """Create reminder records before SLA due time based on config."""
        config = definition.reminder_config or {}
        minutes_before_list = config.get('minutes_before', [60, 30])
        if not isinstance(minutes_before_list, (list, tuple)):
            minutes_before_list = [60, 30]

        recipient = lead.current_salesman
        if not recipient:
            return

        stage_code = lead.current_stage.code if lead.current_stage else 'unknown'
        stage_behaviour = STAGE_EXPIRY_BEHAVIOUR.get(stage_code, {})

        if not stage_behaviour.get('reminder', True):
            return

        for minutes in minutes_before_list:
            reminder_at = due_at - timedelta(minutes=int(minutes))
            if reminder_at <= timezone.now():
                continue
            reminder_type = 'sla_warning'
            if stage_code == 'follow_up':
                reminder_type = 'followup_reminder'
            elif stage_code == 'meeting':
                reminder_type = 'meeting_reminder'
            elif stage_code == 'frozen':
                reminder_type = 'frozen_reactivation'

            NotificationService.create_reminder(
                company=lead.company,
                recipient=recipient,
                title=f'SLA reminder: {lead.full_name}',
                message=f'Lead {lead.full_name} SLA expires in {minutes} minutes (stage: {stage_code}).',
                due_at=reminder_at,
                reminder_type=reminder_type,
                lead=lead,
            )

    @classmethod
    def close_sla(cls, sla_instance, *, reason='satisfied'):
        """Explicitly close/satisfy an active SLA (e.g. salesman took action within time)."""
        if sla_instance.status != 'active':
            return sla_instance
        now = timezone.now()
        sla_instance.status = 'satisfied'
        sla_instance.processed_at = now
        sla_instance.save(update_fields=['status', 'processed_at', 'updated_at'])
        AuditService.log(
            company=sla_instance.lead.company,
            actor_type='system',
            action='sla.satisfied',
            obj=sla_instance.lead,
            metadata={'sla_id': str(sla_instance.id), 'reason': reason},
        )
        return sla_instance

    @classmethod
    def reset_for_rotation(cls, lead, *, assignment=None, actor=None, reason='SLA rotation reset'):
        """Cancel active SLAs, reset visible stage to Fresh, preserve history, and start Fresh SLA."""
        cls.cancel_active_slas(lead, reason='rotation_reset')
        fresh_stage = (
            LeadStage.objects.filter(company=lead.company, code='fresh').first()
            or LeadStage.objects.filter(company__isnull=True, code='fresh').first()
        )
        old_stage = lead.current_stage
        if fresh_stage and old_stage != fresh_stage:
            lead.current_stage = fresh_stage
            lead.status = 'active'
            lead.save(update_fields=['current_stage', 'status', 'updated_at'])
            LeadStageHistory.objects.create(
                lead=lead, from_stage=old_stage, to_stage=fresh_stage,
                changed_by=actor, reason=reason, metadata={'system_action': 'rotation_reset'},
            )
            AuditService.log(
                company=lead.company, actor=actor, actor_type='system' if actor is None else 'user',
                action='lead.stage_reset_fresh', obj=lead,
                before={'stage': getattr(old_stage, 'code', None)}, after={'stage': fresh_stage.code},
                metadata={'reason': reason},
            )
        return cls.start_for_lead(lead, assignment=assignment)

    @classmethod
    def cancel_active_slas(cls, lead, *, reason='cancelled'):
        """Cancel all active SLA instances for a lead."""
        now = timezone.now()
        updated = LeadSLAInstance.objects.filter(lead=lead, status='active').update(
            status='cancelled', processed_at=now, updated_at=now,
        )
        if updated:
            AuditService.log(
                company=lead.company, actor_type='system',
                action='sla.cancelled', obj=lead,
                metadata={'cancelled_count': updated, 'reason': reason},
            )
        return updated

    @classmethod
    def process_expired_slas(cls, limit=100):
        now = timezone.now()
        count = 0
        from apps.sla.selectors import get_expired_sla_instance_ids, get_sla_instance_for_update
        ids = get_expired_sla_instance_ids(limit, now)
        for sla_id in ids:
            with transaction.atomic():
                sla = get_sla_instance_for_update(sla_id)
                if sla.status != 'active' or sla.due_at > timezone.now():
                    continue
                cls.process_single_expired_sla(sla)
                count += 1
        return count

    @classmethod
    def process_single_expired_sla(cls, sla):
        now = timezone.now()
        lead = sla.lead
        sla.status = 'expired'
        sla.expired_at = now
        sla.save(update_fields=['status', 'expired_at', 'updated_at'])

        # Mark active attempt as expired/ended
        from apps.distribution.models import AssignmentAttempt
        active_attempt = lead.assignment_attempts.filter(status='active').first()
        if active_attempt:
            active_attempt.status = 'expired'
            active_attempt.ended_at = now
            active_attempt.save(update_fields=['status', 'ended_at'])

        strategy_code = sla.policy_snapshot.get('expiry_strategy_code') or 'round_robin_load_balanced'
        breach_action = sla.policy_snapshot.get('breach_action') or 'automatic_redistribution'

        # Broker leads always get manual reassignment
        if lead.origin == 'broker' and breach_action == 'automatic_redistribution':
            breach_action = 'manual_reassignment'

        # --- Stage-specific SLA expiry behaviour ---
        stage_code = lead.current_stage.code if lead.current_stage else 'fresh'
        behaviour = STAGE_EXPIRY_BEHAVIOUR.get(stage_code, {'distribution': 'automatic', 'reminder': True})

        # Terminal / deactivation stages → mark inactive, no redistribution
        if behaviour.get('deactivate'):
            lead.status = 'inactive'
            lead.save(update_fields=['status', 'updated_at'])
            sla.status = 'processed'
            sla.processed_at = timezone.now()
            sla.save(update_fields=['status', 'processed_at', 'updated_at'])
            AuditService.log(company=lead.company, actor_type='system', action='sla.expired.deactivated', obj=lead, metadata={'sla_id': str(sla.id), 'stage': stage_code})
            return None

        # Manual-only stages (Follow-up, Meeting) → notify, don't auto-redistribute
        if behaviour.get('distribution') == 'manual':
            breach_action = 'manual_reassignment'

        # Frozen → send frozen reactivation reminder
        if behaviour.get('frozen_reactivation') and lead.current_salesman:
            NotificationService.notify(
                company=lead.company,
                recipient=lead.current_salesman,
                type_code='frozen_reactivation',
                title='Frozen period ended',
                message=f'Lead {lead.full_name} freeze period has ended. Please re-engage.',
                related_object=lead,
                channels=['in_app'],
            )

        if breach_action == 'automatic_redistribution':
            result = DistributionService.assign(lead=lead, actor=None, strategy_code=strategy_code)
            latest_assignment = lead.assignments.filter(is_current=True).first()
            # Universal document rule: after any SLA-triggered rotation the
            # visible stage resets to Fresh, Fresh SLA restarts, and history is
            # preserved.
            cls.reset_for_rotation(lead, assignment=latest_assignment, reason='SLA expired redistribution')
            action = 'sla.expired.redistributed'
        else:
            result = None
            # Notify salesman and/or sales head for manual reassignment
            recipients = []
            if lead.current_salesman:
                recipients.append(lead.current_salesman)
            if lead.current_team and lead.current_team.sales_head and lead.current_team.sales_head != lead.current_salesman:
                recipients.append(lead.current_team.sales_head)
            for recipient in recipients:
                NotificationService.notify(
                    company=lead.company,
                    recipient=recipient,
                    type_code='sla_expired_manual_required',
                    title='SLA expired – manual reassignment required',
                    message=f'Lead {lead.full_name} exceeded SLA (stage: {stage_code}) and needs manual reassignment.',
                    related_object=lead,
                    channels=['in_app', 'email'],
                )
            action = 'sla.expired.manual_required'

        sla.status = 'processed'
        sla.processed_at = timezone.now()
        sla.save(update_fields=['status', 'processed_at', 'updated_at'])
        AuditService.log(
            company=lead.company, actor_type='system', action=action,
            obj=lead, metadata={'sla_id': str(sla.id), 'strategy_code': strategy_code, 'stage': stage_code},
        )
        return result
