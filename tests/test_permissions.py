from django.test import TestCase
from apps.companies.models import Company
from apps.accounts.models import User, UserProfile
from apps.permissions_engine.models import CRMGroupTemplate, CRMGroupTemplatePermission, UserPermissionOverride
from apps.permissions_engine.services.engine import PermissionEngine

class PermissionsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.user = User.objects.create(email='test@test.com', company=self.company)
        self.profile = UserProfile.objects.create(user=self.user)
        self.template = CRMGroupTemplate.objects.create(company=self.company, code='sales', name='Sales')
        self.profile.default_group_template = self.template
        self.profile.save()

    def test_template_permission(self):
        # Set template permission
        CRMGroupTemplatePermission.objects.create(
            group_template=self.template,
            permission_codename='leads.view_lead',
            is_allowed=True
        )
        self.assertTrue(PermissionEngine.has_perm(self.user, 'leads.view_lead'))
        self.assertFalse(PermissionEngine.has_perm(self.user, 'leads.create_lead'))

    def test_permission_override(self):
        # Default is False
        self.assertFalse(PermissionEngine.has_perm(self.user, 'leads.view_lead'))
        
        # Override to True
        UserPermissionOverride.objects.create(
            user=self.user,
            permission_codename='leads.view_lead',
            is_allowed=True
        )
        self.assertTrue(PermissionEngine.has_perm(self.user, 'leads.view_lead'))
        
        # Override to False
        override = UserPermissionOverride.objects.get(user=self.user, permission_codename='leads.view_lead')
        override.is_allowed = False
        override.save()
        self.assertFalse(PermissionEngine.has_perm(self.user, 'leads.view_lead'))
