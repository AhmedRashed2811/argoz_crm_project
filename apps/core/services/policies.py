from apps.core.models import CompanyPolicy, PolicyDefinition


class PolicyResolver:
    """Reads behavior from DB. Services call this instead of hardcoding policy values."""

    @staticmethod
    def get(company, policy_code: str, default=None):
        policy = (
            CompanyPolicy.objects
            .select_related('policy_definition', 'selected_option')
            .filter(company=company, policy_definition__code=policy_code, is_active=True)
            .first()
        )
        if not policy:
            return default
        if policy.selected_option:
            if policy.selected_option.value not in ({}, None):
                return policy.selected_option.value
            return policy.selected_option.code
        return policy.value if policy.value not in ({}, None) else default

    @staticmethod
    def get_code(company, policy_code: str, default=None):
        policy = (
            CompanyPolicy.objects
            .select_related('selected_option', 'policy_definition')
            .filter(company=company, policy_definition__code=policy_code, is_active=True)
            .first()
        )
        if policy and policy.selected_option:
            return policy.selected_option.code
        value = policy.value if policy else None
        if isinstance(value, dict):
            return value.get('code', default)
        return value or default

    @classmethod
    def get_for_source(cls, company, source_code: str, policy_code: str, default=None):
        """Resolve a policy with source-code awareness.

        Looks for a company policy whose value JSON contains a source-specific
        override, falling back to the generic policy value.
        """
        value = cls.get(company, policy_code, default)
        if isinstance(value, dict) and source_code in value:
            return value[source_code]
        return value

    @classmethod
    def get_stage_sla(cls, company, stage_code: str):
        """Retrieve SLA configuration for a specific stage from the policies table.

        Returns a dict with keys like 'duration_value', 'duration_unit',
        'breach_action', 'expiry_strategy_code'.  Falls back to None if
        not configured.
        """
        value = cls.get(company, f'sla_stage_{stage_code}')
        if value:
            return value
        return cls.get(company, 'sla_default_config')

    @classmethod
    def get_distribution_strategy_code(cls, company, source_code: str = '', default='round_robin_load_balanced'):
        """Get the distribution strategy code, optionally source-aware."""
        source_specific = cls.get_for_source(company, source_code, 'lead_auto_distribution_strategy')
        if source_specific and source_specific != default:
            return source_specific
        return cls.get_code(company, 'lead_auto_distribution_strategy', default)

    @classmethod
    def get_walkin_policy(cls, company):
        """Get the walk-in reception policy code for a company."""
        return cls.get_code(company, 'walkin_reception_policy', 'open_floor')

    @classmethod
    def get_self_generated_mode(cls, company):
        """Get the self-generated lead salesman behavior policy."""
        return cls.get_code(company, 'self_generated_salesman_mode', 'permanent_own')

    @classmethod
    def get_broker_assign_mode(cls, company):
        """Get the broker lead assignment behavior."""
        return cls.get_code(company, 'broker_auto_assign_salesman', 'broker_only')

    @classmethod
    def get_existing_client_mode(cls, company):
        """Get the existing client salesman retention policy."""
        return cls.get_code(company, 'existing_client_retain_salesman', 'retain')
