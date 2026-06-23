from django.test import TestCase
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User, SalesProfile
from apps.leads.models import Lead, LeadSource, LeadStage
from apps.sla.models import SLADefinition, LeadSLAInstance
from apps.sla.services.sla import SLAService
from apps.leads.services.leads import LeadService

class SLAExpiryTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.source = LeadSource.objects.create(company=self.company, code='self_generated', name='Self Generated')
        self.stage = LeadStage.objects.create(company=self.company, code='fresh', name='Fresh')
        self.sales = User.objects.create(email='s1@test.com', company=self.company)
        self.sp = SalesProfile.objects.create(user=self.sales, company=self.company, is_available=True, active_lead_count_cache=1, last_received_lead_at=timezone.now())
        
        self.sales2 = User.objects.create(email='s2@test.com', company=self.company)
        self.sp2 = SalesProfile.objects.create(user=self.sales2, company=self.company, is_available=True, active_lead_count_cache=0, last_received_lead_at=timezone.now() - timezone.timedelta(hours=1))

        self.sla_def = SLADefinition.objects.create(
            company=self.company,
            stage=self.stage,
            duration_value=1,
            duration_unit='minutes',
            breach_action='automatic_redistribution',
            expiry_strategy_code='round_robin_load_balanced'
        )

    def test_sla_lifecycle(self):
        lead = Lead.objects.create(company=self.company, full_name='Test Lead', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        
        # Start SLA
        instance = SLAService.start_for_lead(lead)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.status, 'active')
        
        # Cancel SLA
        SLAService.close_sla(instance, reason='satisfied')
        self.assertEqual(instance.status, 'satisfied')

    def test_sla_expiry_processing(self):
        lead = Lead.objects.create(company=self.company, full_name='Test Lead', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        lead.current_salesman = self.sales
        lead.save()
        
        instance = SLAService.start_for_lead(lead)
        # Force expiration
        instance.due_at = timezone.now() - timezone.timedelta(minutes=5)
        instance.save()
        
        # Process expired SLA
        count = SLAService.process_expired_slas()
        self.assertEqual(count, 1)
        
        instance.refresh_from_db()
        self.assertEqual(instance.status, 'processed')
        
        # Lead should be rotated (assigned to sales2 since workload is load balanced)
        lead.refresh_from_db()
        self.assertEqual(lead.current_salesman, self.sales2)
        self.assertEqual(lead.current_stage.code, 'fresh')
