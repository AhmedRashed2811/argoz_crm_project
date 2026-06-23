from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class NotificationType(UUIDBaseModel):
    CATEGORY_CHOICES = [
        ('lead', 'Lead'),
        ('sla', 'SLA'),
        ('reminder', 'Reminder'),
        ('campaign', 'Campaign'),
        ('finance', 'Finance'),
        ('integration', 'Integration'),
        ('system', 'System'),
        ('permission', 'Permission'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    code = models.SlugField(unique=True, max_length=120)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    default_channels = models.JSONField(default=list, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'code']

    def __str__(self):
        return self.name


class Notification(UUIDBaseModel):
    STATUS_UNREAD = 'unread'
    STATUS_READ = 'read'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [(STATUS_UNREAD, 'Unread'), (STATUS_READ, 'Read'), (STATUS_ARCHIVED, 'Archived')]

    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications')
    type = models.ForeignKey(NotificationType, on_delete=models.PROTECT, related_name='notifications')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_object_type = models.CharField(max_length=150, blank=True)
    related_object_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNREAD)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'status', 'created_at'])]
        permissions = [
            ('view_own', 'Can view own notifications'),
            ('manage_preferences', 'Can manage notification preferences'),
            ('broadcast', 'Can broadcast notifications'),
        ]

    def mark_read(self):
        self.status = self.STATUS_READ
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])


class NotificationDelivery(UUIDBaseModel):
    CHANNEL_CHOICES = [('in_app', 'In App'), ('email', 'Email'), ('realtime_ws', 'Realtime WebSocket')]
    STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('skipped', 'Skipped')]
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)


class EmailOutbox(UUIDBaseModel):
    STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('cancelled', 'Cancelled')]
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='email_outbox')
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    template_name = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    retry_count = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_at']
        indexes = [models.Index(fields=['status', 'scheduled_at'])]


class NotificationPreference(UUIDBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE, related_name='preferences')
    channel = models.CharField(max_length=30, choices=NotificationDelivery.CHANNEL_CHOICES)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [('user', 'notification_type', 'channel')]


class Reminder(UUIDBaseModel):
    STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('dismissed', 'Dismissed'), ('cancelled', 'Cancelled')]
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='reminders')
    lead = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.CASCADE, related_name='reminders')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=60)
    title = models.CharField(max_length=255)
    message = models.TextField()
    due_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        ordering = ['due_at']
        indexes = [models.Index(fields=['status', 'due_at'])]
