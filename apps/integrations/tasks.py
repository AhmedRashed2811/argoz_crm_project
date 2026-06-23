from celery import shared_task
from apps.integrations.services.webhooks import IncomingWebhookService

@shared_task
def retry_failed_webhooks():
    return IncomingWebhookService.retry_failed_payloads()
