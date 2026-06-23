import json
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.views.generic import ListView, TemplateView
from django.shortcuts import get_object_or_404
from django.http import Http404
from .models import CompanyIntegration, IncomingWebhookPayload, TenantWebhookEndpoint
from .services.webhooks import IncomingWebhookService
from .selectors import get_incoming_payload_by_id, get_webhook_endpoint_by_id
from apps.audit.services.audit import AuditService


class IntegrationListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = CompanyIntegration
    template_name = 'integrations/integration_list.html'
    context_object_name = 'integrations'
    permission_required = 'integrations.manage_meta_connection'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = CompanyIntegration.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs


class MetaSetupView(LoginRequiredMixin, CRMPermissionRequiredMixin, TemplateView):
    template_name = 'integrations/meta_setup.html'
    permission_required = 'integrations.manage_meta_connection'


class WebhookLogListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = IncomingWebhookPayload
    template_name = 'integrations/webhook_logs.html'
    context_object_name = 'payloads'
    paginate_by = 50
    permission_required = 'integrations.manage_meta_connection'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = IncomingWebhookPayload.objects.all()
        if company:
            qs = qs.filter(endpoint__company=company)
        return qs


@method_decorator(csrf_exempt, name='dispatch')
class TenantWebhookView(View):
    def post(self, request, endpoint_uuid):
        import uuid
        try:
            uuid.UUID(str(endpoint_uuid))
        except ValueError:
            return JsonResponse({'status': 'failed', 'error': 'Invalid endpoint UUID format'}, status=400)

        token = request.headers.get('X-CRM-Webhook-Token') or request.GET.get('token') or ''
        if not token:
            return HttpResponseForbidden('Missing token')

        try:
            raw_payload = json.loads(request.body.decode('utf-8') or '{}')
            payload = IncomingWebhookService.receive(endpoint_uuid=endpoint_uuid, raw_payload=raw_payload, token=token)
            return JsonResponse({'status': payload.processing_status, 'payload_id': str(payload.id)})
        except PermissionError as exc:
            return HttpResponseForbidden(str(exc))
        except TenantWebhookEndpoint.DoesNotExist:
            return JsonResponse({'status': 'failed', 'error': 'Endpoint not found or inactive'}, status=404)
        except Exception as exc:
            return JsonResponse({'status': 'failed', 'error': str(exc)}, status=400)


class WebhookReprocessView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    """Reprocess a failed webhook payload."""
    permission_required = 'integrations.manage_meta_connection'

    def post(self, request, pk):
        company = request.user.company if not request.user.is_superuser else None
        payload = get_incoming_payload_by_id(company, pk)
        if not payload:
            raise Http404("Payload not found or access denied.")
        if payload.processing_status != 'failed':
            return JsonResponse({'error': 'Only failed payloads can be reprocessed.'}, status=400)
        try:
            payload = IncomingWebhookService.reprocess_payload(payload)
            lead = payload.processed_lead
            return JsonResponse({'status': 'reprocessed', 'lead_id': str(lead.pk) if lead else None})
        except Exception as exc:
            return JsonResponse({'status': 'failed', 'error': str(exc)}, status=400)


class WebhookSecretRotateView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    """Rotate the secret token for a webhook endpoint."""
    permission_required = 'integrations.manage_meta_connection'

    def post(self, request, pk):
        import secrets
        from .services.webhooks import hash_token

        company = request.user.company if not request.user.is_superuser else None
        endpoint = get_webhook_endpoint_by_id(company, pk)
        if not endpoint:
            raise Http404("Endpoint not found or access denied.")
        new_token = secrets.token_urlsafe(32)
        endpoint.secret_token_hash = hash_token(new_token)
        endpoint.save(update_fields=['secret_token_hash', 'updated_at'])
        AuditService.log(
            company=endpoint.company, actor=request.user,
            action='webhook.secret_rotated', obj=endpoint,
        )
        return JsonResponse({'status': 'rotated', 'new_token': new_token})
