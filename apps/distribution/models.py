from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class DistributionStrategyDefinition(UUIDBaseModel):
    code = models.SlugField(unique=True, max_length=100)
    class_path = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        permissions = [
            ('view_queue', 'Can view distribution queue'),
            ('run_manual', 'Can run manual distribution'),
            ('manage_strategies', 'Can manage distribution strategies'),
            ('view_logs', 'Can view distribution logs'),
        ]

    def __str__(self):
        return self.name


class RotationPointer(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='rotation_pointers')
    strategy_code = models.CharField(max_length=100)
    scope_mode = models.CharField(max_length=60, default='all_salesmen')
    team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.CASCADE, related_name='rotation_pointers')
    last_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='rotation_pointer_last_user')
    last_team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='rotation_pointer_last_team')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('company', 'strategy_code', 'scope_mode', 'team')]
        indexes = [models.Index(fields=['company', 'strategy_code', 'scope_mode'])]


class AssignmentAttempt(UUIDBaseModel):
    STATUS_CHOICES = [('active', 'Active'), ('successful', 'Successful'), ('expired', 'Expired'), ('skipped', 'Skipped')]
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='assignment_attempts')
    team = models.ForeignKey('accounts.Team', on_delete=models.CASCADE, related_name='assignment_attempts')
    salesman = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assignment_attempts')
    attempt_no = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    sla_instance = models.ForeignKey('sla.LeadSLAInstance', null=True, blank=True, on_delete=models.SET_NULL, related_name='assignment_attempts')

    class Meta:
        ordering = ['lead', 'attempt_no']
