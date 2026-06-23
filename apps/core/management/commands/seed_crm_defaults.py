from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.companies.models import Company, Language
from apps.accounts.models import User, UserProfile
from apps.permissions_engine.models import CRMGroupTemplate, CRMGroupTemplatePermission
from apps.leads.models import LeadSource, LeadStage
from apps.core.models import PolicyDefinition, PolicyOption, CompanyPolicy
from apps.distribution.models import DistributionStrategyDefinition
from apps.integrations.models import IntegrationProvider
from apps.notifications.models import NotificationType

PERMISSION_CATALOG = {
    'system': ['view_dashboard', 'manage_settings', 'run_maintenance_tasks', 'view_health_checks'],
    'company': ['view_company', 'manage_company', 'manage_branches', 'manage_teams', 'manage_languages'],
    'accounts': ['view_users', 'create_user', 'update_user', 'deactivate_user', 'manage_user_groups'],
    'permissions': ['view_matrix', 'manage_group_templates', 'manage_user_permissions'],
    'policies': ['view_policies', 'manage_policies'],
    'audit': ['view_all_logs', 'view_object_timeline', 'export_logs'],
    'leads': ['view_own', 'view_team', 'view_all', 'create', 'update', 'archive', 'import', 'export', 'change_stage', 'create_followup', 'create_meeting', 'view_history', 'reactivate', 'assign_manual', 'redistribute', 'override_assignment', 'view_broker_leads'],
    'lead_sources': ['manage'],
    'distribution': ['view_queue', 'run_manual', 'manage_strategies', 'view_logs'],
    'sla': ['view_dashboard', 'manage_policies', 'process_expired_manual'],
    'reminders': ['view_own', 'view_team', 'manage'],
    'reception': ['create_walkin', 'manage_walkin_queue'],
    'callcenter': ['create_call_lead', 'view_call_queue'],
    'brokers': ['create_lead', 'view_own_leads', 'update_own_leads', 'view_own_commission'],
    'marketing': ['view_campaigns', 'create_campaign', 'update_campaign', 'archive_campaign', 'manage_assets', 'manage_budget', 'submit_approval', 'view_roi', 'manage_campaign_types', 'manage_attribution'],
    'finance': ['view_budgets', 'approve_campaign', 'view_approval_history', 'export_finance_reports'],
    'integrations': ['view', 'manage_meta_connection', 'manage_field_mapping', 'view_webhook_logs', 'reprocess_payload'],
    'notifications': ['view_own', 'manage_preferences', 'broadcast'],
    'reports': ['view_executive', 'view_sales', 'view_marketing', 'view_finance', 'export', 'view_audit'],
}

ALL_CODES = [f'{app}.{codename}' for app, codenames in PERMISSION_CATALOG.items() for codename in codenames]

GROUPS = {
    'System Admins': ALL_CODES,
    'Directors': [
        'system.view_dashboard', 'company.view_company', 'leads.view_all', 'leads.export',
        'marketing.view_campaigns', 'marketing.view_roi', 'finance.view_budgets',
        'reports.view_executive', 'reports.view_sales', 'reports.view_marketing', 'reports.view_finance', 'reports.export',
        'audit.view_all_logs', 'audit.view_object_timeline', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Sales': [
        'leads.view_own', 'leads.create', 'leads.update', 'leads.change_stage', 'leads.create_followup',
        'leads.create_meeting', 'leads.view_history', 'reminders.view_own', 'notifications.view_own', 'notifications.manage_preferences',
        'reports.view_sales',
    ],
    'Sales Head': [
        'leads.view_own', 'leads.view_team', 'leads.create', 'leads.update', 'leads.change_stage', 'leads.create_followup',
        'leads.create_meeting', 'leads.view_history', 'leads.assign_manual', 'leads.redistribute',
        'distribution.view_queue', 'distribution.run_manual', 'distribution.view_logs', 'sla.view_dashboard',
        'reminders.view_own', 'reminders.view_team', 'reports.view_sales', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Sales Operation': [
        'leads.view_all', 'leads.create', 'leads.update', 'leads.import', 'leads.export', 'leads.assign_manual',
        'leads.redistribute', 'leads.override_assignment', 'lead_sources.manage', 'distribution.view_queue',
        'distribution.run_manual', 'distribution.manage_strategies', 'distribution.view_logs', 'sla.view_dashboard',
        'sla.manage_policies', 'sla.process_expired_manual', 'reminders.manage', 'reports.view_sales', 'reports.export',
        'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Call Center': [
        'callcenter.create_call_lead', 'callcenter.view_call_queue', 'leads.create', 'leads.update', 'leads.view_own',
        'leads.view_history', 'reminders.view_own', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Receptionists': [
        'reception.create_walkin', 'reception.manage_walkin_queue', 'leads.create', 'leads.update', 'leads.view_own',
        'leads.view_history', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Brokers': [
        'brokers.create_lead', 'brokers.view_own_leads', 'brokers.update_own_leads', 'brokers.view_own_commission',
        'leads.view_broker_leads', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Marketing Members': [
        'marketing.view_campaigns', 'marketing.create_campaign', 'marketing.update_campaign', 'marketing.manage_assets',
        'marketing.submit_approval', 'marketing.view_roi', 'marketing.manage_attribution', 'leads.view_all',
        'reports.view_marketing', 'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Marketing Managers': [
        'marketing.view_campaigns', 'marketing.create_campaign', 'marketing.update_campaign', 'marketing.archive_campaign',
        'marketing.manage_assets', 'marketing.manage_budget', 'marketing.submit_approval', 'marketing.view_roi',
        'marketing.manage_campaign_types', 'marketing.manage_attribution', 'integrations.view', 'integrations.manage_meta_connection',
        'integrations.manage_field_mapping', 'integrations.view_webhook_logs', 'integrations.reprocess_payload',
        'leads.view_all', 'leads.export', 'reports.view_marketing', 'reports.export', 'audit.view_object_timeline',
        'notifications.view_own', 'notifications.manage_preferences',
    ],
    'Finance Managers': [
        'marketing.view_campaigns', 'marketing.view_roi', 'finance.view_budgets', 'finance.approve_campaign',
        'finance.view_approval_history', 'finance.export_finance_reports', 'reports.view_finance', 'reports.export',
        'audit.view_object_timeline', 'notifications.view_own', 'notifications.manage_preferences',
    ],
}

NOTIFICATION_TYPES = [
    ('lead_assigned', 'Lead Assigned', 'lead', ['in_app'], 'info'),
    ('lead_reassigned', 'Lead Reassigned', 'lead', ['in_app'], 'warning'),
    ('lead_stage_changed', 'Lead Stage Changed', 'lead', ['in_app'], 'info'),
    ('sla_warning', 'SLA Warning', 'sla', ['in_app', 'email'], 'warning'),
    ('sla_expired_manual_required', 'SLA Expired Manual Required', 'sla', ['in_app', 'email'], 'critical'),
    ('sla_redistributed', 'SLA Redistributed', 'sla', ['in_app'], 'warning'),
    ('followup_due', 'Follow-up Due', 'reminder', ['in_app', 'email'], 'warning'),
    ('meeting_due', 'Meeting Due', 'reminder', ['in_app', 'email'], 'warning'),
    ('frozen_end', 'Frozen Period Ended', 'reminder', ['in_app'], 'info'),
    ('campaign_created', 'Campaign Created', 'campaign', ['in_app'], 'info'),
    ('campaign_budget_changed', 'Campaign Budget Changed', 'campaign', ['in_app'], 'warning'),
    ('campaign_pending_approval', 'Campaign Pending Approval', 'finance', ['in_app', 'email'], 'warning'),
    ('campaign_approved', 'Campaign Approved', 'finance', ['in_app', 'email'], 'success'),
    ('campaign_rejected', 'Campaign Rejected', 'finance', ['in_app', 'email'], 'critical'),
    ('webhook_payload_failed', 'Webhook Payload Failed', 'integration', ['in_app', 'email'], 'critical'),
    ('webhook_mapping_missing', 'Webhook Mapping Missing', 'integration', ['in_app', 'email'], 'critical'),
    ('permission_changed', 'Permission Changed', 'permission', ['in_app'], 'warning'),
    ('policy_changed', 'Policy Changed', 'system', ['in_app'], 'warning'),
]


class Command(BaseCommand):
    help = 'Seed Argoz CRM permissions, groups, policies, sources, stages, and notification types.'

    def add_arguments(self, parser):
        parser.add_argument('--company', default='Argoz Demo Company')
        parser.add_argument('--admin-email', default='admin@argoz.local')
        parser.add_argument('--admin-password', default='Admin@12345')

    def handle(self, *args, **options):
        company, _ = Company.objects.get_or_create(
            slug='argoz-demo',
            defaults={'name': options['company'], 'legal_name': options['company']},
        )
        self.seed_permissions_and_groups()
        self.seed_company_defaults(company)
        self.seed_admin(company, options['admin_email'], options['admin_password'])
        self.stdout.write(self.style.SUCCESS('CRM defaults seeded successfully.'))

    def seed_permissions_and_groups(self):
        perm_objs = {}
        for full_code in ALL_CODES:
            app_label, codename = full_code.split('.', 1)
            ct, _ = ContentType.objects.get_or_create(app_label=app_label, model='crmpermission')
            perm, _ = Permission.objects.get_or_create(content_type=ct, codename=codename, defaults={'name': full_code.replace('_', ' ').title()})
            perm_objs[full_code] = perm
        for group_name, codes in GROUPS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.set([perm_objs[c] for c in codes if c in perm_objs])
            template, _ = CRMGroupTemplate.objects.get_or_create(code=group_name.lower().replace(' ', '_'), company=None, defaults={'name': group_name, 'is_system_default': True})
            for c in codes:
                CRMGroupTemplatePermission.objects.get_or_create(group_template=template, permission_codename=c, defaults={'is_allowed': True})

    def seed_company_defaults(self, company):
        for code, name, default in [('ar', 'Arabic', True), ('en', 'English', False)]:
            Language.objects.get_or_create(company=company, code=code, defaults={'name': name, 'is_default': default})
        sources = [
            ('self_generated', 'Self Generated', False), ('campaign', 'Campaign', False), ('broker', 'Broker', False),
            ('walkin', 'Walk-in', True), ('call_center', 'Call Center', True), ('exhibition', 'Exhibition', False),
            ('referral', 'Referral', False), ('existing_client', 'Existing Client', False),
        ]
        for code, name, requires in sources:
            LeadSource.objects.get_or_create(company=company, code=code, defaults={'name': name, 'requires_how_did_you_know': requires, 'distribution_allowed': {'manual': True, 'automatic': True}})
        stages = [
            ('fresh', 'Fresh', True, False, 1), ('interested', 'Interested', True, False, 2),
            ('not_interested', 'Not Interested', False, True, 3), ('followup', 'Follow-up', True, False, 4),
            ('meeting', 'Meeting', True, False, 5), ('not_reached', 'Not Reached', True, False, 6),
            ('frozen', 'Frozen', True, False, 7),
        ]
        for code, name, active, terminal, order in stages:
            LeadStage.objects.get_or_create(company=company, code=code, defaults={'name': name, 'is_active_stage': active, 'is_terminal': terminal, 'sort_order': order})
        for code, name, cls in [
            ('round_robin_load_balanced', 'Round Robin Load Balanced', 'apps.distribution.strategies.RoundRobinLoadBalancedStrategy'),
            ('by_turn', 'By Turn Sequential', 'apps.distribution.strategies.ByTurnSequentialStrategy'),
            ('retry_team_escalation', 'Retry Attempts and Team Escalation', 'apps.distribution.strategies.RetryTeamEscalationStrategy'),
            ('manual_assignment', 'Manual Assignment', 'apps.distribution.strategies.ManualAssignmentStrategy'),
        ]:
            DistributionStrategyDefinition.objects.get_or_create(code=code, defaults={'name': name, 'class_path': cls})
        for code, name in [('meta_ads', 'Meta Ads'), ('make', 'Make'), ('zapier', 'Zapier'), ('native_future', 'Native Future')]:
            IntegrationProvider.objects.get_or_create(code=code, defaults={'name': name})
        for code, name, category, channels, severity in NOTIFICATION_TYPES:
            NotificationType.objects.get_or_create(code=code, defaults={'name': name, 'category': category, 'default_channels': channels, 'severity': severity})
        self.seed_policies(company)

    def seed_policies(self, company):
        policy_specs = {
            'lead_auto_distribution_strategy': ('distribution', 'Lead automatic distribution strategy', ['round_robin_load_balanced', 'by_turn', 'retry_team_escalation']),
            'lead_distribution_scope_mode': ('distribution', 'Lead distribution scope mode', ['team_then_salesman', 'team_then_sales_head', 'all_salesmen']),
            'sla_expiry_method': ('sla', 'SLA expiry method', ['round_robin_load_balanced', 'retry_team_escalation']),
            'walkin_reception_policy': ('leads', 'Walk-in reception policy', ['open_floor', 'team_turn', 'full_rotation']),
            'existing_client_policy': ('leads', 'Existing client preservation policy', ['preserve_original_salesman', 'redistribute_directly']),
            'meta_connector_mode': ('integrations', 'Meta connector mode', ['make_dynamic_webhook', 'zapier_dynamic_webhook', 'native_future']),
        }
        for code, (module, name, options) in policy_specs.items():
            definition, _ = PolicyDefinition.objects.get_or_create(code=code, defaults={'module': module, 'name': name, 'data_type': 'choice'})
            selected = None
            for i, opt in enumerate(options):
                option, _ = PolicyOption.objects.get_or_create(policy_definition=definition, code=opt, defaults={'label': opt.replace('_', ' ').title(), 'value': {'code': opt}, 'sort_order': i})
                if selected is None:
                    selected = option
            CompanyPolicy.objects.get_or_create(company=company, policy_definition=definition, is_active=True, defaults={'selected_option': selected, 'value': {}})

    def seed_admin(self, company, email, password):
        user, created = User.objects.get_or_create(email=email, defaults={'username': email, 'company': company, 'is_staff': True, 'is_superuser': True})
        if created:
            user.set_password(password)
            user.save()
        UserProfile.objects.get_or_create(user=user, defaults={'display_name': 'System Administrator', 'job_title': 'System Admin'})
