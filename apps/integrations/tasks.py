from celery import shared_task
from django.utils import timezone
from apps.integrations.services.webhooks import IncomingWebhookService


@shared_task(name='apps.integrations.tasks.retry_failed_webhooks')
def retry_failed_webhooks():
    return IncomingWebhookService.retry_failed_payloads()


@shared_task(name='apps.integrations.tasks.process_webhook_payload', max_retries=3, default_retry_delay=300)
def process_webhook_payload(payload_id):
    from apps.integrations.models import IncomingWebhookPayload
    from apps.audit.services.audit import AuditService
    from django.db import transaction

    try:
        payload = IncomingWebhookPayload.objects.select_related('endpoint__company', 'endpoint__integration').get(pk=payload_id)
    except IncomingWebhookPayload.DoesNotExist:
        return

    with transaction.atomic():
        try:
            lead = IncomingWebhookService.process_payload(payload)
            payload.processed_lead = lead
            payload.processing_status = 'processed'
            payload.processed_at = timezone.now()
            payload.save(update_fields=['processed_lead', 'processing_status', 'processed_at', 'updated_at'])
            integration = payload.endpoint.integration
            integration.last_success_at = timezone.now()
            integration.last_error = ''
            integration.save(update_fields=['last_success_at', 'last_error', 'updated_at'])
            AuditService.log(company=payload.endpoint.company, actor_type='webhook', action='webhook.payload_processed', obj=lead, metadata={'payload_id': payload_id})
        except Exception as exc:
            payload.processing_status = 'failed'
            payload.error_message = str(exc)
            payload.retry_count += 1
            backoff = 5 * (2 ** (payload.retry_count - 1))
            payload.next_retry_at = timezone.now() + timezone.timedelta(minutes=backoff)
            payload.save(update_fields=['processing_status', 'error_message', 'retry_count', 'next_retry_at', 'updated_at'])
            integration = payload.endpoint.integration
            integration.status = 'error'
            integration.last_error = str(exc)
            integration.save(update_fields=['status', 'last_error', 'updated_at'])
            AuditService.log(company=payload.endpoint.company, actor_type='webhook', action='webhook.payload_failed', obj=payload, metadata={'error': str(exc), 'payload_id': payload_id})
