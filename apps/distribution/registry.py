from importlib import import_module
from apps.distribution.strategies import (
    RoundRobinLoadBalancedStrategy,
    ByTurnSequentialStrategy,
    RetryTeamEscalationStrategy,
    ManualAssignmentStrategy,
    WalkInOpenFloorStrategy,
    WalkInTeamTurnStrategy,
    WalkInFullRotationStrategy,
)


class DistributionStrategyRegistry:
    _registry = {
        RoundRobinLoadBalancedStrategy.code: RoundRobinLoadBalancedStrategy,
        ByTurnSequentialStrategy.code: ByTurnSequentialStrategy,
        RetryTeamEscalationStrategy.code: RetryTeamEscalationStrategy,
        ManualAssignmentStrategy.code: ManualAssignmentStrategy,
        WalkInOpenFloorStrategy.code: WalkInOpenFloorStrategy,
        WalkInTeamTurnStrategy.code: WalkInTeamTurnStrategy,
        WalkInFullRotationStrategy.code: WalkInFullRotationStrategy,
    }

    @classmethod
    def register(cls, strategy_cls):
        cls._registry[strategy_cls.code] = strategy_cls
        return strategy_cls

    @classmethod
    def get(cls, code):
        if code not in cls._registry:
            raise KeyError(f'Unknown distribution strategy: {code}')
        return cls._registry[code]()

