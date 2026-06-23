from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.views.generic import ListView
from .models import LeadSLAInstance, SLADefinition
from .selectors import get_sla_instances, get_sla_definitions


class SLADashboardView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = LeadSLAInstance
    template_name = 'sla/dashboard.html'
    context_object_name = 'sla_instances'
    paginate_by = 50
    permission_required = 'sla.manage_sla_policy'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_sla_instances(company)


class SLADefinitionListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = SLADefinition
    template_name = 'sla/definitions.html'
    permission_required = 'sla.manage_sla_policy'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_sla_definitions(company)

