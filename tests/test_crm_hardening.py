from django.test import TestCase, Client
from django.utils import timezone
from decimal import Decimal
from apps.companies.models import Company, Branch, Language
from apps.accounts.models import User, SalesProfile, Team
from apps.leads.models import Lead, LeadSource, LeadStage
from apps.audit.models import AuditLog
from apps.integrations.models import CompanyIntegration, IncomingWebhookPayload, TenantWebhookEndpoint
from apps.permissions_engine.models import UserPermissionOverride
from apps.sla.models import SLADefinition, LeadSLAInstance
from apps.sla.services.sla import SLAService
from apps.distribution.models import ManualDistributionRequest, AssignmentAttempt
from apps.marketing.models import Campaign, CampaignEvent, SocialMediaAd, SocialMediaPlatformLine, CampaignKPIResult
from apps.marketing.services.roi_service import ROIService
from apps.marketing.services.campaigns import CampaignValidationService
from apps.notifications.models import EmailOutbox, Reminder
from django.urls import reverse


class CRMHardeningTestCase(TestCase):
    def setUp(self):
        # Create Companies
        self.company_a = Company.objects.create(name='Company A', slug='company-a')
        self.company_b = Company.objects.create(name='Company B', slug='company-b')

        # Create Users
        self.user_a = User.objects.create_user(username='usera', email='usera@company-a.com', password='password123', company=self.company_a, is_staff=True)
        self.user_b = User.objects.create_user(username='userb', email='userb@company-b.com', password='password123', company=self.company_b, is_staff=True)
        
        self.superuser = User.objects.create_superuser(username='super', email='super@crm.com', password='password123')

        # Create Lead Sources & Stages
        self.source_a = LeadSource.objects.create(company=self.company_a, code='campaign', name='Campaign Source')
        self.stage_a = LeadStage.objects.create(company=self.company_a, code='fresh', name='Fresh Stage')

        # Setup Clients
        self.client_a = Client()
        self.client_a.login(email='usera@company-a.com', password='password123')

        self.client_b = Client()
        self.client_b.login(email='userb@company-b.com', password='password123')

        self.client_super = Client()
        self.client_super.login(email='super@crm.com', password='password123')

    def grant_perm(self, user, codename):
        UserPermissionOverride.objects.create(user=user, permission_codename=codename, is_allowed=True)

    def test_audit_log_view_company_scoping(self):
        # Create audit logs for A and B
        log_a = AuditLog.objects.create(company=self.company_a, action='test.action.a', object_type='Lead', object_id='1')
        log_b = AuditLog.objects.create(company=self.company_b, action='test.action.b', object_type='Lead', object_id='2')

        self.grant_perm(self.user_a, 'audit.view_audit_log')

        # Query via User A
        response = self.client_a.get(reverse('audit:list'))
        self.assertEqual(response.status_code, 200)
        logs = list(response.context['logs'])
        self.assertIn(log_a, logs)
        self.assertNotIn(log_b, logs)

    def test_integrations_company_scoping(self):
        self.grant_perm(self.user_a, 'integrations.manage_meta_connection')
        from apps.integrations.models import IntegrationProvider
        provider = IntegrationProvider.objects.create(code='meta', name='Meta')
        integration_a = CompanyIntegration.objects.create(company=self.company_a, provider=provider, status='active')
        integration_b = CompanyIntegration.objects.create(company=self.company_b, provider=provider, status='active')

        response = self.client_a.get(reverse('integrations:list'))
        self.assertEqual(response.status_code, 200)
        integrations = list(response.context['integrations'])
        self.assertIn(integration_a, integrations)
        self.assertNotIn(integration_b, integrations)

    def test_notification_outbox_company_scoping(self):
        # Email outboxes
        outbox_a = EmailOutbox.objects.create(company=self.company_a, to_email='a@test.com', subject='A')
        outbox_b = EmailOutbox.objects.create(company=self.company_b, to_email='b@test.com', subject='B')

        # Reminders
        reminder_a = Reminder.objects.create(company=self.company_a, recipient=self.user_a, reminder_type='generic', title='Rem A', message='A', due_at=timezone.now())
        reminder_b = Reminder.objects.create(company=self.company_b, recipient=self.user_b, reminder_type='generic', title='Rem B', message='B', due_at=timezone.now())

        response = self.client_a.get(reverse('notifications:list'))
        self.assertEqual(response.status_code, 200)
        
        reminders = list(response.context['reminders'])
        self.assertIn(reminder_a, reminders)
        self.assertNotIn(reminder_b, reminders)

        outbox = list(response.context['outbox'])
        self.assertIn(outbox_a, outbox)
        self.assertNotIn(outbox_b, outbox)

    def test_sla_dynamic_fallback(self):
        # Delete any seeded/default SLA definitions
        SLADefinition.objects.all().delete()
        
        # No SLADefinition seeded. Call start_for_lead
        lead = Lead.objects.create(company=self.company_a, full_name='Hardened Lead', phone_number='010', normalized_phone='010', source=self.source_a, current_stage=self.stage_a)
        
        # Starts SLA utilizing policy fallbacks
        instance = SLAService.start_for_lead(lead)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.status, 'active')
        self.assertEqual(instance.policy_snapshot.get('definition_id'), 'fallback')
        self.assertEqual(instance.policy_snapshot.get('duration_value'), 1)
        self.assertEqual(instance.policy_snapshot.get('duration_unit'), 'hours')

    def test_sla_expiry_manual_distribution_request(self):
        lead = Lead.objects.create(company=self.company_a, full_name='Manual Reassign Lead', phone_number='011', normalized_phone='011', source=self.source_a, current_stage=self.stage_a, origin='broker')
        
        # Seed definition with manual_reassignment action
        sla_def = SLADefinition.objects.create(
            company=self.company_a,
            stage=self.stage_a,
            duration_value=30,
            duration_unit='minutes',
            breach_action='manual_reassignment',
            expiry_strategy_code='manual_assignment'
        )
        
        instance = SLAService.start_for_lead(lead)
        instance.due_at = timezone.now() - timezone.timedelta(minutes=5)
        instance.save()
        
        count = SLAService.process_expired_slas()
        self.assertEqual(count, 1)
        
        # Assert ManualDistributionRequest was created
        reqs = ManualDistributionRequest.objects.filter(lead=lead, status='pending')
        self.assertEqual(reqs.count(), 1)
        self.assertEqual(reqs.first().company, self.company_a)

    def test_manual_distribution_views(self):
        self.grant_perm(self.user_a, 'distribution.run_manual_distribution')
        self.grant_perm(self.user_b, 'distribution.run_manual_distribution')
        lead = Lead.objects.create(company=self.company_a, full_name='Queue Lead', phone_number='012', normalized_phone='012', source=self.source_a, current_stage=self.stage_a)
        
        req = ManualDistributionRequest.objects.create(
            company=self.company_a,
            lead=lead,
            status='pending'
        )
        
        # Check list queue
        response = self.client_a.get(reverse('distribution:list'))
        self.assertEqual(response.status_code, 200)
        requests = list(response.context['requests'])
        self.assertIn(req, requests)

        # Check detail queue
        response = self.client_a.get(reverse('distribution:detail', kwargs={'pk': req.pk}))
        self.assertEqual(response.status_code, 200)

        # Try to access from Company B (should be 404)
        response_b = self.client_b.get(reverse('distribution:detail', kwargs={'pk': req.pk}))
        self.assertEqual(response_b.status_code, 404)

    def test_campaign_assets_validation(self):
        campaign = Campaign.objects.create(company=self.company_a, name='Campaign 1', start_date='2026-06-01', end_date='2026-08-31')
        event_other = CampaignEvent.objects.create(campaign=campaign, event_name='Gala A', venue_place='HQ', event_date='2026-06-15')
        
        campaign_other = Campaign.objects.create(company=self.company_a, name='Campaign 2', start_date='2026-06-01', end_date='2026-08-31')
        event_b = CampaignEvent.objects.create(campaign=campaign_other, event_name='Gala B', venue_place='HQ', event_date='2026-06-15')
        
        # Social media ad in Campaign 1 linked to event of Campaign 2
        ad = SocialMediaAd.objects.create(campaign=campaign, name='FB Ad', linked_event=event_b)
        
        with self.assertRaises(ValueError):
            CampaignValidationService.validate_assets(campaign)

    def test_campaign_kpi_target_and_actuals(self):
        campaign = Campaign.objects.create(company=self.company_a, name='KPI Campaign', start_date='2026-06-01', end_date='2026-08-31')
        
        # Event with target and actual attendees
        CampaignEvent.objects.create(
            campaign=campaign,
            event_name='KPI Gala',
            venue_place='HQ',
            event_date='2026-06-15',
            budget=Decimal('100.00'),
            target_attendees=200,
            actual_attendees=150
        )
        
        ROIService.calculate_event_roi(campaign)
        
        kpi_target = CampaignKPIResult.objects.get(campaign=campaign, metric_code='kpi_target')
        kpi_actual = CampaignKPIResult.objects.get(campaign=campaign, metric_code='kpi_actual')
        kpi_achievement = CampaignKPIResult.objects.get(campaign=campaign, metric_code='kpi_achievement_pct')
        
        self.assertEqual(kpi_target.metric_value, Decimal('200.00'))
        self.assertEqual(kpi_actual.metric_value, Decimal('150.00'))
        self.assertEqual(kpi_achievement.metric_value, Decimal('75.00'))

    def test_campaign_create_cross_company_prevention(self):
        self.grant_perm(self.user_a, 'marketing.create_campaign')
        
        # User A tries to create a campaign and post company_id of Company B
        post_data = {
            'company': str(self.company_b.pk),
            'name': 'Hack Campaign',
            'description': 'Hacking cross company creation',
            'start_date': '2026-06-01',
            'end_date': '2026-08-31',
            'target_type': 'other'
        }
        
        response = self.client_a.post(reverse('marketing:campaign_create'), post_data)
        # Should result in form error message and not create Campaign B
        self.assertFalse(Campaign.objects.filter(name='Hack Campaign').exists())
