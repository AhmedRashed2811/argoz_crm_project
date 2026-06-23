from django.test import TestCase
from apps.companies.models import Company
from apps.accounts.models import User, Team, TeamMembership, SalesProfile
from apps.leads.models import Lead, LeadSource, LeadStage
from apps.leads.services.leads import LeadService

class LeadWorkflowsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.source = LeadSource.objects.create(company=self.company, code='self_generated', name='Self Generated')
        self.stage = LeadStage.objects.create(company=self.company, code='fresh', name='Fresh')
        self.sales = User.objects.create(email='s1@test.com', company=self.company)
        self.sp = SalesProfile.objects.create(user=self.sales, company=self.company, is_available=True)

    def test_duplicate_lead_reactivation(self):
        # Create lead and set to inactive
        lead, created = LeadService.create_lead(
            company=self.company,
            full_name='Test Lead',
            phone_country_code='+20',
            phone_number='123456789',
            source=self.source,
            current_stage=self.stage,
        )
        self.assertTrue(created)
        
        lead.status = Lead.STATUS_INACTIVE
        lead.save()
        
        # Submit duplicate lead, it should reactivate and return created=True
        lead2, reactivated = LeadService.create_lead(
            company=self.company,
            full_name='Test Lead Duplicate',
            phone_country_code='+20',
            phone_number='123456789',
            source=self.source,
            current_stage=self.stage,
        )
        self.assertTrue(reactivated)
        self.assertEqual(lead2.status, Lead.STATUS_ACTIVE)

    def test_call_me_again_escalation(self):
        # Create lead and assign it
        lead, created = LeadService.create_lead(
            company=self.company,
            full_name='Test Lead',
            phone_country_code='+20',
            phone_number='987654321',
            source=self.source,
            current_stage=self.stage,
        )
        LeadService.assign_lead(lead=lead, strategy_code='manual_assignment', salesman=self.sales)
        
        # Resubmit lead while active (triggers Call Me Again)
        lead2, created2 = LeadService.create_lead(
            company=self.company,
            full_name='Test Lead',
            phone_country_code='+20',
            phone_number='987654321',
            source=self.source,
            current_stage=self.stage,
        )
        self.assertFalse(created2)
