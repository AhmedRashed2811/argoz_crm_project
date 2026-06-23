from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.views.generic import ListView, DetailView
from .models import AuditLog


class AuditLogListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = AuditLog
    template_name = 'audit/audit_list.html'
    context_object_name = 'logs'
    paginate_by = 50
    permission_required = 'audit.view_audit_log'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = AuditLog.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs


class AuditLogDetailView(LoginRequiredMixin, CRMPermissionRequiredMixin, DetailView):
    model = AuditLog
    template_name = 'audit/audit_detail.html'
    permission_required = 'audit.view_audit_log'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = AuditLog.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs
