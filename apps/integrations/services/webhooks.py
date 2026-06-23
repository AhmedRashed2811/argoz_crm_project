import hashlib
import hmac
import json
from django.utils import timezone
from django.db import transaction
from apps.integrations.models import TenantWebhookEndpoint, IncomingWebhookPayload, ExternalFormMapping
from apps.leads.services.leads import LeadService
from apps.audit.services.audit import AuditService


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


class IncomingWebhookService:
    @staticmethod
    def validate_token(endpoint: TenantWebhookEndpoint, raw_token: str) -> bool:
        return hmac.compare_digest(endpoint.secret_token_hash, hash_token(raw_token or ''))

    @staticmethod
    def extract_idempotency_key(payload):
        return str(payload.get('leadgen_id') or payload.get('id') or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())

    @classmethod
    @transaction.atomic
    def receive(cls, *, endpoint_uuid, raw_payload, token):
        endpoint = TenantWebhookEndpoint.objects.select_related('company', 'integration').get(endpoint_uuid=endpoint_uuid, is_active=True)
        if not cls.validate_token(endpoint, token):
            raise PermissionError('Invalid webhook token')
        endpoint.last_used_at = timezone.now()
        endpoint.save(update_fields=['last_used_at', 'updated_at'])
        idem = cls.extract_idempotency_key(raw_payload)
        payload, created = IncomingWebhookPayload.objects.get_or_create(endpoint=endpoint, idempotency_key=idem, defaults={'raw_payload': raw_payload})
        if not created and payload.processing_status == 'processed':
            return payload
        try:
            lead = cls.process_payload(payload)
            payload.processed_lead = lead
            payload.processing_status = 'processed'
            payload.processed_at = timezone.now()
            payload.save(update_fields=['processed_lead', 'processing_status', 'processed_at', 'updated_at'])
            endpoint.integration.last_success_at = timezone.now()
            endpoint.integration.last_error = ''
            endpoint.integration.save(update_fields=['last_success_at', 'last_error', 'updated_at'])
            AuditService.log(company=endpoint.company, actor_type='webhook', action='webhook.payload_processed', obj=lead, metadata={'payload_id': str(payload.id)})
            return payload
        except Exception as exc:
            payload.processing_status = 'failed'
            payload.error_message = str(exc)
            payload.save(update_fields=['processing_status', 'error_message', 'updated_at'])
            endpoint.integration.status = 'error'
            endpoint.integration.last_error = str(exc)
            endpoint.integration.save(update_fields=['status', 'last_error', 'updated_at'])
            raise

    @classmethod
    def process_payload(cls, payload: IncomingWebhookPayload):
        raw = payload.raw_payload
        form_id = str(raw.get('form_id') or raw.get('external_form_id') or '')
        mapping = ExternalFormMapping.objects.select_related('lead_source', 'campaign', 'endpoint__company').filter(endpoint=payload.endpoint, external_form_id=form_id, is_active=True).first()
        if not mapping:
            mapping = ExternalFormMapping.objects.select_related('lead_source', 'campaign', 'endpoint__company').filter(endpoint=payload.endpoint, is_active=True).first()
        if not mapping:
            raise ValueError('No active form mapping found for endpoint.')
        mapped = {'metadata': {'webhook_payload_id': str(payload.id), 'raw_payload': raw}}
        for field in mapping.field_mappings.all():
            value = raw.get(field.external_field_name)
            if field.is_required and value in (None, ''):
                raise ValueError(f'Missing required field: {field.external_field_name}')
            if value is not None:
                mapped[field.crm_field_name] = value
        full_name = mapped.get('full_name') or raw.get('full_name') or raw.get('name') or 'Meta Lead'
        phone_number = mapped.get('phone_number') or raw.get('phone') or raw.get('phone_number') or ''
        email = mapped.get('email') or raw.get('email') or ''
        lead, created = LeadService.create_lead(
            company=payload.endpoint.company,
            full_name=full_name,
            phone_country_code=mapped.get('phone_country_code', '+20'),
            phone_number=phone_number,
            email=email,
            source=mapping.lead_source,
            origin=mapping.default_origin,
            campaign=mapping.campaign,
            metadata=mapped.get('metadata', {}),
        )
        if created:
            LeadService.assign_lead(lead=lead, actor=None)
        return lead
