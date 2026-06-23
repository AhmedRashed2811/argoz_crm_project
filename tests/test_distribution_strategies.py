from django.test import TestCase
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User, Team, TeamMembership, SalesProfile
from apps.leads.models import Lead, LeadSource, LeadStage, LeadAssignment
from apps.distribution.models import RotationPointer, DistributionStrategyDefinition, AssignmentAttempt
from apps.distribution.services.distribution import DistributionService

class DistributionStrategiesTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.source = LeadSource.objects.create(company=self.company, code='campaign', name='Campaign')
        self.stage = LeadStage.objects.create(company=self.company, code='fresh', name='Fresh')
        
        self.team1 = Team.objects.create(company=self.company, code='team-1', name='Team 1')
        self.team2 = Team.objects.create(company=self.company, code='team-2', name='Team 2')
        
        self.sales1 = User.objects.create(email='s1@test.com', company=self.company)
        self.sales2 = User.objects.create(email='s2@test.com', company=self.company)
        
        TeamMembership.objects.create(team=self.team1, user=self.sales1, role='salesman')
        TeamMembership.objects.create(team=self.team1, user=self.sales2, role='salesman')
        
        self.sp1 = SalesProfile.objects.create(user=self.sales1, company=self.company, active_lead_count_cache=0, last_received_lead_at=timezone.now())
        self.sp2 = SalesProfile.objects.create(user=self.sales2, company=self.company, active_lead_count_cache=0, last_received_lead_at=timezone.now() - timezone.timedelta(hours=1))

    def test_round_robin_workload(self):
        # sp2 has the older last_received_lead_at, so sp2 should receive first
        lead = Lead.objects.create(company=self.company, full_name='L1', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        result = DistributionService.assign(lead=lead, strategy_code='round_robin_load_balanced', scope_mode='all_salesmen')
        self.assertEqual(result.salesman, self.sales2)

    def test_by_turn_sequential(self):
        lead1 = Lead.objects.create(company=self.company, full_name='L1', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        result1 = DistributionService.assign(lead=lead1, strategy_code='by_turn', scope_mode='all_salesmen')
        
        lead2 = Lead.objects.create(company=self.company, full_name='L2', phone_number='987654321', normalized_phone='987654321', source=self.source, current_stage=self.stage)
        result2 = DistributionService.assign(lead=lead2, strategy_code='by_turn', scope_mode='all_salesmen')
        
        self.assertNotEqual(result1.salesman, result2.salesman)

    def test_retry_attempts_and_team_escalation(self):
        lead = Lead.objects.create(company=self.company, full_name='L1', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        
        # Initial routing (Attempt 1)
        res1 = DistributionService.assign(lead=lead, strategy_code='retry_team_escalation', team=self.team1)
        self.assertEqual(res1.team, self.team1)
        
        # Force expiration of first attempt and check redistribution (Attempt 2)
        res2 = DistributionService.assign(lead=lead, strategy_code='retry_team_escalation', team=self.team1)
        self.assertEqual(res2.team, self.team1)
        self.assertNotEqual(res1.salesman, res2.salesman)
        
        # Verify attempt numbers
        attempts = list(lead.assignment_attempts.all().order_by('attempt_no'))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].attempt_no, 1)
        self.assertEqual(attempts[1].attempt_no, 2)
        self.assertGreater(attempts[1].due_at, timezone.now())
