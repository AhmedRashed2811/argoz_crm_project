from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class LeadSource(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='lead_sources')
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    requires_how_did_you_know = models.BooleanField(default=False)
    distribution_allowed = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'code')]
        permissions = [('manage_sources', 'Can manage lead sources')]

    def __str__(self):
        return self.name


class HowDidYouKnowOption(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='how_did_you_know_options')
    name = models.CharField(max_length=150)
    source = models.ForeignKey(LeadSource, null=True, blank=True, on_delete=models.SET_NULL, related_name='how_options')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class LeadStage(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.CASCADE, related_name='lead_stages')
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    is_active_stage = models.BooleanField(default=True)
    is_terminal = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = [('company', 'code')]

    def __str__(self):
        return self.name


class Lead(UUIDBaseModel):
    ORIGIN_DIRECT = 'direct'
    ORIGIN_BROKER = 'broker'
    ORIGIN_CHOICES = [(ORIGIN_DIRECT, 'Direct'), (ORIGIN_BROKER, 'Broker')]
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [(STATUS_ACTIVE, 'Active'), (STATUS_INACTIVE, 'Inactive'), (STATUS_ARCHIVED, 'Archived')]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='leads')
    full_name = models.CharField(max_length=255)
    phone_country_code = models.CharField(max_length=10, default='+20')
    phone_number = models.CharField(max_length=30)
    normalized_phone = models.CharField(max_length=40, db_index=True)
    email = models.EmailField(blank=True)
    source = models.ForeignKey(LeadSource, on_delete=models.PROTECT, related_name='leads')
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_DIRECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    current_stage = models.ForeignKey(LeadStage, null=True, blank=True, on_delete=models.SET_NULL, related_name='current_leads')
    current_team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='current_leads')
    current_salesman = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='current_leads')
    broker = models.ForeignKey('accounts.BrokerProfile', null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
    language = models.ForeignKey('companies.Language', null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
    campaign = models.ForeignKey('marketing.Campaign', null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
    how_did_you_know = models.ForeignKey(HowDidYouKnowOption, null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('company', 'normalized_phone')]
        permissions = [
            ('view_own', 'Can view own leads'),
            ('view_team', 'Can view team leads'),
            ('view_all', 'Can view all leads'),
            ('import_leads', 'Can import leads'),
            ('export_leads', 'Can export leads'),
            ('change_stage', 'Can change lead stage'),
            ('create_followup', 'Can create lead follow-up'),
            ('create_meeting', 'Can create lead meeting'),
            ('view_history', 'Can view lead history'),
            ('reactivate', 'Can reactivate inactive leads'),
            ('assign_manual', 'Can manually assign leads'),
            ('redistribute', 'Can redistribute leads'),
            ('override_assignment', 'Can override assignment'),
            ('view_broker_leads', 'Can view broker leads'),
        ]
        indexes = [
            models.Index(fields=['company', 'status', 'current_stage']),
            models.Index(fields=['company', 'current_salesman', 'status']),
        ]

    def __str__(self):
        return f'{self.full_name} - {self.phone_number}'


class LeadAssignment(UUIDBaseModel):
    TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
        ('retry', 'Retry'),
        ('escalation', 'Escalation'),
        ('self', 'Self Generated'),
        ('broker', 'Broker'),
    ]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='assignments')
    team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='lead_assignments')
    salesman = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='lead_assignments')
    assignment_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='manual')
    strategy_code = models.CharField(max_length=100, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_leads')
    assigned_at = models.DateTimeField(default=timezone.now)
    is_current = models.BooleanField(default=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-assigned_at']
        indexes = [models.Index(fields=['lead', 'is_current'])]

    def __str__(self):
        return f'{self.lead} -> {self.salesman or self.team}'


class LeadStageHistory(UUIDBaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='stage_history')
    from_stage = models.ForeignKey(LeadStage, null=True, blank=True, on_delete=models.SET_NULL, related_name='history_from')
    to_stage = models.ForeignKey(LeadStage, null=True, blank=True, on_delete=models.SET_NULL, related_name='history_to')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='lead_stage_changes')
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-changed_at']


class LeadActivity(UUIDBaseModel):
    TYPE_CHOICES = [('call', 'Call'), ('note', 'Note'), ('whatsapp', 'WhatsApp'), ('email', 'Email'), ('visit', 'Visit'), ('status_update', 'Status Update')]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    result = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='lead_activities')

    class Meta:
        ordering = ['-created_at']


class LeadFollowUp(UUIDBaseModel):
    STATUS_CHOICES = [('pending', 'Pending'), ('done', 'Done'), ('missed', 'Missed'), ('cancelled', 'Cancelled')]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='followups')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lead_followups')
    due_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reminder_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['due_at']


class Meeting(UUIDBaseModel):
    TYPE_CHOICES = [('office', 'Office'), ('site_visit', 'Site Visit'), ('online', 'Online')]
    STATUS_CHOICES = [('scheduled', 'Scheduled'), ('done', 'Done'), ('missed', 'Missed'), ('cancelled', 'Cancelled')]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='meetings')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lead_meetings')
    scheduled_at = models.DateTimeField()
    location = models.TextField(blank=True)
    meeting_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='office')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_at']


class LeadReactivation(UUIDBaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='reactivations')
    reactivated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reactivated_leads')
    reason = models.TextField()
    previous_status = models.CharField(max_length=30)

    class Meta:
        ordering = ['-created_at']
