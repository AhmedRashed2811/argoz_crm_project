from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import LeadSLAInstance, SLADefinition


class SLADashboardView(LoginRequiredMixin, ListView):
    model = LeadSLAInstance
    template_name = 'sla/dashboard.html'
    context_object_name = 'sla_instances'
    paginate_by = 50


class SLADefinitionListView(LoginRequiredMixin, ListView):
    model = SLADefinition
    template_name = 'sla/definitions.html'
