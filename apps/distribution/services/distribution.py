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
        strategy = DistributionStrategyRegistry.get(strategy_code)
        result = strategy.assign(lead=lead, actor=actor, scope_mode=scope_mode, team=team, salesman=salesman)
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
