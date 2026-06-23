"""
Seed default CRM configuration data.

Usage:
    python manage.py seed_defaults
    python manage.py seed_defaults --company-slug=my-company   # seed company-specific data too
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from apps.core.permissions import all_documented_permission_codes


# ---------------------------------------------------------------------------
# Default Lead Stages
# ---------------------------------------------------------------------------
DEFAULT_STAGES = [
    {'code': 'fresh', 'name': 'Fresh', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 0},
    {'code': 'interested', 'name': 'Interested', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 10},
    {'code': 'not_interested', 'name': 'Not Interested', 'is_active_stage': False, 'is_terminal': True, 'sort_order': 20},
    {'code': 'follow_up', 'name': 'Follow Up', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 30},
    {'code': 'meeting', 'name': 'Meeting', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 40},
    {'code': 'not_reached', 'name': 'Not Reached', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 50},
    {'code': 'frozen', 'name': 'Frozen', 'is_active_stage': True, 'is_terminal': False, 'sort_order': 60},
    {'code': 'no_answer', 'name': 'No Answer', 'is_active_stage': False, 'is_terminal': True, 'sort_order': 70},
    {'code': 'travelled', 'name': 'Travelled', 'is_active_stage': False, 'is_terminal': True, 'sort_order': 80},
    {'code': 'deceased', 'name': 'Deceased', 'is_active_stage': False, 'is_terminal': True, 'sort_order': 90},
]

# ---------------------------------------------------------------------------
# Default Lead Sources (the 8 from Doc 2)
# ---------------------------------------------------------------------------
DEFAULT_SOURCES = [
    {'code': 'self_generated', 'name': 'Self Generated', 'requires_how_did_you_know': False},
    {'code': 'campaign', 'name': 'Campaign', 'requires_how_did_you_know': False},
    {'code': 'broker', 'name': 'Broker', 'requires_how_did_you_know': False},
    {'code': 'walkin', 'name': 'Walk-in', 'requires_how_did_you_know': True},
    {'code': 'call_center', 'name': 'Call Center', 'requires_how_did_you_know': True},
    {'code': 'exhibition', 'name': 'Exhibition', 'requires_how_did_you_know': False},
    {'code': 'referral', 'name': 'Referral', 'requires_how_did_you_know': False},
    {'code': 'existing_client', 'name': 'Existing Client', 'requires_how_did_you_know': False},
]

# ---------------------------------------------------------------------------
# Default "How Did You Know" Options (including mandatory "Website")
# ---------------------------------------------------------------------------
DEFAULT_HOW_OPTIONS = [
    'Website',
    'Social Media',
    'Friend / Referral',
    'TV / Radio',
    'Street Ads',
    'Exhibition',
    'Online Search',
    'Other',
]

# ---------------------------------------------------------------------------
# Default Policy Definitions and Options
# ---------------------------------------------------------------------------
DEFAULT_POLICIES = [
    {
        'code': 'lead_auto_distribution_strategy',
        'module': 'distribution',
        'name': 'Lead Auto-Distribution Strategy',
        'data_type': 'choice',
        'options': [
            {'code': 'round_robin_load_balanced', 'label': 'Round Robin (Load Balanced)', 'sort_order': 0},
            {'code': 'by_turn', 'label': 'By Turn (Sequential)', 'sort_order': 1},
        ],
    },
    {
        'code': 'lead_distribution_scope_mode',
        'module': 'distribution',
        'name': 'Distribution Scope Mode',
        'data_type': 'choice',
        'options': [
            {'code': 'all_salesmen', 'label': 'All Salesmen (company-wide)', 'sort_order': 0},
            {'code': 'team_then_salesman', 'label': 'Team then Salesman', 'sort_order': 1},
            {'code': 'team_then_sales_head', 'label': 'Team then Sales Head Decides', 'sort_order': 2},
        ],
    },
    {
        'code': 'walkin_reception_policy',
        'module': 'distribution',
        'name': 'Walk-in Reception Policy',
        'data_type': 'choice',
        'options': [
            {'code': 'open_floor', 'label': 'Policy 1 – Open Floor (Any Available Salesman)', 'sort_order': 0},
            {'code': 'team_turn', 'label': 'Policy 2 – Team Turn (Sequential Team Rotation, Head Assigns)', 'sort_order': 1},
            {'code': 'full_rotation', 'label': 'Policy 3 – Full Rotation (All Salesmen Across All Teams)', 'sort_order': 2},
        ],
    },
    {
        'code': 'sla_breach_action_direct',
        'module': 'sla',
        'name': 'SLA Breach Action for Direct Leads',
        'data_type': 'choice',
        'options': [
            {'code': 'automatic_redistribution', 'label': 'Automatic Redistribution', 'sort_order': 0},
            {'code': 'manual_reassignment', 'label': 'Manual Reassignment', 'sort_order': 1},
        ],
    },
    {
        'code': 'self_generated_salesman_mode',
        'module': 'leads',
        'name': 'Self-Generated Lead Salesman Behavior',
        'data_type': 'choice',
        'options': [
            {'code': 'permanent_own', 'label': 'Lead permanently assigned to the salesman', 'sort_order': 0},
            {'code': 'sla_redistribute', 'label': 'Redistribute via SLA if no contact is made', 'sort_order': 1},
        ],
    },
    {
        'code': 'broker_auto_assign_salesman',
        'module': 'leads',
        'name': 'Broker Lead: Auto-Assign to Company Salesman',
        'data_type': 'choice',
        'options': [
            {'code': 'broker_only', 'label': 'Remain with broker only', 'sort_order': 0},
            {'code': 'assign_salesman', 'label': 'Also assign to a company salesman', 'sort_order': 1},
        ],
    },
    {
        'code': 'existing_client_retain_salesman',
        'module': 'leads',
        'name': 'Existing Client: Retain Original Salesman',
        'data_type': 'choice',
        'options': [
            {'code': 'retain', 'label': 'Preserve previous salesman relationship', 'sort_order': 0},
            {'code': 'redistribute', 'label': 'Redistribute directly (ignore previous salesman)', 'sort_order': 1},
        ],
    },
    {
        'code': 'sla_reminder_schedule',
        'module': 'sla',
        'name': 'SLA Reminder Schedule (minutes before due)',
        'data_type': 'json',
        'options': [],
    },
]


# Additional canonical policy definitions from the technical document.  The
# resolver also supports legacy names, but seeding these codes makes new
# installations match the documents directly.
DEFAULT_POLICIES.extend([
    {
        'code': 'automatic_distribution_strategy', 'module': 'distribution', 'name': 'Automatic Distribution Strategy', 'data_type': 'choice',
        'options': [
            {'code': 'round_robin_load_balanced', 'label': 'Round Robin (Load Balanced)', 'sort_order': 0},
            {'code': 'by_turn', 'label': 'By Turn (Sequential)', 'sort_order': 1},
            {'code': 'retry_team_escalation', 'label': 'Retry Attempts and Team Escalation', 'sort_order': 2},
        ],
    },
    {
        'code': 'distribution_scope_mode', 'module': 'distribution', 'name': 'Distribution Scope Mode', 'data_type': 'choice',
        'options': [
            {'code': 'all_salesmen', 'label': 'All Salesmen', 'sort_order': 0},
            {'code': 'team_then_salesman', 'label': 'Team then Salesman', 'sort_order': 1},
            {'code': 'team_then_sales_head', 'label': 'Team then Sales Head', 'sort_order': 2},
        ],
    },
    {'code': 'sla_breach_action_broker', 'module': 'sla', 'name': 'SLA Breach Action for Broker Leads', 'data_type': 'choice', 'options': [{'code': 'manual_reassignment', 'label': 'Manual Reassignment', 'sort_order': 0}]},
    {'code': 'retry_attempts_per_team', 'module': 'distribution', 'name': 'Retry Attempts Per Team', 'data_type': 'integer', 'options': []},
    {'code': 'retry_attempt_window', 'module': 'distribution', 'name': 'Retry Attempt Window', 'data_type': 'duration', 'options': []},
    {'code': 'origin_sla_direct', 'module': 'sla', 'name': 'Origin SLA - Direct Leads', 'data_type': 'duration', 'options': []},
    {'code': 'origin_sla_broker', 'module': 'sla', 'name': 'Origin SLA - Broker Leads', 'data_type': 'duration', 'options': []},
    {'code': 'stage_sla_fresh', 'module': 'sla', 'name': 'Stage SLA - Fresh', 'data_type': 'duration', 'options': []},
    {'code': 'stage_sla_interested', 'module': 'sla', 'name': 'Stage SLA - Interested', 'data_type': 'duration', 'options': []},
    {'code': 'stage_sla_not_reached', 'module': 'sla', 'name': 'Stage SLA - Not Reached', 'data_type': 'duration', 'options': []},
    {'code': 'stage_sla_frozen', 'module': 'sla', 'name': 'Stage SLA - Frozen', 'data_type': 'duration', 'options': []},
    {'code': 'reminder_mode_not_reached', 'module': 'sla', 'name': 'Reminder Mode for Not Reached Stage', 'data_type': 'choice', 'options': [{'code': 'automatic', 'label': 'Automatic', 'sort_order': 0}, {'code': 'manual', 'label': 'Manual', 'sort_order': 1}]},
    {'code': 'campaign_budget_calculation_rule', 'module': 'marketing', 'name': 'Campaign Budget Calculation Rule', 'data_type': 'choice', 'options': [{'code': 'standard_total', 'label': 'Standard Total', 'sort_order': 0}, {'code': 'type_level_only', 'label': 'Type Level Only', 'sort_order': 1}, {'code': 'policy_custom', 'label': 'Policy Custom', 'sort_order': 2}]},
    {'code': 'finance_approval_reason_required', 'module': 'marketing', 'name': 'Finance Approval Reason Required', 'data_type': 'json', 'options': []},
    {'code': 'integration_meta_connector', 'module': 'integrations', 'name': 'Integration Meta Connector', 'data_type': 'choice', 'options': [{'code': 'make', 'label': 'Make', 'sort_order': 0}, {'code': 'zapier', 'label': 'Zapier', 'sort_order': 1}, {'code': 'native_future', 'label': 'Native Future', 'sort_order': 2}]},
])

# ---------------------------------------------------------------------------
# Default Distribution Strategy Definitions (DB records)
# ---------------------------------------------------------------------------
DEFAULT_STRATEGIES = [
    {'code': 'round_robin_load_balanced', 'class_path': 'apps.distribution.strategies.RoundRobinLoadBalancedStrategy', 'name': 'Round Robin Load Balanced'},
    {'code': 'by_turn', 'class_path': 'apps.distribution.strategies.ByTurnSequentialStrategy', 'name': 'By Turn Sequential'},
    {'code': 'manual_assignment', 'class_path': 'apps.distribution.strategies.ManualAssignmentStrategy', 'name': 'Manual Assignment'},
    {'code': 'retry_team_escalation', 'class_path': 'apps.distribution.strategies.RetryTeamEscalationStrategy', 'name': 'Retry Attempts & Team Escalation'},
    {'code': 'walkin_open_floor', 'class_path': 'apps.distribution.strategies.WalkInOpenFloorStrategy', 'name': 'Walk-in – Open Floor'},
    {'code': 'walkin_team_turn', 'class_path': 'apps.distribution.strategies.WalkInTeamTurnStrategy', 'name': 'Walk-in – Team Turn'},
    {'code': 'walkin_full_rotation', 'class_path': 'apps.distribution.strategies.WalkInFullRotationStrategy', 'name': 'Walk-in – Full Rotation'},
]

# ---------------------------------------------------------------------------
# Default Notification Types (Section 28.1 catalog)
# ---------------------------------------------------------------------------
DEFAULT_NOTIFICATION_TYPES = [
    {'code': 'lead_assigned', 'name': 'Lead Assigned', 'category': 'lead', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'lead_stage_changed', 'name': 'Lead Stage Changed', 'category': 'lead', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'lead_reassigned', 'name': 'Lead Reassigned', 'category': 'lead', 'severity': 'warning', 'default_channels': ['in_app', 'email']},
    {'code': 'lead_reactivated', 'name': 'Lead Reactivated', 'category': 'lead', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'sla_warning', 'name': 'SLA Warning', 'category': 'sla', 'severity': 'warning', 'default_channels': ['in_app']},
    {'code': 'sla_expired', 'name': 'SLA Expired', 'category': 'sla', 'severity': 'critical', 'default_channels': ['in_app', 'email']},
    {'code': 'sla_expired_manual_required', 'name': 'SLA Expired – Manual Reassignment Required', 'category': 'sla', 'severity': 'critical', 'default_channels': ['in_app', 'email']},
    {'code': 'followup_reminder', 'name': 'Follow-up Reminder', 'category': 'reminder', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'meeting_reminder', 'name': 'Meeting Reminder', 'category': 'reminder', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'frozen_reactivation', 'name': 'Frozen Period Ended', 'category': 'reminder', 'severity': 'warning', 'default_channels': ['in_app']},
    {'code': 'campaign_approval_decided', 'name': 'Campaign Approval Decision', 'category': 'campaign', 'severity': 'info', 'default_channels': ['in_app', 'email']},
    {'code': 'campaign_budget_updated', 'name': 'Campaign Budget Updated', 'category': 'campaign', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'webhook_payload_failed', 'name': 'Webhook Payload Processing Failed', 'category': 'integration', 'severity': 'critical', 'default_channels': ['in_app', 'email']},
    {'code': 'permission_changed', 'name': 'Permissions Changed', 'category': 'permission', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'generic', 'name': 'General Reminder', 'category': 'reminder', 'severity': 'info', 'default_channels': ['in_app']},
    {'code': 'system_announcement', 'name': 'System Announcement', 'category': 'system', 'severity': 'info', 'default_channels': ['in_app']},
]

# ---------------------------------------------------------------------------
# Default Group Templates with permission codenames
# ---------------------------------------------------------------------------
DEFAULT_GROUPS = {
    'System Admins': [
        'accounts.view_users', 'accounts.create_user', 'accounts.update_user', 'accounts.deactivate_user',
        'accounts.manage_user_groups',
        'companies.view_company_dashboard', 'companies.manage_company', 'companies.manage_branches',
        'companies.manage_teams', 'companies.manage_languages',
        'permissions_engine.view_matrix', 'permissions_engine.manage_group_templates',
        'permissions_engine.manage_user_permissions',
        'core.view_policies', 'core.manage_policies',
        'leads.view_all', 'leads.import_leads', 'leads.export_leads', 'leads.manage_sources',
        'distribution.view_queue', 'distribution.run_manual', 'distribution.manage_strategies', 'distribution.view_logs',
        'sla.view_dashboard', 'sla.manage_policies', 'sla.process_expired_manual',
        'integrations.view_integrations', 'integrations.manage_meta_connection',
        'integrations.manage_field_mapping', 'integrations.view_webhook_logs', 'integrations.reprocess_payload',
        'audit.view_all_logs', 'audit.view_object_timeline', 'audit.export_logs',
        'notifications.broadcast',
        'marketing.view_campaigns', 'marketing.create_campaign', 'marketing.update_campaign',
        'marketing.archive_campaign', 'marketing.manage_assets', 'marketing.manage_budget',
        'marketing.submit_approval', 'marketing.view_roi',
        'marketing.manage_campaign_types', 'marketing.manage_attribution',
    ],
    'Directors': [
        'accounts.view_users',
        'companies.view_company_dashboard',
        'leads.view_all', 'leads.view_history', 'leads.export_leads',
        'distribution.view_queue', 'distribution.view_logs',
        'sla.view_dashboard',
        'audit.view_all_logs', 'audit.view_object_timeline',
        'marketing.view_campaigns', 'marketing.view_roi',
    ],
    'Sales': [
        'leads.view_own', 'leads.change_stage', 'leads.create_followup', 'leads.create_meeting', 'leads.view_history',
    ],
    'Sales Head': [
        'leads.view_own', 'leads.view_team', 'leads.change_stage', 'leads.create_followup',
        'leads.create_meeting', 'leads.view_history', 'leads.assign_manual', 'leads.redistribute',
    ],
    'Sales Operation': [
        'leads.view_all', 'leads.import_leads', 'leads.export_leads', 'leads.assign_manual',
        'leads.redistribute', 'leads.override_assignment', 'leads.manage_sources', 'leads.reactivate',
        'distribution.view_queue', 'distribution.run_manual', 'distribution.manage_strategies', 'distribution.view_logs',
        'sla.view_dashboard', 'sla.manage_policies', 'sla.process_expired_manual',
    ],
    'Call Center': [
        'leads.view_own', 'leads.change_stage', 'leads.create_followup', 'leads.view_history',
    ],
    'Receptionists': [
        'leads.view_own', 'leads.change_stage', 'leads.view_history',
    ],
    'Brokers': [
        'leads.view_broker_leads', 'leads.view_own', 'leads.change_stage', 'leads.view_history',
    ],
    'Marketing Members': [
        'marketing.view_campaigns', 'marketing.create_campaign', 'marketing.update_campaign',
        'marketing.manage_assets', 'marketing.submit_approval',
    ],
    'Marketing Managers': [
        'marketing.view_campaigns', 'marketing.create_campaign', 'marketing.update_campaign',
        'marketing.archive_campaign', 'marketing.manage_assets', 'marketing.manage_budget',
        'marketing.submit_approval', 'marketing.view_roi',
        'marketing.manage_campaign_types', 'marketing.manage_attribution',
        'integrations.view_integrations', 'integrations.manage_meta_connection',
        'integrations.manage_field_mapping', 'integrations.view_webhook_logs',
    ],
    'Finance Managers': [
        'marketing.view_campaigns', 'marketing.manage_budget', 'marketing.view_roi',
    ],
}


class Command(BaseCommand):
    help = 'Seed default CRM configuration (stages, sources, policies, groups, notification types, strategies).'

    def add_arguments(self, parser):
        parser.add_argument('--company-slug', type=str, default=None, help='Company slug to seed company-specific data for.')

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.companies.models import Company
        from apps.leads.models import LeadStage, LeadSource, HowDidYouKnowOption
        from apps.core.models import PolicyDefinition, PolicyOption, CompanyPolicy
        from apps.distribution.models import DistributionStrategyDefinition
        from apps.notifications.models import NotificationType
        from apps.sla.models import SLADefinition
        from apps.permissions_engine.models import CRMGroupTemplate, CRMGroupTemplatePermission

        company = None
        slug = options.get('company_slug')
        if slug:
            company = Company.objects.filter(slug=slug).first()
            if not company:
                self.stderr.write(self.style.ERROR(f'Company with slug "{slug}" not found.'))
                return

        # ------ Lead Stages ------
        for s in DEFAULT_STAGES:
            LeadStage.objects.get_or_create(company=company, code=s['code'], defaults={
                'name': s['name'], 'is_active_stage': s['is_active_stage'],
                'is_terminal': s['is_terminal'], 'sort_order': s['sort_order'],
            })
        self.stdout.write(self.style.SUCCESS(f'  [OK] Lead stages seeded ({len(DEFAULT_STAGES)})'))

        # ------ Lead Sources ------
        for s in DEFAULT_SOURCES:
            LeadSource.objects.get_or_create(company=company, code=s['code'], defaults={
                'name': s['name'], 'requires_how_did_you_know': s['requires_how_did_you_know'],
            })
        self.stdout.write(self.style.SUCCESS(f'  [OK] Lead sources seeded ({len(DEFAULT_SOURCES)})'))

        # ------ How Did You Know Options (include mandatory "Website") ------
        if company:
            for name in DEFAULT_HOW_OPTIONS:
                HowDidYouKnowOption.objects.get_or_create(company=company, name=name, defaults={'is_active': True})
            self.stdout.write(self.style.SUCCESS(f'  [OK] How-did-you-know options seeded ({len(DEFAULT_HOW_OPTIONS)})'))

        # ------ Policy Definitions & Options ------
        for p in DEFAULT_POLICIES:
            defn, _ = PolicyDefinition.objects.get_or_create(code=p['code'], defaults={
                'module': p['module'], 'name': p['name'], 'data_type': p['data_type'],
            })
            for opt in p.get('options', []):
                PolicyOption.objects.get_or_create(policy_definition=defn, code=opt['code'], defaults={
                    'label': opt['label'], 'sort_order': opt.get('sort_order', 0),
                })
            # Set company defaults if company provided and policy not yet set
            if company and p.get('options'):
                if not CompanyPolicy.objects.filter(company=company, policy_definition=defn, is_active=True).exists():
                    first_option = defn.options.order_by('sort_order').first()
                    if first_option:
                        CompanyPolicy.objects.create(company=company, policy_definition=defn, selected_option=first_option)
        self.stdout.write(self.style.SUCCESS(f'  [OK] Policy definitions seeded ({len(DEFAULT_POLICIES)})'))

        # ------ Distribution Strategy Definitions ------
        for s in DEFAULT_STRATEGIES:
            DistributionStrategyDefinition.objects.get_or_create(code=s['code'], defaults={
                'class_path': s['class_path'], 'name': s['name'],
            })
        self.stdout.write(self.style.SUCCESS(f'  [OK] Distribution strategies seeded ({len(DEFAULT_STRATEGIES)})'))

        # ------ Notification Types ------
        for nt in DEFAULT_NOTIFICATION_TYPES:
            NotificationType.objects.get_or_create(code=nt['code'], defaults={
                'name': nt['name'], 'category': nt['category'],
                'severity': nt['severity'], 'default_channels': nt['default_channels'],
            })
        self.stdout.write(self.style.SUCCESS(f'  [OK] Notification types seeded ({len(DEFAULT_NOTIFICATION_TYPES)})'))

        # ------ Default SLA Definitions (company-specific) ------
        if company:
            fresh_stage = LeadStage.objects.filter(company=company, code='fresh').first()
            if fresh_stage and not SLADefinition.objects.filter(company=company).exists():
                SLADefinition.objects.create(
                    company=company, stage=fresh_stage,
                    duration_value=24, duration_unit='hours',
                    breach_action='automatic_redistribution',
                    expiry_strategy_code='round_robin_load_balanced',
                    reminder_config={'minutes_before': [60, 30]},
                )
                self.stdout.write(self.style.SUCCESS('  [OK] Default SLA definition seeded'))

        # ------ Group Templates & Permissions ------
        for group_name, perm_codes in DEFAULT_GROUPS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            # Attach Django permissions (best-effort: skip if codename not found)
            perms = []
            for code in perm_codes:
                parts = code.split('.')
                if len(parts) == 2:
                    perm = Permission.objects.filter(content_type__app_label=parts[0], codename=parts[1]).first()
                    if perm:
                        perms.append(perm)
            if perms:
                group.permissions.set(perms)
            # Also create CRMGroupTemplate mirror
            tpl, _ = CRMGroupTemplate.objects.get_or_create(company=company, code=group_name.lower().replace(' ', '_'), defaults={
                'name': group_name, 'is_system_default': True,
            })
            for code in perm_codes:
                CRMGroupTemplatePermission.objects.get_or_create(group_template=tpl, permission_codename=code, defaults={'is_allowed': True})

        self.stdout.write(self.style.SUCCESS(f'  [OK] Group templates seeded ({len(DEFAULT_GROUPS)})'))
        self.stdout.write(self.style.SUCCESS('\n[OK] All defaults seeded successfully.'))
