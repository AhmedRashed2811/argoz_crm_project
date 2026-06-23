import uuid
from django.db import models
from apps.core.models import UUIDBaseModel


class IntegrationProvider(UUIDBaseModel):
    code = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CompanyIntegration(UUIDBaseModel):
    STATUS_CHOICES = [('draft', 'Draft'), ('active', 'Active'), ('paused', 'Paused'), ('error', 'Error')]
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='integrations')
    provider = models.ForeignKey(IntegrationProvider, on_delete=models.PROTECT, related_name='company_integrations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    setup_metadata = models.JSONField(default=dict, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        permissions = [
            ('view_integrations', 'Can view integrations'),
            ('manage_meta_connection', 'Can manage Meta connection'),
            ('manage_field_mapping', 'Can manage field mapping'),
            ('view_webhook_logs', 'Can view webhook logs'),
            ('reprocess_payload', 'Can reprocess payload'),
        ]

    def __str__(self):
        return f'{self.company} - {self.provider}'


class TenantWebhookEndpoint(UUIDBaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='webhook_endpoints')
    integration = models.ForeignKey(CompanyIntegration, on_delete=models.CASCADE, related_name='webhook_endpoints')
    endpoint_uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    secret_token_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def public_path(self):
        return f'/integrations/webhooks/{self.endpoint_uuid}/'


class ExternalFormMapping(UUIDBaseModel):
    ORIGIN_CHOICES = [('direct', 'Direct'), ('broker', 'Broker')]
    endpoint = models.ForeignKey(TenantWebhookEndpoint, on_delete=models.CASCADE, related_name='form_mappings')
    external_page_id = models.CharField(max_length=255, blank=True)
    external_form_id = models.CharField(max_length=255)
    campaign = models.ForeignKey('marketing.Campaign', null=True, blank=True, on_delete=models.SET_NULL, related_name='external_form_mappings')
    lead_source = models.ForeignKey('leads.LeadSource', on_delete=models.PROTECT, related_name='external_form_mappings')
    default_origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default='direct')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('endpoint', 'external_form_id')]


class IntegrationFieldMapping(UUIDBaseModel):
    form_mapping = models.ForeignKey(ExternalFormMapping, on_delete=models.CASCADE, related_name='field_mappings')
    external_field_name = models.CharField(max_length=255)
    crm_field_name = models.CharField(max_length=255)
    transform_rule = models.JSONField(default=dict, blank=True)
    is_required = models.BooleanField(default=False)


class IncomingWebhookPayload(UUIDBaseModel):
    STATUS_CHOICES = [('received', 'Received'), ('processed', 'Processed'), ('failed', 'Failed'), ('ignored', 'Ignored'), ('reprocessed', 'Reprocessed')]
    endpoint = models.ForeignKey(TenantWebhookEndpoint, on_delete=models.CASCADE, related_name='incoming_payloads')
    raw_payload = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    processing_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    error_message = models.TextField(blank=True)
    processed_lead = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='webhook_payloads')
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('endpoint', 'idempotency_key')]
        ordering = ['-received_at']
