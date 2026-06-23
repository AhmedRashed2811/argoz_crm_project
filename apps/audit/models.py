from django.conf import settings
from django.db import models
from apps.core.models import UUIDBaseModel


class AuditLog(UUIDBaseModel):
    ACTOR_USER = 'user'
    ACTOR_SYSTEM = 'system'
    ACTOR_WEBHOOK = 'webhook'
    ACTOR_SCHEDULER = 'scheduler'
    ACTOR_CHOICES = [
        (ACTOR_USER, 'User'),
        (ACTOR_SYSTEM, 'System'),
        (ACTOR_WEBHOOK, 'Webhook'),
        (ACTOR_SCHEDULER, 'Scheduler'),
    ]

    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_actor_users')
    actor_type = models.CharField(max_length=20, choices=ACTOR_CHOICES, default=ACTOR_USER)
    action = models.CharField(max_length=150, db_index=True)
    object_type = models.CharField(max_length=150, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    app_label = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    changes_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', 'action', 'created_at'])]
        permissions = [
            ('view_all_logs', 'Can view all audit logs'),
            ('view_object_timeline', 'Can view object audit timeline'),
            ('export_logs', 'Can export audit logs'),
        ]

    def __str__(self):
        return f'{self.action} on {self.object_type}:{self.object_id}'
