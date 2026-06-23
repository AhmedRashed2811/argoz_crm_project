from django.db import models
from apps.core.models import UUIDBaseModel, ActiveManager


class Company(UUIDBaseModel):
    STATUS_ACTIVE = 'active'
    STATUS_SUSPENDED = 'suspended'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=120)
    legal_name = models.CharField(max_length=255, blank=True)
    timezone = models.CharField(max_length=64, default='Africa/Cairo')
    currency = models.CharField(max_length=3, default='EGP')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['name']
        permissions = [
            ('view_company_dashboard', 'Can view company dashboard'),
            ('manage_company', 'Can manage company'),
            ('manage_branches', 'Can manage branches'),
            ('manage_teams', 'Can manage teams'),
            ('manage_languages', 'Can manage languages'),
        ]

    def __str__(self):
        return self.name


class Branch(UUIDBaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['company__name', 'name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return f'{self.company} - {self.name}'


class Language(UUIDBaseModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name='languages')
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'code')]

    def __str__(self):
        return self.name
