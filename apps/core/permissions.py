"""Central CRM permission contract.

The business/technical documents define user-facing permission codes such as
``leads.create_lead`` and ``marketing.manage_campaign_budget``.  Earlier
versions of this project used shorter legacy names such as ``leads.create`` and
``marketing.manage_budget``.  This module keeps the documented contract in one
place and exposes legacy aliases so services can accept either code without
breaking existing seeded data.
"""

DOCUMENTED_PERMISSIONS = {
    'leads.view_lead': 'View lead records and lead detail pages',
    'leads.create_lead': 'Create leads from supported sources',
    'leads.update_lead': 'Update lead contact data and notes',
    'leads.assign_lead_manual': 'Manually assign a lead to a team or salesman',
    'leads.redistribute_lead': 'Trigger or approve lead redistribution',
    'leads.change_lead_stage': 'Change lead stage and create stage history',
    'leads.view_lead_history': 'View assignment, activity, and stage history',
    'distribution.manage_distribution_policy': 'Configure distribution methods and scope modes',
    'distribution.run_manual_distribution': 'Perform manual distribution actions',
    'sla.manage_sla_policy': 'Configure stage and origin SLA rules',
    'marketing.view_campaign': 'View campaign list, detail, budget, and reports',
    'marketing.create_campaign': 'Create campaign master and child type records',
    'marketing.update_campaign': 'Edit campaign data and assets',
    'marketing.manage_campaign_budget': 'Edit budget and other cost lines',
    'marketing.submit_campaign_for_approval': 'Send campaign to finance review',
    'marketing.view_campaign_roi': 'View campaign ROI and KPI screens',
    'finance.approve_campaign': 'Approve, semi-approve, or reject campaign budget',
    'integrations.manage_meta_connection': 'Generate tenant webhooks and configure Meta lead mappings',
    'audit.view_audit_log': 'View central audit records and object timelines',
    'companies.manage_company_policy': 'Configure company policy values and options',
}

PERMISSION_ALIASES = {
    # lead aliases
    # No alias for leads.view_lead to scoped legacy permissions: view_own/team/all
    # are data-scope permissions and must not become interchangeable.
    'leads.create_lead': {'leads.create'},
    'leads.update_lead': {'leads.update'},
    'leads.assign_lead_manual': {'leads.assign_manual'},
    'leads.redistribute_lead': {'leads.redistribute'},
    'leads.change_lead_stage': {'leads.change_stage'},
    'leads.view_lead_history': {'leads.view_history'},
    # distribution / SLA aliases
    'distribution.manage_distribution_policy': {'distribution.manage_strategies'},
    'distribution.run_manual_distribution': {'distribution.run_manual'},
    'sla.manage_sla_policy': {'sla.manage_policies'},
    # marketing aliases
    'marketing.view_campaign': {'marketing.view_campaigns'},
    'marketing.manage_campaign_budget': {'marketing.manage_budget'},
    'marketing.submit_campaign_for_approval': {'marketing.submit_approval'},
    'marketing.view_campaign_roi': {'marketing.view_roi'},
    # integrations / audit / company aliases
    'audit.view_audit_log': {'audit.view_all_logs', 'audit.view_object_timeline'},
    'companies.manage_company_policy': {'companies.manage_company', 'core.manage_policies'},
    'integrations.manage_meta_connection': {'integrations.manage_meta_connection'},
}

# Reverse aliases mean legacy checks also succeed when only documented codes were
# seeded or assigned.
for documented, aliases in list(PERMISSION_ALIASES.items()):
    for alias in aliases:
        PERMISSION_ALIASES.setdefault(alias, set()).add(documented)


def permission_candidates(permission_code: str) -> list[str]:
    """Return normalized permission code plus all known compatible aliases."""
    code = (permission_code or '').strip()
    ordered = [code]
    for alias in sorted(PERMISSION_ALIASES.get(code, set())):
        if alias not in ordered:
            ordered.append(alias)
    return ordered


def all_documented_permission_codes() -> list[str]:
    return list(DOCUMENTED_PERMISSIONS.keys())
