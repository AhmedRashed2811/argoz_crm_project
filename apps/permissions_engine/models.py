from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class CRMGroupTemplate(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='crm_group_templates')
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=120)
    description = models.TextField(blank=True)
    is_system_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'code')]
        permissions = [
            ('view_matrix', 'Can view permission matrix'),
            ('manage_group_templates', 'Can manage group templates'),
            ('manage_user_permissions', 'Can manage user permissions'),
        ]

    def __str__(self):
        return self.name


class CRMGroupTemplatePermission(UUIDBaseModel):
    group_template = models.ForeignKey(CRMGroupTemplate, on_delete=models.CASCADE, related_name='template_permissions')
    permission_codename = models.CharField(max_length=150)
    is_allowed = models.BooleanField(default=True)

    class Meta:
        unique_together = [('group_template', 'permission_codename')]
        ordering = ['group_template__name', 'permission_codename']

    def __str__(self):
        return f'{self.group_template}: {self.permission_codename}'


class UserPermissionOverride(UUIDBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='crm_permission_overrides')
    permission_codename = models.CharField(max_length=150)
    is_allowed = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='changed_permission_overrides')
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('user', 'permission_codename')]
        ordering = ['user__email', 'permission_codename']

    def __str__(self):
        state = 'allow' if self.is_allowed else 'deny'
        return f'{self.user} {state} {self.permission_codename}'


class PermissionChangeLog(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='permission_logs')
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='permission_change_logs')
    permission_codename = models.CharField(max_length=150)
    old_value = models.BooleanField(null=True, blank=True)
    new_value = models.BooleanField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='performed_permission_changes')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
