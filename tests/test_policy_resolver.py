from django.test import TestCase
from apps.companies.models import Company
from apps.core.models import PolicyDefinition, PolicyOption, CompanyPolicy
from apps.core.services.policies import PolicyResolver

class PolicyResolverTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.defn = PolicyDefinition.objects.create(code='lead_auto_distribution_strategy', module='distribution', name='Strategy')
        self.opt1 = PolicyOption.objects.create(policy_definition=self.defn, code='round_robin_load_balanced', label='RR', value={'code': 'round_robin_load_balanced'})
        self.opt2 = PolicyOption.objects.create(policy_definition=self.defn, code='by_turn', label='By Turn', value={'code': 'by_turn'})

    def test_default_policy(self):
        val = PolicyResolver.get(self.company, 'lead_auto_distribution_strategy', default='round_robin_load_balanced')
        self.assertEqual(val, 'round_robin_load_balanced')

    def test_company_policy_override(self):
        CompanyPolicy.objects.create(
            company=self.company,
            policy_definition=self.defn,
            selected_option=self.opt2,
            is_active=True
        )
        val = PolicyResolver.get_code(self.company, 'lead_auto_distribution_strategy')
        self.assertEqual(val, 'by_turn')
