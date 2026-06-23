from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import UUIDBaseModel


class Campaign(UUIDBaseModel):
    TARGET_CHOICES = [('project', 'Project'), ('unit', 'Unit'), ('event', 'Event'), ('exhibition', 'Exhibition'), ('other', 'Other')]
    APPROVAL_CHOICES = [('draft', 'Draft'), ('pending', 'Pending'), ('approved', 'Approved'), ('semi_approved', 'Semi Approved'), ('not_approved', 'Not Approved')]
    LIFECYCLE_CHOICES = [('coming', 'Coming'), ('active', 'Active'), ('ended', 'Ended')]
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    target_type = models.CharField(max_length=30, choices=TARGET_CHOICES, default='other')
    target_object_id = models.UUIDField(null=True, blank=True)
    total_budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    approval_status = models.CharField(max_length=30, choices=APPROVAL_CHOICES, default='draft')
    lifecycle_status_cache = models.CharField(max_length=20, choices=LIFECYCLE_CHOICES, default='coming')
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_campaigns')
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('view_campaigns', 'Can view campaigns'),
            ('create_campaign', 'Can create campaign'),
            ('update_campaign', 'Can update campaign'),
            ('archive_campaign', 'Can archive campaign'),
            ('manage_assets', 'Can manage campaign assets'),
            ('manage_budget', 'Can manage campaign budget'),
            ('submit_approval', 'Can submit campaign approval'),
            ('view_roi', 'Can view ROI'),
            ('manage_campaign_types', 'Can manage campaign types'),
            ('manage_attribution', 'Can manage campaign attribution'),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(end_date__gte=models.F('start_date')), name='campaign_end_date_gte_start_date'),
            models.CheckConstraint(check=models.Q(total_budget__gte=0), name='campaign_total_budget_non_negative'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.total_budget is not None and self.total_budget < 0:
            raise ValidationError({'total_budget': 'Campaign total budget must be non-negative.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Campaign end date must be equal to or after the start date.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def update_lifecycle_status(self, save=True):
        today = timezone.localdate()
        if today < self.start_date:
            status = 'coming'
        elif self.start_date <= today <= self.end_date:
            status = 'active'
        else:
            status = 'ended'
        self.lifecycle_status_cache = status
        if save:
            self.save(update_fields=['lifecycle_status_cache', 'updated_at'])
        return status


class CampaignTypeSelection(UUIDBaseModel):
    TYPE_CHOICES = [('events', 'Events'), ('tv_ads', 'TV Ads'), ('street_ads', 'Street Ads'), ('social_media', 'Social Media'), ('exhibition', 'Exhibition')]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='type_selections')
    type_code = models.CharField(max_length=40, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('campaign', 'type_code')]


class CampaignAsset(UUIDBaseModel):
    ASSET_CHOICES = [('image', 'Image'), ('video', 'Video'), ('document', 'Document')]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='assets')
    related_type = models.CharField(max_length=80, blank=True)
    related_object_id = models.UUIDField(null=True, blank=True)
    file = models.FileField(upload_to='campaign_assets/')
    asset_type = models.CharField(max_length=20, choices=ASSET_CHOICES, default='image')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='uploaded_campaign_assets')


class CampaignEvent(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='events')
    event_name = models.CharField(max_length=255)
    venue_place = models.CharField(max_length=255)
    event_date = models.DateField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    target_attendees = models.PositiveIntegerField(null=True, blank=True)
    actual_attendees = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='event_logos/', blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='campaign_event_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Event budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.event_name


class EventCelebrity(UUIDBaseModel):
    event = models.ForeignKey(CampaignEvent, on_delete=models.CASCADE, related_name='celebrities')
    name = models.CharField(max_length=255)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='event_celebrity_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Celebrity budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class EventGiveaway(UUIDBaseModel):
    event = models.ForeignKey(CampaignEvent, on_delete=models.CASCADE, related_name='giveaways')
    name = models.CharField(max_length=255)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='event_giveaway_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Giveaway budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class EventCatering(UUIDBaseModel):
    event = models.ForeignKey(CampaignEvent, on_delete=models.CASCADE, related_name='catering_items')
    name = models.CharField(max_length=255)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='event_catering_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Catering budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TVAd(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='tv_ads')
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='tv_ad_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'TV Ad budget must be non-negative.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'TV Ad end date must be equal to or after start date.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TVAdChannel(UUIDBaseModel):
    tv_ad = models.ForeignKey(TVAd, on_delete=models.CASCADE, related_name='channels')
    channel_name = models.CharField(max_length=255)
    channel_budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    assets = models.ManyToManyField(CampaignAsset, blank=True, related_name='tv_channels')

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(channel_budget__gte=0), name='tv_ad_channel_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.channel_budget is not None and self.channel_budget < 0:
            raise ValidationError({'channel_budget': 'TV channel budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TVAdSlot(UUIDBaseModel):
    tv_ad = models.ForeignKey(TVAd, on_delete=models.CASCADE, related_name='slots')
    appearance_time = models.TimeField()
    number_of_appearances = models.PositiveIntegerField(default=1)


class StreetAd(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='street_ads')
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='street_ad_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Street Ad budget must be non-negative.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Street Ad end date must be equal to or after start date.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StreetAdTypeLine(UUIDBaseModel):
    AD_TYPE_CHOICES = [
        ('billboard', 'Billboard'), ('banner', 'Banner'), ('bus_shelter', 'Bus Shelter'),
        ('led_screen', 'LED Screen'), ('transit_wrap', 'Transit / Bus Wrap'), ('wall_mural', 'Wall Mural'),
        ('lamp_post', 'Lamp Post'), ('bridge_banner', 'Bridge Banner'), ('other', 'Other'),
    ]
    street_ad = models.ForeignKey(StreetAd, on_delete=models.CASCADE, related_name='type_lines')
    ad_type = models.CharField(max_length=40, choices=AD_TYPE_CHOICES)
    total_number = models.PositiveIntegerField(default=1)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='street_ad_type_line_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Street ad type budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StreetAdLocation(UUIDBaseModel):
    type_line = models.ForeignKey(StreetAdTypeLine, on_delete=models.CASCADE, related_name='locations')
    location = models.TextField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='street_ad_location_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Street ad location budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ExhibitionRecord(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='exhibitions')
    name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='exhibition_record_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Exhibition budget must be non-negative.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Exhibition end date must be equal to or after start date.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class SocialMediaAd(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='social_ads')
    name = models.CharField(max_length=255)
    target_kpi = models.CharField(max_length=100, blank=True)
    linked_event = models.ForeignKey(CampaignEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_ads')
    description = models.TextField(blank=True)


class SocialMediaPlatformLine(UUIDBaseModel):
    PLATFORM_CHOICES = [('meta', 'Meta'), ('facebook', 'Facebook'), ('instagram', 'Instagram'), ('whatsapp', 'WhatsApp'), ('tiktok', 'TikTok'), ('linkedin', 'LinkedIn'), ('x', 'X'), ('google_ads', 'Google Ads'), ('website', 'Website')]
    social_ad = models.ForeignKey(SocialMediaAd, on_delete=models.CASCADE, related_name='platform_lines')
    platform = models.CharField(max_length=40, choices=PLATFORM_CHOICES)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    target_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    creative_assets = models.ManyToManyField(CampaignAsset, blank=True, related_name='social_platforms')

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(budget__gte=0), name='social_media_platform_line_budget_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.budget is not None and self.budget < 0:
            raise ValidationError({'budget': 'Social platform budget must be non-negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CampaignOtherCost(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='other_costs')
    value = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    reason = models.TextField()
    cost_created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='campaign_other_costs')

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(value__gte=0), name='campaign_other_cost_value_non_negative'),
        ]

    def clean(self):
        super().clean()
        if self.value is not None and self.value < 0:
            raise ValidationError({'value': 'Other cost value must be non-negative.'})
        if self.value is not None and not str(self.reason or '').strip():
            raise ValidationError({'reason': 'Reason is required when other cost value is set.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CampaignApprovalHistory(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='approval_history')
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='campaign_approval_decisions')
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-decided_at']


class CampaignKPIResult(UUIDBaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='kpi_results')
    metric_code = models.CharField(max_length=100)
    metric_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    calculated_at = models.DateTimeField(default=timezone.now)


class LeadCampaignAttribution(UUIDBaseModel):
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='campaign_attributions')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='lead_attributions')
    campaign_type = models.CharField(max_length=60, blank=True)
    child_object_id = models.UUIDField(null=True, blank=True)
    platform = models.CharField(max_length=60, blank=True)
    tracking_method = models.CharField(max_length=60, default='manual')

    class Meta:
        indexes = [models.Index(fields=['campaign', 'campaign_type', 'platform'])]


class EventAttendance(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='event_attendances')
    event = models.ForeignKey(CampaignEvent, on_delete=models.CASCADE, related_name='attendances')
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, null=True, blank=True, related_name='event_attendances')
    registered_at = models.DateTimeField(default=timezone.now)
    attended = models.BooleanField(default=False)
    platform = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-registered_at']
