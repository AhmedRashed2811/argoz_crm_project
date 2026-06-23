import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class UUIDBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_%(class)s_set',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_%(class)s_set',
    )
    is_archived = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_archived=False, is_deleted=False)

    def for_company(self, company):
        if company is None:
            return self
        return self.filter(company=company)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return ActiveQuerySet(self.model, using=self._db).active()


class SystemConfiguration(UUIDBaseModel):
    key = models.SlugField(unique=True, max_length=120)
    value = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key

class PolicyDefinition(UUIDBaseModel):
    DATA_CHOICE = 'choice'
    DATA_INTEGER = 'integer'
    DATA_DURATION = 'duration'
    DATA_BOOLEAN = 'boolean'
    DATA_JSON = 'json'
    DATA_TYPE_CHOICES = [
        (DATA_CHOICE, 'Choice'),
        (DATA_INTEGER, 'Integer'),
        (DATA_DURATION, 'Duration'),
        (DATA_BOOLEAN, 'Boolean'),
        (DATA_JSON, 'JSON'),
    ]
    code = models.SlugField(unique=True, max_length=120)
    module = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES, default=DATA_CHOICE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['module', 'code']
        permissions = [
            ('view_policies', 'Can view policies'),
            ('manage_policies', 'Can manage policies'),
        ]

    def __str__(self):
        return self.name


class PolicyOption(UUIDBaseModel):
    policy_definition = models.ForeignKey(PolicyDefinition, on_delete=models.CASCADE, related_name='options')
    code = models.SlugField(max_length=120)
    label = models.CharField(max_length=255)
    value = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['policy_definition__code', 'sort_order', 'label']
        unique_together = [('policy_definition', 'code')]

    def __str__(self):
        return f'{self.policy_definition.code}: {self.code}'


class CompanyPolicy(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='policies')
    policy_definition = models.ForeignKey(PolicyDefinition, on_delete=models.CASCADE, related_name='company_policies')
    selected_option = models.ForeignKey(PolicyOption, null=True, blank=True, on_delete=models.SET_NULL, related_name='company_policies')
    value = models.JSONField(default=dict, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('company', 'policy_definition', 'is_active')]
        ordering = ['company__name', 'policy_definition__module', 'policy_definition__code']

    def __str__(self):
        return f'{self.company} - {self.policy_definition.code}'


class PolicyChangeHistory(UUIDBaseModel):
    company_policy = models.ForeignKey(CompanyPolicy, on_delete=models.CASCADE, related_name='history')
    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='policy_changes')
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']
