from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import TemplateView
from apps.leads.models import Lead
from apps.sla.models import LeadSLAInstance
from apps.marketing.models import Campaign


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.request.user.company
        now = timezone.now()

        # Live metrics
        if company:
            lead_qs = Lead.objects.filter(company=company)
            sla_qs = LeadSLAInstance.objects.filter(lead__company=company)
            camp_qs = Campaign.objects.filter(company=company, is_archived=False)
        else:
            lead_qs = Lead.objects.all()
            sla_qs = LeadSLAInstance.objects.all()
            camp_qs = Campaign.objects.filter(is_archived=False)

        active_leads = lead_qs.filter(status='active').count()
        open_sla = sla_qs.filter(status='active').count()
        active_campaigns = camp_qs.filter(lifecycle_status_cache='active').count()
        pending_approvals = camp_qs.filter(approval_status='pending').count()
        leads_this_month = lead_qs.filter(created_at__month=now.month, created_at__year=now.year).count()
        expired_sla = sla_qs.filter(status__in=['expired', 'processed']).count()

        context.update({
            'page_title': 'Executive Dashboard',
            'metric_cards': [
                {'label': 'Active Leads', 'value': active_leads, 'hint': f'{leads_this_month} added this month'},
                {'label': 'Open SLA Items', 'value': open_sla, 'hint': f'{expired_sla} expired total'},
                {'label': 'Active Campaigns', 'value': active_campaigns, 'hint': f'{camp_qs.count()} total'},
                {'label': 'Pending Approvals', 'value': pending_approvals, 'hint': 'Finance queue'},
            ],
        })
        return context
