from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class SLADefinition(UUIDBaseModel):
    UNIT_CHOICES = [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')]
    BREACH_CHOICES = [('manual_reassignment', 'Manual Reassignment'), ('automatic_redistribution', 'Automatic Redistribution')]
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='sla_definitions')
    source = models.ForeignKey('leads.LeadSource', null=True, blank=True, on_delete=models.CASCADE, related_name='sla_definitions')
    origin = models.CharField(max_length=20, blank=True)
    stage = models.ForeignKey('leads.LeadStage', null=True, blank=True, on_delete=models.CASCADE, related_name='sla_definitions')
    duration_value = models.PositiveIntegerField(default=1)
    duration_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='hours')
    breach_action = models.CharField(max_length=40, choices=BREACH_CHOICES, default='automatic_redistribution')
    expiry_strategy_code = models.CharField(max_length=100, default='round_robin_load_balanced')
    reminder_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['company', 'source', 'stage']
        permissions = [
            ('view_dashboard', 'Can view SLA dashboard'),
            ('manage_policies', 'Can manage SLA policies'),
            ('process_expired_manual', 'Can process expired SLA manually'),
        ]

    def __str__(self):
        return f'{self.company} SLA {self.duration_value} {self.duration_unit}'


class LeadSLAInstance(UUIDBaseModel):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('satisfied', 'Satisfied'),
        ('expired', 'Expired'),
        ('processed', 'Processed'),
        ('cancelled', 'Cancelled'),
    ]
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='sla_instances')
    assignment = models.ForeignKey('leads.LeadAssignment', null=True, blank=True, on_delete=models.SET_NULL, related_name='sla_instances')
    stage = models.ForeignKey('leads.LeadStage', on_delete=models.PROTECT, related_name='sla_instances')
    starts_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    expired_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['due_at']
        indexes = [models.Index(fields=['status', 'due_at'])]

    def __str__(self):
        return f'{self.lead} SLA due {self.due_at}'
