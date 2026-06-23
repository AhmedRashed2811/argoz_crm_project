from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from apps.core.models import UUIDBaseModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, editable=False)
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.SET_NULL, related_name='users')
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        permissions = [
            ('view_users', 'Can view users'),
            ('create_user', 'Can create users'),
            ('update_user', 'Can update users'),
            ('deactivate_user', 'Can deactivate users'),
            ('manage_user_groups', 'Can manage user groups'),
        ]

    def __str__(self):
        return self.get_full_name() or self.email or self.username

    def save(self, *args, **kwargs):
        import uuid
        if not self.id:
            self.id = uuid.uuid4()
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)


class UserProfile(UUIDBaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=255, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to='user_avatars/', blank=True, null=True)
    default_group_template = models.ForeignKey(
        'permissions_engine.CRMGroupTemplate',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='defaulted_profiles',
    )
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.display_name or str(self.user)


class Team(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=120)
    sales_head = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='headed_teams')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['company__name', 'sort_order', 'name']
        unique_together = [('company', 'code')]

    def __str__(self):
        return self.name


class TeamMembership(UUIDBaseModel):
    ROLE_SALES_HEAD = 'sales_head'
    ROLE_SALESMAN = 'salesman'
    ROLE_OPERATION = 'operation'
    ROLE_CHOICES = [
        (ROLE_SALES_HEAD, 'Sales Head'),
        (ROLE_SALESMAN, 'Salesman'),
        (ROLE_OPERATION, 'Sales Operation'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_memberships')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_SALESMAN)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('team', 'user', 'role')]

    def __str__(self):
        return f'{self.user} - {self.team} ({self.role})'


class SalesProfile(UUIDBaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='sales_profile')
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='sales_profiles')
    is_available = models.BooleanField(default=True)
    max_active_leads = models.PositiveIntegerField(null=True, blank=True)
    active_lead_count_cache = models.PositiveIntegerField(default=0)
    last_received_lead_at = models.DateTimeField(null=True, blank=True)
    languages = models.ManyToManyField('companies.Language', blank=True, related_name='sales_profiles')

    class Meta:
        indexes = [models.Index(fields=['company', 'is_available', 'active_lead_count_cache'])]

    def __str__(self):
        return f'Sales profile: {self.user}'


class BrokerProfile(UUIDBaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='broker_profile')
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='broker_profiles')
    broker_company_name = models.CharField(max_length=255, blank=True)
    license_no = models.CharField(max_length=120, blank=True)
    commission_policy = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.broker_company_name or str(self.user)
