from __future__ import annotations

from datetime import timedelta
from typing import Any

from apps.core.models import CompanyPolicy


class PolicyResolver:
    """Reads company behaviour from DB.

    The three CRM documents define canonical policy codes.  Earlier project
    iterations used a few different names.  This resolver accepts the documented
    codes first and falls back to legacy aliases so the codebase can be upgraded
    without breaking existing seeded company policies.
    """

    POLICY_ALIASES = {
        'automatic_distribution_strategy': ('lead_auto_distribution_strategy',),
        'lead_auto_distribution_strategy': ('automatic_distribution_strategy',),
        'distribution_scope_mode': ('lead_distribution_scope_mode',),
        'lead_distribution_scope_mode': ('distribution_scope_mode',),
        'origin_sla_direct': ('sla_origin_direct',),
        'origin_sla_broker': ('sla_origin_broker',),
        'stage_sla_fresh': ('sla_stage_fresh',),
        'stage_sla_interested': ('sla_stage_interested',),
        'stage_sla_not_reached': ('sla_stage_not_reached', 'sla_stage_no_answer'),
        'stage_sla_frozen': ('sla_stage_frozen',),
        'stage_sla_follow_up': ('sla_stage_follow_up', 'sla_stage_followup'),
        'stage_sla_meeting': ('sla_stage_meeting',),
        'sla_breach_action_broker': ('broker_sla_breach_action',),
        'existing_client_policy': ('existing_client_retain_salesman',),
        'existing_client_retain_salesman': ('existing_client_policy',),
        'integration_meta_connector': ('meta_connector_mode',),
        'meta_connector_mode': ('integration_meta_connector',),
        'campaign_budget_calculation_rule': ('campaign_budget_rule',),
    }

    VALUE_ALIASES = {
        # Existing-client policy values from older seed data -> document values.
        'retain': 'preserve_original_salesman',
        'redistribute': 'redistribute_by_policy',
        'redistribute_directly': 'redistribute_by_policy',
        # Integration connector values from older seed data -> document values.
        'make_dynamic_webhook': 'make',
        'zapier_dynamic_webhook': 'zapier',
    }

    @classmethod
    def _candidate_codes(cls, policy_code: str) -> list[str]:
        code = (policy_code or '').strip()
        candidates = [code]
        for alias in cls.POLICY_ALIASES.get(code, ()):  # documented -> legacy and legacy -> documented
            if alias not in candidates:
                candidates.append(alias)
        return candidates

    @classmethod
    def _normalize_value(cls, value: Any):
        if isinstance(value, str):
            return cls.VALUE_ALIASES.get(value, value)
        if isinstance(value, dict):
            normalized = dict(value)
            code = normalized.get('code')
            if isinstance(code, str):
                normalized['code'] = cls.VALUE_ALIASES.get(code, code)
            return normalized
        return value

    @classmethod
    def _get_policy(cls, company, policy_code: str):
        return (
            CompanyPolicy.objects
            .select_related('policy_definition', 'selected_option')
            .filter(company=company, policy_definition__code__in=cls._candidate_codes(policy_code), is_active=True)
            .order_by('policy_definition__code')
            .first()
        )

    @classmethod
    def get(cls, company, policy_code: str, default=None):
        policy = cls._get_policy(company, policy_code)
        if not policy:
            return default
        if policy.selected_option:
            if policy.selected_option.value not in ({}, None):
                return cls._normalize_value(policy.selected_option.value)
            return cls._normalize_value(policy.selected_option.code)
        return cls._normalize_value(policy.value) if policy.value not in ({}, None) else default

    @classmethod
    def get_code(cls, company, policy_code: str, default=None):
        policy = cls._get_policy(company, policy_code)
        if policy and policy.selected_option:
            return cls._normalize_value(policy.selected_option.code)
        value = policy.value if policy else None
        if isinstance(value, dict):
            return cls._normalize_value(value.get('code', default))
        return cls._normalize_value(value) or default

    @classmethod
    def get_bool(cls, company, policy_code: str, default=False):
        value = cls.get(company, policy_code, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            value = value.get('value', value.get('enabled', default))
        if isinstance(value, str):
            return value.lower() in {'1', 'true', 'yes', 'y', 'on'}
        return bool(value)

    @classmethod
    def get_int(cls, company, policy_code: str, default=0):
        value = cls.get(company, policy_code, default)
        if isinstance(value, dict):
            value = value.get('value', value.get('count', value.get('attempts', default)))
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @classmethod
    def get_duration(cls, company, policy_code: str, default: timedelta | None = None) -> timedelta | None:
        """Resolve duration policies stored as JSON, integer minutes, or strings.

        Supported JSON examples:
        - {'duration_value': 30, 'duration_unit': 'minutes'}
        - {'value': 2, 'unit': 'hours'}
        - {'minutes': 30}
        """
        value = cls.get(company, policy_code, None)
        if value in (None, ''):
            return default
        if isinstance(value, timedelta):
            return value
        if isinstance(value, (int, float)):
            return timedelta(minutes=int(value))
        if isinstance(value, str):
            try:
                return timedelta(minutes=int(value))
            except ValueError:
                return default
        if isinstance(value, dict):
            if 'minutes' in value:
                return timedelta(minutes=int(value['minutes']))
            if 'hours' in value:
                return timedelta(hours=int(value['hours']))
            if 'days' in value:
                return timedelta(days=int(value['days']))
            amount = value.get('duration_value', value.get('value', value.get('count')))
            unit = value.get('duration_unit', value.get('unit', 'minutes'))
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                return default
            if unit == 'days':
                return timedelta(days=amount)
            if unit == 'hours':
                return timedelta(hours=amount)
            return timedelta(minutes=amount)
        return default

    @classmethod
    def get_for_source(cls, company, source_code: str, policy_code: str, default=None):
        """Resolve a policy with source-code awareness."""
        value = cls.get(company, policy_code, default)
        if isinstance(value, dict) and source_code in value:
            return cls._normalize_value(value[source_code])
        return value

    @classmethod
    def get_stage_sla(cls, company, stage_code: str):
        """Retrieve SLA configuration for a stage using document and legacy codes."""
        normalized = (stage_code or '').replace('-', '_')
        candidates = [
            f'stage_sla_{normalized}',
            f'sla_stage_{normalized}',
        ]
        if normalized == 'followup':
            candidates.extend(['stage_sla_follow_up', 'sla_stage_follow_up'])
        for code in candidates:
            value = cls.get(company, code)
            if value:
                return value
        return cls.get(company, 'sla_default_config')

    @classmethod
    def get_distribution_strategy_code(cls, company, source_code: str = '', default='round_robin_load_balanced'):
        source_specific = cls.get_for_source(company, source_code, 'automatic_distribution_strategy')
        if isinstance(source_specific, dict):
            source_specific = source_specific.get('code')
        if source_specific and source_specific != default:
            return cls._normalize_value(source_specific)
        return cls.get_code(company, 'automatic_distribution_strategy', default)

    @classmethod
    def get_distribution_scope_mode(cls, company, default='all_salesmen'):
        return cls.get_code(company, 'distribution_scope_mode', default)

    @classmethod
    def get_retry_attempt_window(cls, company, default_minutes=60) -> timedelta:
        return cls.get_duration(company, 'retry_attempt_window', timedelta(minutes=default_minutes))

    @classmethod
    def get_walkin_policy(cls, company):
        return cls.get_code(company, 'walkin_reception_policy', 'open_floor')

    @classmethod
    def get_self_generated_mode(cls, company):
        return cls.get_code(company, 'self_generated_salesman_mode', 'permanent_own')

    @classmethod
    def get_broker_assign_mode(cls, company):
        return cls.get_code(company, 'broker_auto_assign_salesman', 'broker_only')

    @classmethod
    def get_existing_client_mode(cls, company):
        return cls.get_code(company, 'existing_client_policy', 'preserve_original_salesman')

    @classmethod
    def approval_reason_required(cls, company, status: str) -> bool:
        policy = cls.get(company, 'finance_approval_reason_required', {'semi_approved': True, 'not_approved': True})
        if isinstance(policy, bool):
            return policy
        if isinstance(policy, dict):
            return bool(policy.get(status, policy.get('value', status in {'semi_approved', 'not_approved'})))
        return status in {'semi_approved', 'not_approved'}
