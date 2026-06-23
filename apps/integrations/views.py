import json
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, TemplateView
from django.shortcuts import get_object_or_404
from .models import CompanyIntegration, IncomingWebhookPayload, TenantWebhookEndpoint
from .services.webhooks import IncomingWebhookService
from apps.audit.services.audit import AuditService


class IntegrationListView(LoginRequiredMixin, ListView):
    model = CompanyIntegration
    template_name = 'integrations/integration_list.html'
    context_object_name = 'integrations'


class MetaSetupView(LoginRequiredMixin, TemplateView):
    template_name = 'integrations/meta_setup.html'


class WebhookLogListView(LoginRequiredMixin, ListView):
    model = IncomingWebhookPayload
    template_name = 'integrations/webhook_logs.html'
    context_object_name = 'payloads'
    paginate_by = 50


@method_decorator(csrf_exempt, name='dispatch')
class TenantWebhookView(View):
    def post(self, request, endpoint_uuid):
        token = request.headers.get('X-CRM-Webhook-Token') or request.GET.get('token') or ''
        try:
            raw_payload = json.loads(request.body.decode('utf-8') or '{}')
            payload = IncomingWebhookService.receive(endpoint_uuid=endpoint_uuid, raw_payload=raw_payload, token=token)
            return JsonResponse({'status': payload.processing_status, 'payload_id': str(payload.id)})
        except PermissionError:
            return HttpResponseForbidden('Invalid token')
        except Exception as exc:
            return JsonResponse({'status': 'failed', 'error': str(exc)}, status=400)


class WebhookReprocessView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Reprocess a failed webhook payload."""
    permission_required = 'integrations.reprocess_payload'

    def post(self, request, pk):
        payload = get_object_or_404(IncomingWebhookPayload, pk=pk)
        if payload.processing_status != 'failed':
            return JsonResponse({'error': 'Only failed payloads can be reprocessed.'}, status=400)
        try:
            payload.processing_status = 'pending'
            payload.error_message = ''
            payload.save(update_fields=['processing_status', 'error_message', 'updated_at'])
            lead = IncomingWebhookService.process_payload(payload)
            payload.processed_lead = lead
            payload.processing_status = 'processed'
            payload.save(update_fields=['processed_lead', 'processing_status', 'updated_at'])
            AuditService.log(
                company=payload.endpoint.company, actor=request.user,
                action='webhook.payload_reprocessed', obj=lead,
                metadata={'payload_id': str(payload.id)},
            )
            return JsonResponse({'status': 'processed', 'lead_id': str(lead.pk) if lead else None})
        except Exception as exc:
            payload.processing_status = 'failed'
            payload.error_message = str(exc)
            payload.save(update_fields=['processing_status', 'error_message', 'updated_at'])
            return JsonResponse({'status': 'failed', 'error': str(exc)}, status=400)


class WebhookSecretRotateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Rotate the secret token for a webhook endpoint."""
    permission_required = 'integrations.manage_field_mapping'

    def post(self, request, pk):
        import secrets
        from .services.webhooks import hash_token

        endpoint = get_object_or_404(TenantWebhookEndpoint, pk=pk)
        new_token = secrets.token_urlsafe(32)
        endpoint.secret_token_hash = hash_token(new_token)
        endpoint.save(update_fields=['secret_token_hash', 'updated_at'])
        AuditService.log(
            company=endpoint.company, actor=request.user,
            action='webhook.secret_rotated', obj=endpoint,
        )
        return JsonResponse({'status': 'rotated', 'new_token': new_token})
