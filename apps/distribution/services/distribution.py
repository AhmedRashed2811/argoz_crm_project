from django.db import transaction
from django.utils import timezone
from apps.core.services.policies import PolicyResolver
from apps.distribution.registry import DistributionStrategyRegistry
from apps.audit.services.audit import AuditService


class DistributionService:
    DEFAULT_STRATEGY = 'round_robin_load_balanced'
    DEFAULT_SCOPE = 'all_salesmen'

    @classmethod
    def assign(cls, *, lead, actor=None, strategy_code=None, scope_mode=None, team=None, salesman=None, reason=''):
        # If no strategy code specified, resolve from walk-in policy or generic policy
        if not strategy_code:
            source_code = lead.source.code if lead.source else ''
            if source_code == 'walkin':
                walkin_policy = PolicyResolver.get_walkin_policy(lead.company)
                strategy_map = {
                    'open_floor': 'walkin_open_floor',
                    'team_turn': 'walkin_team_turn',
                    'full_rotation': 'walkin_full_rotation',
                }
                strategy_code = strategy_map.get(walkin_policy, cls.DEFAULT_STRATEGY)
            else:
                strategy_code = PolicyResolver.get_distribution_strategy_code(
                    lead.company, source_code, cls.DEFAULT_STRATEGY,
                )
        scope_mode = scope_mode or PolicyResolver.get_distribution_scope_mode(lead.company, cls.DEFAULT_SCOPE)
        # Resolve the language pre-check (defaults to the company default language
        # per Doc 1 §3.2.3) and pass it down so every strategy filters the pool.
        from apps.distribution.selectors import resolve_distribution_language
        language = resolve_distribution_language(lead)
        strategy = DistributionStrategyRegistry.get(strategy_code)
        result = strategy.assign(lead=lead, actor=actor, scope_mode=scope_mode, team=team, salesman=salesman, language=language)
        AuditService.log(company=lead.company, actor=actor, action='lead.assigned', obj=lead, after={
            'strategy_code': result.strategy_code,
            'salesman_id': str(result.salesman_id) if hasattr(result, 'salesman_id') else str(result.salesman.id) if result.salesman else None,
            'team_id': str(result.team.id) if result.team else None,
            'reason': result.reason or reason,
        })
        return result

    @classmethod
    def manual_assign(cls, *, lead, actor, team=None, salesman=None):
        return cls.assign(lead=lead, actor=actor, strategy_code='manual_assignment', scope_mode='manual', team=team, salesman=salesman)


class ManualDistributionService:
    @classmethod
    @transaction.atomic
    def assign_request(cls, request_obj, salesman, team=None, actor=None):
        if request_obj.status != 'pending':
            raise ValueError("This request is already processed.")

        from apps.leads.services.leads import LeadService
        # Assign the lead manually
        LeadService.assign_lead(lead=request_obj.lead, actor=actor, strategy_code='manual_assignment', salesman=salesman, team=team)

        request_obj.status = 'assigned'
        request_obj.assigned_to = salesman
        if team:
            request_obj.original_team = team
        request_obj.actioned_by = actor
        request_obj.actioned_at = timezone.now()
        request_obj.save()

        AuditService.log(
            company=request_obj.lead.company, actor=actor, action='lead.manual_request_assigned',
            obj=request_obj.lead, metadata={'request_id': str(request_obj.id), 'salesman_id': str(salesman.id)}
        )
        return request_obj

    @classmethod
    @transaction.atomic
    def ignore_request(cls, request_obj, actor=None, reason=''):
        if request_obj.status != 'pending':
            raise ValueError("This request is already processed.")

        request_obj.status = 'ignored'
        request_obj.actioned_by = actor
        request_obj.actioned_at = timezone.now()
        request_obj.reason = reason
        request_obj.save()

        # Start a new SLA for the original salesman as they were preserved
        from apps.sla.services.sla import SLAService
        lead = request_obj.lead
        assignment = lead.assignments.filter(is_current=True).first()
        SLAService.start_for_lead(lead, assignment=assignment)

        AuditService.log(
            company=lead.company, actor=actor, action='lead.manual_request_ignored',
            obj=lead, metadata={'request_id': str(request_obj.id), 'reason': reason}
        )
        return request_obj
