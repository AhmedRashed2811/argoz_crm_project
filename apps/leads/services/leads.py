from apps.sla.models import LeadSLAInstance
import re
from django.db import transaction
from apps.leads.models import Lead, LeadAssignment, LeadStageHistory, LeadReactivation
from apps.marketing.models import LeadCampaignAttribution
from apps.distribution.services.distribution import DistributionService
from apps.sla.services.sla import SLAService
from apps.audit.services.audit import AuditService
from apps.notifications.services.notifications import NotificationService
from apps.core.services.policies import PolicyResolver


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
                                origin=None, actor=None, metadata=None, **kwargs):
        """Create a lead and immediately apply the document's source-specific backend workflow.

        This keeps lead creation, duplicate handling, attribution, assignment, and SLA start
        in one transaction-safe service entry point for web views, imports, and integrations.
        """
        metadata = metadata or {}
        source_code = normalize_source_code(getattr(source, 'code', metadata.get('source_code', '')))
        if origin is None:
            origin = Lead.ORIGIN_BROKER if source_code == 'broker' else Lead.ORIGIN_DIRECT

        # Minimal backend validations from the functional document.
        if getattr(source, 'requires_how_did_you_know', False) and not (kwargs.get('how_did_you_know') or metadata.get('how_did_you_know')):
            raise ValueError('This lead source requires a "How did you know us" value. The Website option must be available in master data.')
        if source_code == 'exhibition' and not metadata.get('salesman'):
            raise ValueError('Exhibition leads must be manually assigned to a salesman and cannot remain unassigned.')
        if source_code == 'referral' and not metadata.get('referrer_name'):
            raise ValueError('Referral leads must capture the referrer name as free text.')
        if source_code == 'campaign' and not (kwargs.get('campaign') or metadata.get('campaign')):
            raise ValueError('Campaign leads must be attributed to a campaign.')
        if source_code == 'walkin' and metadata.get('how_did_you_know_name') == '':
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
            LeadService.assign_lead_by_source(lead=lead, actor=actor, source_code=source_code, metadata=merged_metadata)
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
    def assign_lead_by_source(*, lead, actor, source_code, metadata=None):
        """Source-aware assignment that applies all business rules from Doc 2 Section 4.2."""
        metadata = metadata or {}
        source_code = normalize_source_code(source_code)
        company = lead.company

        # --- a) Self-Generated ---
        if source_code == 'self_generated':
            return LeadService._assign_self_generated(lead=lead, actor=actor, metadata=metadata)

        # --- b) Campaign ---
        if source_code == 'campaign':
            if not (lead.campaign_id or metadata.get('campaign')):
                raise ValueError('Campaign leads must store campaign attribution.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'campaign')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=metadata.get('team'), salesman=metadata.get('salesman'))
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- c) Broker ---
        if source_code == 'broker':
            return LeadService._assign_broker(lead=lead, actor=actor, metadata=metadata)

        # --- d) Walk-in ---
        if source_code == 'walkin':
            return LeadService._assign_walkin(lead=lead, actor=actor, metadata=metadata)

        # --- e) Call Center ---
        if source_code == 'call_center':
            if not (metadata.get('caller_source') or metadata.get('how_did_you_know')):
                raise ValueError('Call Center leads must capture caller_source or how_did_you_know.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'call_center')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=metadata.get('team'), salesman=metadata.get('salesman'))
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- f) Exhibition ---
        if source_code == 'exhibition':
            salesman = metadata.get('salesman')
            if not salesman:
                raise ValueError('Exhibition leads must be assigned to a salesman.')
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                           salesman=salesman, team=metadata.get('team'))

        # --- g) Referral ---
        if source_code == 'referral':
            if not metadata.get('referrer_name'):
                raise ValueError('Referral leads must capture referrer_name.')
            strategy = PolicyResolver.get_distribution_strategy_code(company, 'referral')
            dist_mode = metadata.get('distribution_mode', 'automatic')
            if dist_mode == 'manual':
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               team=metadata.get('team'), salesman=metadata.get('salesman'))
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code=strategy)

        # --- h) Existing Client ---
        if source_code == 'existing_client':
            return LeadService._assign_existing_client(lead=lead, actor=actor, metadata=metadata)

        # Fallback: generic automatic distribution
        return LeadService.assign_lead(lead=lead, actor=actor)

    @staticmethod
    def _assign_self_generated(*, lead, actor, metadata):
        """Self-generated business rules from Doc 2 Section 4.2a."""
        from apps.accounts.models import TeamMembership

        mode = metadata.get('self_owner_mode') or PolicyResolver.get_self_generated_mode(lead.company)

        # Check if actor is a Sales Head
        is_sales_head = TeamMembership.objects.filter(
            user=actor, role=TeamMembership.ROLE_SALES_HEAD, is_active=True, team__company=lead.company,
        ).exists()

        if is_sales_head:
            # Sales Head: may assign to himself, a team member, or run team-level Round Robin
            salesman = metadata.get('salesman')
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
    def _assign_broker(*, lead, actor, metadata):
        """Broker business rules from Doc 2 Section 4.2c."""
        from apps.accounts.models import BrokerProfile

        broker_mode = metadata.get('broker_assign_mode') or PolicyResolver.get_broker_assign_mode(lead.company)

        # Check if actor is a broker
        is_broker = BrokerProfile.objects.filter(user=actor, company=lead.company, is_active=True).exists()

        if is_broker:
            # Broker logged in → auto-assign to broker
            result = LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment', salesman=actor)
            if broker_mode == 'assign_salesman':
                # Also assign to a company salesman (run auto-distribution)
                LeadService.assign_lead(lead=lead, actor=actor)
            return result
        else:
            # Another user logged in: select broker, optionally assign salesman
            salesman = metadata.get('salesman')
            if salesman:
                return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment',
                                               salesman=salesman, team=metadata.get('team'))
            if broker_mode == 'assign_salesman':
                return LeadService.assign_lead(lead=lead, actor=actor)
            # Remain with broker only — just mark as assigned
            return LeadService.assign_lead(lead=lead, actor=actor, strategy_code='manual_assignment')

    @staticmethod
    def _assign_walkin(*, lead, actor, metadata):
        """Walk-in reception policy from Doc 2 Section 4.2d (3 policies)."""
        policy = PolicyResolver.get_walkin_policy(lead.company)
        salesman = metadata.get('salesman')
        team = metadata.get('team')

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
        """Handle 'call me again' request within SLA — bypasses Round Robin."""
        # Close existing SLA (lead is being handled)
        active_sla = LeadSLAInstance.objects.filter(lead=lead, status='active').first()
        if active_sla:
            SLAService.close_sla(active_sla, reason='call_me_again')
        # Re-assign to current salesman manually (bypass auto-distribution)
        if lead.current_salesman:
            result = DistributionService.manual_assign(
                lead=lead, actor=actor or lead.current_salesman,
                salesman=lead.current_salesman, team=lead.current_team,
            )
            # Start a new SLA for the fresh interaction
            assignment = lead.assignments.filter(is_current=True).first()
            SLAService.start_for_lead(lead, assignment=assignment)
            AuditService.log(company=lead.company, actor=actor, action='lead.call_me_again', obj=lead)
            return result
        return None

    @staticmethod
    def change_stage(*, lead, new_stage, actor=None, reason=''):
        old_stage = lead.current_stage
        lead.current_stage = new_stage
        if new_stage.is_terminal:
            lead.status = Lead.STATUS_INACTIVE
        lead.save(update_fields=['current_stage', 'status', 'updated_at'])
        LeadStageHistory.objects.create(lead=lead, from_stage=old_stage, to_stage=new_stage, changed_by=actor, reason=reason)
        AuditService.log(company=lead.company, actor=actor, action='lead.stage_changed', obj=lead, before={'stage': getattr(old_stage, 'code', None)}, after={'stage': new_stage.code})

        # Close active SLA when stage changes (salesman took action)
        from apps.sla.models import LeadSLAInstance
        active_sla = LeadSLAInstance.objects.filter(lead=lead, status='active').first()
        if active_sla:
            SLAService.close_sla(active_sla, reason=f'stage_changed_to_{new_stage.code}')

        # If new stage has its own SLA, start it
        if not new_stage.is_terminal:
            assignment = lead.assignments.filter(is_current=True).first()
            SLAService.start_for_lead(lead, assignment=assignment)

        return lead

    @staticmethod
    def reactivate(*, lead, actor=None, reason=''):
        previous = lead.status
        lead.status = Lead.STATUS_ACTIVE
        lead.save(update_fields=['status', 'updated_at'])
        LeadReactivation.objects.create(lead=lead, reactivated_by=actor, reason=reason, previous_status=previous)
        AuditService.log(company=lead.company, actor=actor, action='lead.reactivated', obj=lead, before={'status': previous}, after={'status': lead.status})
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
