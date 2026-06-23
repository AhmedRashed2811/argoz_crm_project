from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView
from apps.leads.selectors import (
    get_leads_report_queryset,
    get_lead_stage_distribution,
    get_lead_trend,
    get_salesman_performance,
    get_lead_source_breakdown,
    get_lead_stage_funnel,
    get_lead_followups_queryset,
    get_meetings_queryset,
    get_assignments_this_month,
)
from apps.sla.selectors import (
    get_sla_instances,
    get_sla_compliance_rate,
)
from apps.marketing.selectors import (
    get_campaigns_report_queryset,
    get_campaign_kpi_results,
    get_top_campaigns,
    get_campaign_source_leads,
    get_campaign_platform_performance,
    get_budget_by_approval,
    get_monthly_spend,
    get_pending_campaigns_detail,
    get_average_cost_per_lead,
    get_campaign_review_queue,
    get_total_campaign_budget,
    get_approved_campaign_budget,
)


class ExecutiveReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/executive_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        now = timezone.now()

        # Lead pipeline summary
        lead_qs = get_leads_report_queryset(company)
        ctx['total_leads'] = lead_qs.count()
        ctx['active_leads'] = lead_qs.filter(status='active').count()
        ctx['inactive_leads'] = lead_qs.filter(status='inactive').count()
        ctx['leads_this_month'] = lead_qs.filter(created_at__month=now.month, created_at__year=now.year).count()

        # Lead stage distribution
        ctx['stage_distribution'] = get_lead_stage_distribution(company)

        # SLA summary
        sla_qs = get_sla_instances(company)
        ctx['open_sla_count'] = sla_qs.filter(status='active').count()
        ctx['expired_sla_count'] = sla_qs.filter(status__in=['expired', 'processed']).count()
        ctx['satisfied_sla_count'] = sla_qs.filter(status='satisfied').count()

        # Campaign summary
        camp_qs = get_campaigns_report_queryset(company)
        ctx['active_campaigns'] = camp_qs.filter(lifecycle_status_cache='active').count()
        ctx['pending_approvals'] = camp_qs.filter(approval_status='pending').count()
        ctx['total_campaign_budget'] = get_total_campaign_budget(company)

        # Lead trend (last 12 weeks)
        ctx['lead_trend'] = get_lead_trend(company, now - timezone.timedelta(weeks=12))

        return ctx


class SalesReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/sales_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        now = timezone.now()

        # Per-salesman performance
        ctx['salesman_performance'] = get_salesman_performance(company)

        # Per-source lead counts
        ctx['source_breakdown'] = get_lead_source_breakdown(company)

        # Stage conversion funnel
        ctx['stage_funnel'] = get_lead_stage_funnel(company)

        # Follow-up/Meeting summary this month
        followup_qs = get_lead_followups_queryset(company)
        ctx['followups_this_month'] = followup_qs.filter(created_at__month=now.month, created_at__year=now.year).count()
        ctx['followups_pending'] = followup_qs.filter(status='pending').count()

        meeting_qs = get_meetings_queryset(company)
        ctx['meetings_this_month'] = meeting_qs.filter(created_at__month=now.month, created_at__year=now.year).count()
        ctx['meetings_completed'] = meeting_qs.filter(status='completed').count()

        # SLA compliance: % of satisfied vs total expired+satisfied
        ctx['sla_compliance_rate'] = get_sla_compliance_rate(company)

        # Assignment distribution this month
        ctx['assignments_this_month'] = get_assignments_this_month(company, now.year, now.month)

        return ctx


class MarketingReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/marketing_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company

        # Refresh metrics for active campaigns to guarantee accuracy
        from apps.marketing.services.roi_service import ROIService
        camp_qs = get_campaigns_report_queryset(company)
        for campaign in camp_qs.filter(lifecycle_status_cache='active'):
            ROIService.recalculate_all_kpis(campaign)

        # Campaign overview
        ctx['total_campaigns'] = camp_qs.count()
        ctx['active_campaigns'] = camp_qs.filter(lifecycle_status_cache='active').count()
        ctx['budget_total'] = get_total_campaign_budget(company)
        ctx['budget_approved'] = get_approved_campaign_budget(company)

        # Per-campaign KPIs
        ctx['campaign_kpis'] = get_campaign_kpi_results(company)

        # Top campaigns by lead count
        ctx['top_campaigns'] = get_top_campaigns(company, 10)

        # Leads per source from campaigns
        ctx['campaign_source_leads'] = get_campaign_source_leads(company)

        # Platform performance (social media)
        ctx['platform_performance'] = get_campaign_platform_performance(company)

        return ctx


class FinanceReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/finance_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company

        # Budget summary by approval status
        ctx['budget_by_approval'] = get_budget_by_approval(company)

        # Monthly spend trend (budget of campaigns that started each month)
        ctx['monthly_spend'] = get_monthly_spend(company)

        # Pending approvals detail
        ctx['pending_campaigns'] = get_pending_campaigns_detail(company)

        # Average cost per lead across all approved campaigns
        ctx['avg_cost_per_lead'] = get_average_cost_per_lead(company)

        # Finance queue (semi_approved + not_approved)
        ctx['review_queue'] = get_campaign_review_queue(company, 20)

        return ctx
