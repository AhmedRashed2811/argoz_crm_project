from apps.integrations.models import IncomingWebhookPayload, TenantWebhookEndpoint

def get_incoming_payload_by_id(company, payload_id):
    if company:
        return IncomingWebhookPayload.objects.filter(endpoint__company=company, pk=payload_id).first()
    return IncomingWebhookPayload.objects.filter(pk=payload_id).first()

def get_webhook_endpoint_by_id(company, endpoint_id):
    if company:
        return TenantWebhookEndpoint.objects.filter(company=company, pk=endpoint_id).first()
    return TenantWebhookEndpoint.objects.filter(pk=endpoint_id).first()
