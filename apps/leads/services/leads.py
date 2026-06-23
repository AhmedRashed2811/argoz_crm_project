from apps.sla.models import LeadSLAInstance
import re
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from apps.leads.models import Lead, LeadAssignment, LeadStageHistory, LeadReactivation, LeadFollowUp, Meeting
from apps.marketing.models import LeadCampaignAttribution
from apps.distribution.services.distribution import DistributionService
from apps.sla.services.sla import SLAService
from apps.audit.services.audit import AuditService
from apps.notifications.services.notifications import NotificationService
from apps.core.services.policies import PolicyResolver

def update_salesman_cache(salesman):
    if salesman and hasattr(salesman, 'sales_profile'):
        profile = salesman.sales_profile
        profile.active_lead_count_cache = salesman.current_leads.filter(status='active').count()
        profile.save(update_fields=['active_lead_count_cache', 'updated_at'])


def normalize_phone(country_code, number):
    cc = re.sub(r'\D+', '', str(country_code or ''))
    num = re.sub(r'\D+', '', str(number or ''))
    if num.startswith(cc) and cc:
        return num
    return f'{cc}{num}'


def normalize_source_code(source_code: str) -> str:
    return (source_code or '').strip().lower().replace('-', '_').replace(' ', '_')


class LeadService:
    @staticmethod
    def create_lead(*, company, full_name, phone_country_code, phone_number, source, origin='direct', actor=None, **kwargs):
        with transaction.atomic():
            lead, created = Lead.objects.get_or_create(
                company=company,
                normalized_phone=normalize_phone(phone_country_code, phone_number),
                defaults={
                    'full_name': full_name,
                    'phone_country_code': phone_country_code,
                    'phone_number': phone_number,
                    'source': source,
                    'origin': origin,
                    **kwargs,
                },
            )
            if not created:
                lead.metadata = {**lead.metadata, 'last_duplicate_attempt': kwargs.get('metadata', {})}
                lead.save(update_fields=['metadata', 'updated_at'])
                AuditService.log(company=company, actor=actor, action='lead.duplicate_detected', obj=lead)
                
                if lead.status == Lead.STATUS_INACTIVE:
                    # Reactivate inactive leads (triggers automatic/manual redistribution)
                    LeadService.reactivate(lead=lead, actor=actor, reason='Reactivated via duplicate lead intake submission')
                    return lead, True
                else:
                    # Active lead within SLA: escalate via "Call Me Again" workflow
                    LeadService.handle_call_me_again(lead=lead, actor=actor)
                    return lead, False
            AuditService.log(company=company, actor=actor, action='lead.created', obj=lead, after={'source': source.code, 'origin': origin})

            # --- Create campaign attribution if campaign is linked ---
            campaign = kwargs.get('campaign')
            if campaign:
                LeadService._create_attribution(lead, campaign, kwargs.get('metadata', {}))

            return lead, True

    @staticmethod
    def create_lead_from_source(*, company, full_name, phone_country_code='+20', phone_number='', source,
                                origin=None, actor=None, metadata=None, team=None, salesman=None, **kwargs):
        """Create a lead and immediately apply the document's source-specific backend workflow.

        This keeps lead creation, duplicate handling, attribution, assignment, and SLA start
        in one transaction-safe service entry point for web views, imports, and integrations.
        """
        metadata = metadata or {}
        source_code = normalize_source_code(getattr(source, 'code', metadata.get('source_code', '')))
        if origin is None:
            origin = Lead.ORIGIN_BROKER if source_code == 'broker' else Lead.ORIGIN_DIRECT

        # Resolve broker from actor or metadata
        broker = None
        from apps.accounts.models import BrokerProfile, User
        if actor and hasattr(actor, 'broker_profile') and actor.broker_profile.is_active and actor.broker_profile.company == company:
            broker = actor.broker_profile
        else:
            broker_ref = metadata.get('broker') or kwargs.get('broker')
            if broker_ref:
                if isinstance(broker_ref, BrokerProfile):
                    broker = broker_ref
                elif isinstance(broker_ref, User):
                    broker = BrokerProfile.objects.filter(user=broker_ref, company=company, is_active=True).first()
                elif isinstance(broker_ref, str):
                    broker = BrokerProfile.objects.filter(pk=broker_ref, company=company, is_active=True).first()
                    if not broker:
                        broker = BrokerProfile.objects.filter(user_id=broker_ref, company=company, is_active=True).first()
        if broker:
            kwargs['broker'] = broker

        # If team or salesman is passed inside metadata, pop and resolve them
        if not team:
            team = metadata.pop('team', None)
        else:
            metadata.pop('team', None)

        if not salesman:
            salesman = metadata.pop('salesman', None)
        else:
            metadata.pop('salesman', None)

        from apps.accounts.models import User, Team
        if isinstance(team, str):
            team = Team.objects.filter(pk=team).first()
        if isinstance(salesman, str):
            salesman = User.objects.filter(pk=salesman).first()

        # Minimal backend validations from the functional document.
        if getattr(source, 'requires_how_did_you_know', False) and not (kwargs.get('how_did_you_know') or metadata.get('how_did_you_know')):
            raise ValueError('This lead source requires a "How did you know us" value. The Website option must be available in master data.')
        if source_code == 'exhibition' and not salesman:
            raise ValueError('Exhibition leads must be manually assigned to a salesman and cannot remain unassigned.')
        if source_code == 'referral' and not metadata.get('referrer_name'):
            raise ValueError('Referral leads must capture the referrer name as free text.')
        if source_code == 'campaign' and not (kwargs.get('campaign') or metadata.get('campaign')):
            raise ValueError('Campaign leads must be attributed to a campaign.')
        if source_code == 'walkin' and metadata.get('how_did_you_know_name') == '' and not kwargs.get('how_did_you_know'):
            raise ValueError('Walk-in leads must capture how the visitor knew the company.')
        if source_code == 'call_center' and not (metadata.get('caller_source') or metadata.get('how_did_you_know') or kwargs.get('how_did_you_know')):
            raise ValueError('Call Center leads must capture caller source information.')

        if metadata.get('campaign') and not kwargs.get('campaign'):
            kwargs['campaign'] = metadata['campaign']
        if metadata.get('how_did_you_know') and not kwargs.get('how_did_you_know'):
            kwargs['how_did_you_know'] = metadata['how_did_you_know']

        # Store source-specific metadata on the lead for audit/reporting.
        existing_meta = kwargs.pop('metadata', {}) or {}
        merged_metadata = {**existing_meta, **metadata, 'source_workflow': source_code}

        lead, created = LeadService.create_lead(
            company=company,
            full_name=full_name,
            phone_country_code=phone_country_code,
            phone_number=phone_number,
            source=source,
            origin=origin,
            actor=actor,
            metadata=merged_metadata,
            **kwargs,
        )
        if created:
            LeadService.assign_lead_by_source(lead=lead, actor=actor, source_code=source_code, metadata=merged_metadata, team=team, salesman=salesman)
        return lead, created

    @staticmethod
    def _create_attribution(lead, campaign, metadata):
        """Create a LeadCampaignAttribution record linking a lead to its campaign and child type."""
        campaign_child_type = metadata.get('campaign_child_type', '') if isinstance(metadata, dict) else ''
        campaign_child_id = metadata.get('campaign_child_id', '') if isinstance(metadata, dict) else ''
        platform = metadata.get('platform', '') if isinstance(metadata, dict) else ''
        tracking_method = 'manual'
        if metadata.get('webhook_payload_id'):
            tracking_method = 'webhook'

        LeadCampaignAttribution.objects.create(
            lead=lead,
            campaign=campaign,
            campaign_type=campaign_child_type or '',
            child_object_id=campaign_child_id or None,
            platform=platform or '',
            tracking_method=tracking_method,
        )

    @staticmethod
    def assign_lead(*, lead, actor=None, strategy_code=None, team=None, salesman=None):
        result = DistributionService.assign(lead=lead, actor=actor, strategy_code=strategy_code, team=team, salesman=salesman)
        assignment = lead.assignments.filter(is_current=True).first()
        SLAService.start_for_lead(lead, assignment=assignment)
        if result.salesman:
            NotificationService.notify(
                company=lead.company,
                recipient=result.salesman,
                type_code='lead_assigned',
                title='New lead assigned',
                message=f'Lead {lead.full_name} was assigned to you.',
                related_object=lead,
            )
        return result

    @staticmethod
    def assign_lead_by_source(*, lead, actor, source_code, metadata=None, team=None, salesman=None):
        """Source-aware assignment that applies all business rules from Doc 2 Section 4.2."""
        metadata = metadata or {}
        source_code = normalize_source_code(source_code)
        company = lead.company

        # --- a) Self-Generated ---
        if source_code == 'self_generated':
            return LeadService._assign_self_generated(lead=lead, actor=actor, metadata=metadata, team=team, salesman=salesman)

        # --- b) Campaign ---
        if source_code == 'campaign':
            if not (lead.campaign_id or metadata.get('campaign')):
                raise ValueError('Campaign leads must store campaign attribution.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'campaign')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=team, salesman=salesman)
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- c) Broker ---
        if source_code == 'broker':
            return LeadService._assign_broker(lead=lead, actor=actor, metadata=metadata, team=team, salesman=salesman)

        # --- d) Walk-in ---
        if source_code == 'walkin':
            return LeadService._assign_walkin(lead=lead, actor=actor, metadata=metadata, team=team, salesman=salesman)

        # --- e) Call Center ---
        if source_code == 'call_center':
            if not (metadata.get('caller_source') or metadata.get('how_did_you_know') or lead.how_did_you_know_id):
                raise ValueError('Call Center leads must capture caller_source or how_did_you_know.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'call_center')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=team, salesman=salesman)
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- f) Exhibition ---
        if source_code == 'exhibition':
            if not salesman:
                raise ValueError('Exhibition leads must be assigned to a salesman.')
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                           salesman=salesman, team=team)

        # --- g) Referral ---
        if source_code == 'referral':
            if not metadata.get('referrer_name'):
                raise ValueError('Referral leads must capture referrer_name.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'referral')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=team, salesman=salesman)
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- h) Existing Client ---
        if source_code == 'existing_client':
            return LeadService._assign_existing_client(lead=lead, actor=actor, metadata=metadata)

        # Fallback: generic automatic distribution
        return LeadService.assign_lead(lead=lead, actor=actor)

    @staticmethod
    def _assign_self_generated(*, lead, actor, metadata, team=None, salesman=None):
        """Self-generated business rules from Doc 2 Section 4.2a."""
        from apps.accounts.models import TeamMembership

        mode = metadata.get('self_owner_mode') or PolicyResolver.get_self_generated_mode(lead.company)

        # Check if actor is a Sales Head
        is_sales_head = TeamMembership.objects.filter(
            user=actor, role=TeamMembership.ROLE_SALES_HEAD, is_active=True, team__company=lead.company,
        ).exists()

        if is_sales_head:
            # Sales Head: may assign to himself, a team member, or run team-level Round Robin
            if not salesman:
                salesman = metadata.get('salesman')
            if not team:
                team = metadata.get('team')
            if salesman:
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               salesman=salesman, team=team)
            if team:
                return LeadService.assign_lead(lead=lead, actor=actor, team=team)
            # Default: assign to self
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment', salesman=actor)
        else:
            # Salesman: auto-assigned to self
            result = LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment', salesman=actor)
            # If policy is sla_redistribute, the SLA will handle redistribution on expiry
            # (no extra action needed here; SLA expiry processing handles it)
            return result

    @staticmethod
    def _assign_broker(*, lead, actor, metadata, team=None, salesman=None):
        """Broker business rules from Doc 2 Section 4.2c."""
        from apps.accounts.models import BrokerProfile, SalesProfile, User

        broker_mode = metadata.get('broker_assign_mode') or PolicyResolver.get_broker_assign_mode(lead.company)

        # 1. Resolve and set broker on the lead:
        actor_broker_profile = BrokerProfile.objects.filter(user=actor, company=lead.company, is_active=True).first()
        broker = None
        if actor_broker_profile:
            broker = actor_broker_profile
        else:
            broker_ref = metadata.get('broker')
            if broker_ref:
                if isinstance(broker_ref, BrokerProfile):
                    broker = broker_ref
                elif isinstance(broker_ref, User):
                    broker = BrokerProfile.objects.filter(user=broker_ref, company=lead.company, is_active=True).first()
                elif isinstance(broker_ref, str):
                    broker = BrokerProfile.objects.filter(pk=broker_ref, company=lead.company, is_active=True).first()
                    if not broker:
                        broker = BrokerProfile.objects.filter(user_id=broker_ref, company=lead.company, is_active=True).first()
        if broker:
            lead.broker = broker
            lead.save(update_fields=['broker', 'updated_at'])

        # Log broker_owner_assigned audit
        AuditService.log(company=lead.company, actor=actor, action='lead.broker_owner_assigned', obj=lead)

        # 2. Check if the broker user (associated with lead.broker or actor) has an active SalesProfile
        broker_user = lead.broker.user if lead.broker else (actor if actor_broker_profile else None)

        has_sales_profile = False
        if broker_user:
            has_sales_profile = SalesProfile.objects.filter(user=broker_user, company=lead.company, is_available=True).exists()

        if not salesman:
            salesman = metadata.get('salesman')
        if isinstance(salesman, str):
            salesman = User.objects.filter(pk=salesman).first()

        if salesman:
            # We are assigning to an explicit company salesman
            result = LeadService.assign_lead(lead=lead, actor=None, strategy_code='manual_assignment',
                                           salesman=salesman, team=team or metadata.get('team'))
            AuditService.log(company=lead.company, actor=actor, action='lead.broker_to_sales_assigned', obj=lead)
            return result

        if broker_mode == 'assign_salesman':
            # Run auto-distribution
            result = LeadService.assign_lead(lead=lead, actor=None)
            AuditService.log(company=lead.company, actor=actor, action='lead.broker_to_sales_assigned', obj=lead)
            return result

        # If broker user has a SalesProfile, assign them as salesman
        if has_sales_profile and broker_user:
            result = LeadService.assign_lead(lead=lead, actor=None, strategy_code='manual_assignment', salesman=broker_user)
            return result

        # Otherwise, remain with broker only - just mark as assigned, salesman=None
        result = LeadService.assign_lead(lead=lead, actor=None, strategy_code='manual_assignment', salesman=None)
        return result

    @staticmethod
    def _assign_walkin(*, lead, actor, metadata, team=None, salesman=None):
        """Walk-in reception policy from Doc 2 Section 4.2d (3 policies)."""
        policy = PolicyResolver.get_walkin_policy(lead.company)

        strategy_map = {
            'open_floor': 'walkin_open_floor',
            'team_turn': 'walkin_team_turn',
            'full_rotation': 'walkin_full_rotation',
        }
        strategy_code = strategy_map.get(policy, 'walkin_open_floor')
        return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy_code,
                                       team=team, salesman=salesman)

    @staticmethod
    def _assign_existing_client(*, lead, actor, metadata):
        """Existing client business rules from Doc 2 Section 4.2h."""
        from apps.accounts.models import User

        mode = PolicyResolver.get_existing_client_mode(lead.company)
        existing_phone = metadata.get('existing_client_phone', '')

        if mode in ('retain', 'preserve_original_salesman') and existing_phone:
            # Look up previous salesman for this phone number
            from apps.leads.selectors import get_duplicate_lead_for_existing_client
            previous_lead = get_duplicate_lead_for_existing_client(lead.company, existing_phone, exclude_lead_id=lead.pk)
            if previous_lead and previous_lead.current_salesman:
                previous_salesman = previous_lead.current_salesman
                if previous_salesman.is_active:
                    # Re-assign to the original salesman
                    return LeadService.assign_lead(
                        lead=lead, actor=actor, strategy_code='manual_assignment',
                        salesman=previous_salesman,
                    )
                # Previous salesman no longer active → redistribute
        # Redistribute per policy
        return LeadService.assign_lead(lead=lead, actor=actor)

    @staticmethod
    def handle_call_me_again(*, lead, actor=None):
        """Handle 'call me again' request within SLA — creates manual distribution request."""
        # 1. Close existing SLA if active
        active_sla = LeadSLAInstance.objects.filter(lead=lead, status='active').first()
        if active_sla:
            SLAService.close_sla(active_sla, reason='call_me_again_escalation')

        # 2. Create the ManualDistributionRequest
        from apps.distribution.models import ManualDistributionRequest
        from apps.accounts.models import User
        from apps.permissions_engine.services.engine import PermissionEngine

        req = ManualDistributionRequest.objects.create(
            company=lead.company,
            lead=lead,
            original_salesman=lead.current_salesman,
            original_team=lead.current_team,
            status='pending',
            reason='Lead re-engaged / call me again requested while active within SLA.'
        )

        # 3. Log Audit
        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.call_me_again_escalation',
            obj=lead,
            metadata={'request_id': str(req.id)}
        )

        # 4. Notify authorized users
        auth_users = User.objects.filter(company=lead.company, is_active=True)
        for u in auth_users:
            if PermissionEngine.has_perm(u, 'distribution.run_manual_distribution') or PermissionEngine.has_perm(u, 'leads.assign_lead_manual'):
                NotificationService.notify(
                    company=lead.company,
                    recipient=u,
                    type_code='generic',
                    title='Lead Call Me Again Escalation',
                    message=f'Lead {lead.full_name} has requested "Call Me Again" and is escalated for manual distribution.',
                    related_object=lead,
                )
        return req

    @staticmethod
    def change_stage(*, lead, new_stage, actor=None, reason='', **kwargs):
        old_stage = lead.current_stage
        
        # 1. Validations
        if new_stage.code in ('follow_up', 'followup'):
            due_at = kwargs.get('due_at') or lead.metadata.get('followup_due_at')
            if not due_at and not lead.followups.filter(status='pending').exists():
                raise ValueError("Follow-up stage requires a scheduled due date and time.")
        
        if new_stage.code == 'meeting':
            scheduled_at = kwargs.get('scheduled_at') or lead.metadata.get('meeting_scheduled_at')
            if not scheduled_at and not lead.meetings.filter(status='scheduled').exists():
                raise ValueError("Meeting stage requires a scheduled meeting date and time.")
                
        if new_stage.code == 'frozen':
            freeze_end = kwargs.get('freeze_end') or lead.metadata.get('freeze_end')
            if not freeze_end:
                raise ValueError("Frozen stage requires a freeze end date.")

        # 2. Update stage and status
        lead.current_stage = new_stage
        if new_stage.is_terminal:
            lead.status = Lead.STATUS_INACTIVE
        lead.save(update_fields=['current_stage', 'status', 'updated_at'])
        
        # Mark active assignment attempts as successful (contacted)
        lead.assignment_attempts.filter(status='active').update(
            status='successful', ended_at=timezone.now()
        )
        
        LeadStageHistory.objects.create(lead=lead, from_stage=old_stage, to_stage=new_stage, changed_by=actor, reason=reason)
        AuditService.log(company=lead.company, actor=actor, action='lead.stage_changed', obj=lead, before={'stage': getattr(old_stage, 'code', None)}, after={'stage': new_stage.code})

        # 3. Create follow-up / meeting / frozen records if passed
        if new_stage.code in ('follow_up', 'followup') and kwargs.get('due_at'):
            from apps.leads.models import LeadFollowUp
            lead.followups.filter(status='pending').update(status='cancelled')
            LeadFollowUp.objects.create(
                lead=lead,
                assigned_to=lead.current_salesman or actor,
                due_at=kwargs.get('due_at'),
                status='pending',
                notes=reason
            )
            
        if new_stage.code == 'meeting' and kwargs.get('scheduled_at'):
            from apps.leads.models import Meeting
            lead.meetings.filter(status='scheduled').update(status='cancelled')
            Meeting.objects.create(
                lead=lead,
                assigned_to=lead.current_salesman or actor,
                scheduled_at=kwargs.get('scheduled_at'),
                location=kwargs.get('location', ''),
                meeting_type=kwargs.get('meeting_type', 'office'),
                status='scheduled',
                notes=reason
            )
            
        if new_stage.code == 'frozen' and kwargs.get('freeze_end'):
            lead.metadata['freeze_end'] = str(kwargs.get('freeze_end'))
            lead.save(update_fields=['metadata'])
            if lead.current_salesman:
                NotificationService.create_reminder(
                    company=lead.company,
                    recipient=lead.current_salesman,
                    title=f"Frozen lead reactivation: {lead.full_name}",
                    message=f"Lead {lead.full_name} freeze period has ended.",
                    due_at=kwargs.get('freeze_end'),
                    reminder_type='frozen_reactivation',
                    lead=lead
                )

        # 4. Handle Not Reached automatic reminder mode
        if new_stage.code in ('not_reached', 'no_answer'):
            mode = PolicyResolver.get_code(lead.company, 'reminder_mode_not_reached', 'automatic')
            if mode == 'automatic' and lead.current_salesman:
                due_at = timezone.now() + timedelta(hours=2)
                from apps.leads.models import LeadFollowUp
                LeadFollowUp.objects.create(
                    lead=lead,
                    assigned_to=lead.current_salesman,
                    due_at=due_at,
                    status='pending',
                    notes="Automatic follow-up scheduled for Not Reached stage."
                )
                NotificationService.create_reminder(
                    company=lead.company,
                    recipient=lead.current_salesman,
                    title=f"Call again: {lead.full_name}",
                    message=f"Lead {lead.full_name} was not reached. Please call again.",
                    due_at=due_at,
                    reminder_type='followup_reminder',
                    lead=lead
                )

        # Close active SLA when stage changes (salesman took action)
        from apps.sla.models import LeadSLAInstance
        active_sla = LeadSLAInstance.objects.filter(lead=lead, status='active').first()
        if active_sla:
            SLAService.close_sla(active_sla, reason=f'stage_changed_to_{new_stage.code}')

        # If new stage has its own SLA, start it
        if not new_stage.is_terminal:
            assignment = lead.assignments.filter(is_current=True).first()
            SLAService.start_for_lead(lead, assignment=assignment)

        # Update cache count for the salesman
        if lead.current_salesman:
            update_salesman_cache(lead.current_salesman)

        return lead

    @staticmethod
    def reactivate(*, lead, actor=None, reason=''):
        previous = lead.status
        lead.status = Lead.STATUS_ACTIVE
        lead.save(update_fields=['status', 'updated_at'])
        LeadReactivation.objects.create(lead=lead, reactivated_by=actor, reason=reason, previous_status=previous)
        AuditService.log(company=lead.company, actor=actor, action='lead.reactivated', obj=lead, before={'status': previous}, after={'status': lead.status})
        
        # Update cache count for the salesman
        if lead.current_salesman:
            update_salesman_cache(lead.current_salesman)
            
        # Redistribute reactivated lead per policy
        LeadService.assign_lead(lead=lead, actor=actor)
        NotificationService.notify(
            company=lead.company,
            recipient=lead.current_salesman,
            type_code='lead_reactivated',
            title='Lead reactivated',
            message=f'Lead {lead.full_name} has been reactivated and assigned to you.',
            related_object=lead,
        ) if lead.current_salesman else None
        return lead


class FollowUpService:
    @staticmethod
    def schedule_followup(*, lead, actor, due_at, reminder_at=None, notes='', assigned_to=None):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_followup'):
            raise PermissionError("Actor does not have permission to schedule a follow-up.")

        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        if not due_at:
            raise ValueError("Follow-up due_at is required.")

        followup = LeadFollowUp.objects.create(
            lead=lead,
            assigned_to=assigned_to or actor,
            due_at=due_at,
            reminder_at=reminder_at,
            notes=notes,
            status='pending',
        )

        if followup.reminder_at and followup.reminder_at > timezone.now():
            NotificationService.create_reminder(
                company=lead.company,
                recipient=followup.assigned_to,
                title=f"Follow-up reminder: {lead.full_name}",
                message=f"Scheduled follow-up for {lead.full_name} is due at {followup.due_at}.",
                due_at=followup.reminder_at,
                reminder_type='followup_warning',
                lead=lead,
            )

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.followup_scheduled',
            obj=lead,
            metadata={'followup_id': str(followup.id), 'due_at': str(due_at)}
        )
        return followup

    @staticmethod
    def update_followup(*, followup, actor, due_at=None, reminder_at=None, notes=None, assigned_to=None, status=None):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_followup'):
            raise PermissionError("Actor does not have permission to update a follow-up.")

        lead = followup.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        old_reminder = followup.reminder_at

        if due_at is not None:
            followup.due_at = due_at
        if reminder_at is not None:
            followup.reminder_at = reminder_at
        if notes is not None:
            followup.notes = notes
        if assigned_to is not None:
            followup.assigned_to = assigned_to
        if status is not None:
            followup.status = status

        followup.save()

        if reminder_at and reminder_at != old_reminder and reminder_at > timezone.now():
            NotificationService.create_reminder(
                company=lead.company,
                recipient=followup.assigned_to,
                title=f"Follow-up reminder: {lead.full_name}",
                message=f"Scheduled follow-up for {lead.full_name} is due at {followup.due_at}.",
                due_at=reminder_at,
                reminder_type='followup_warning',
                lead=lead,
            )

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.followup_updated',
            obj=lead,
            metadata={'followup_id': str(followup.id), 'status': followup.status}
        )
        return followup

    @staticmethod
    def complete_followup(*, followup, actor, notes=''):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_followup'):
            raise PermissionError("Actor does not have permission to complete a follow-up.")

        lead = followup.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        followup.status = 'done'
        if notes:
            followup.notes = notes
        followup.save()

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.followup_completed',
            obj=lead,
            metadata={'followup_id': str(followup.id)}
        )
        return followup

    @staticmethod
    def cancel_followup(*, followup, actor):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_followup'):
            raise PermissionError("Actor does not have permission to cancel a follow-up.")

        lead = followup.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        followup.status = 'cancelled'
        followup.save()

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.followup_cancelled',
            obj=lead,
            metadata={'followup_id': str(followup.id)}
        )
        return followup


class MeetingService:
    @staticmethod
    def schedule_meeting(*, lead, actor, scheduled_at, location='', meeting_type='office', notes='', assigned_to=None):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_meeting'):
            raise PermissionError("Actor does not have permission to schedule a meeting.")

        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        if not scheduled_at:
            raise ValueError("Meeting scheduled_at is required.")

        meeting = Meeting.objects.create(
            lead=lead,
            assigned_to=assigned_to or actor,
            scheduled_at=scheduled_at,
            location=location,
            meeting_type=meeting_type,
            notes=notes,
            status='scheduled',
        )

        reminder_time = meeting.scheduled_at - timedelta(hours=1)
        if reminder_time > timezone.now():
            NotificationService.create_reminder(
                company=lead.company,
                recipient=meeting.assigned_to,
                title=f"Meeting reminder: {lead.full_name}",
                message=f"Scheduled meeting ({meeting.meeting_type}) with {lead.full_name} is at {meeting.scheduled_at}.",
                due_at=reminder_time,
                reminder_type='meeting_warning',
                lead=lead,
            )

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.meeting_scheduled',
            obj=lead,
            metadata={'meeting_id': str(meeting.id), 'scheduled_at': str(scheduled_at)}
        )
        return meeting

    @staticmethod
    def update_meeting(*, meeting, actor, scheduled_at=None, location=None, meeting_type=None, notes=None, assigned_to=None, status=None):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_meeting'):
            raise PermissionError("Actor does not have permission to update a meeting.")

        lead = meeting.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        old_scheduled_at = meeting.scheduled_at

        if scheduled_at is not None:
            meeting.scheduled_at = scheduled_at
        if location is not None:
            meeting.location = location
        if meeting_type is not None:
            meeting.meeting_type = meeting_type
        if notes is not None:
            meeting.notes = notes
        if assigned_to is not None:
            meeting.assigned_to = assigned_to
        if status is not None:
            meeting.status = status

        meeting.save()

        if scheduled_at and scheduled_at != old_scheduled_at:
            reminder_time = scheduled_at - timedelta(hours=1)
            if reminder_time > timezone.now():
                NotificationService.create_reminder(
                    company=lead.company,
                    recipient=meeting.assigned_to,
                    title=f"Meeting reminder: {lead.full_name}",
                    message=f"Scheduled meeting ({meeting.meeting_type}) with {lead.full_name} is at {meeting.scheduled_at}.",
                    due_at=reminder_time,
                    reminder_type='meeting_warning',
                    lead=lead,
                )

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.meeting_updated',
            obj=lead,
            metadata={'meeting_id': str(meeting.id), 'status': meeting.status}
        )
        return meeting

    @staticmethod
    def complete_meeting(*, meeting, actor, notes=''):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_meeting'):
            raise PermissionError("Actor does not have permission to complete a meeting.")

        lead = meeting.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        meeting.status = 'done'
        if notes:
            meeting.notes = notes
        meeting.save()

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.meeting_completed',
            obj=lead,
            metadata={'meeting_id': str(meeting.id)}
        )
        return meeting

    @staticmethod
    def cancel_meeting(*, meeting, actor):
        from apps.permissions_engine.services.engine import PermissionEngine
        if actor and not actor.is_superuser and not PermissionEngine.has_perm(actor, 'leads.create_meeting'):
            raise PermissionError("Actor does not have permission to cancel a meeting.")

        lead = meeting.lead
        if actor and not actor.is_superuser and actor.company and lead.company != actor.company:
            raise PermissionError("Company mismatch: Lead does not belong to your company.")

        meeting.status = 'cancelled'
        meeting.save()

        AuditService.log(
            company=lead.company,
            actor=actor,
            action='lead.meeting_cancelled',
            obj=lead,
            metadata={'meeting_id': str(meeting.id)}
        )
        return meeting
