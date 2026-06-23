from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Avg, Sum, F
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from django.views.generic import TemplateView
from apps.leads.models import Lead, LeadAssignment, LeadStageHistory, LeadFollowUp, Meeting
from apps.marketing.models import Campaign, CampaignKPIResult, LeadCampaignAttribution
from apps.sla.models import LeadSLAInstance


class ExecutiveReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/executive_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        now = timezone.now()

        # Lead pipeline summary
        lead_qs = Lead.objects.filter(company=company) if company else Lead.objects.all()
        ctx['total_leads'] = lead_qs.count()
        ctx['active_leads'] = lead_qs.filter(status='active').count()
        ctx['inactive_leads'] = lead_qs.filter(status='inactive').count()
        ctx['leads_this_month'] = lead_qs.filter(created_at__month=now.month, created_at__year=now.year).count()

        # Lead stage distribution
        ctx['stage_distribution'] = list(
            lead_qs.filter(status='active').values(stage_name=F('current_stage__name'))
            .annotate(count=Count('id')).order_by('-count')
        )

        # SLA summary
        sla_qs = LeadSLAInstance.objects.filter(lead__company=company) if company else LeadSLAInstance.objects.all()
        ctx['open_sla_count'] = sla_qs.filter(status='active').count()
        ctx['expired_sla_count'] = sla_qs.filter(status__in=['expired', 'processed']).count()
        ctx['satisfied_sla_count'] = sla_qs.filter(status='satisfied').count()

        # Campaign summary
        camp_qs = Campaign.objects.filter(company=company) if company else Campaign.objects.all()
        ctx['active_campaigns'] = camp_qs.filter(lifecycle_status_cache='active', is_archived=False).count()
        ctx['pending_approvals'] = camp_qs.filter(approval_status='pending', is_archived=False).count()
        ctx['total_campaign_budget'] = camp_qs.filter(is_archived=False).aggregate(total=Sum('total_budget'))['total'] or 0

        # Lead trend (last 12 weeks)
        ctx['lead_trend'] = list(
            lead_qs.filter(created_at__gte=now - timezone.timedelta(weeks=12))
            .annotate(week=TruncWeek('created_at'))
            .values('week').annotate(count=Count('id')).order_by('week')
        )

        return ctx


class SalesReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/sales_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        now = timezone.now()
        lead_qs = Lead.objects.filter(company=company) if company else Lead.objects.all()

        # Per-salesman performance
        ctx['salesman_performance'] = list(
            lead_qs.filter(status='active', current_salesman__isnull=False)
            .values(salesman_name=F('current_salesman__email'))
            .annotate(
                total=Count('id'),
                active=Count('id', filter=Q(status='active')),
            )
            .order_by('-total')[:20]
        )

        # Per-source lead counts
        ctx['source_breakdown'] = list(
            lead_qs.values(source_name=F('source__name'))
            .annotate(count=Count('id')).order_by('-count')
        )

        # Stage conversion funnel
        ctx['stage_funnel'] = list(
            lead_qs.filter(status='active')
            .values(stage_name=F('current_stage__name'), stage_order=F('current_stage__sort_order'))
            .annotate(count=Count('id')).order_by('stage_order')
        )

        # Follow-up/Meeting summary this month
        followup_qs = LeadFollowUp.objects.filter(lead__company=company) if company else LeadFollowUp.objects.all()
        ctx['followups_this_month'] = followup_qs.filter(created_at__month=now.month, created_at__year=now.year).count()
        ctx['followups_pending'] = followup_qs.filter(status='pending').count()

        meeting_qs = Meeting.objects.filter(lead__company=company) if company else Meeting.objects.all()
        ctx['meetings_this_month'] = meeting_qs.filter(created_at__month=now.month, created_at__year=now.year).count()
        ctx['meetings_completed'] = meeting_qs.filter(status='completed').count()

        # SLA compliance: % of satisfied vs total expired+satisfied
        sla_qs = LeadSLAInstance.objects.filter(lead__company=company) if company else LeadSLAInstance.objects.all()
        total_resolved = sla_qs.filter(status__in=['satisfied', 'expired', 'processed']).count()
        satisfied = sla_qs.filter(status='satisfied').count()
        ctx['sla_compliance_rate'] = round(satisfied / total_resolved * 100, 1) if total_resolved else 0

        # Assignment distribution this month
        ctx['assignments_this_month'] = list(
            LeadAssignment.objects.filter(
                lead__company=company, created_at__month=now.month, created_at__year=now.year,
            ).values(type=F('assignment_type'))
            .annotate(count=Count('id')).order_by('-count')
        ) if company else []

        return ctx


class MarketingReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/marketing_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        camp_qs = Campaign.objects.filter(company=company, is_archived=False) if company else Campaign.objects.filter(is_archived=False)

        # Campaign overview
        ctx['total_campaigns'] = camp_qs.count()
        ctx['active_campaigns'] = camp_qs.filter(lifecycle_status_cache='active').count()
        ctx['budget_total'] = camp_qs.aggregate(total=Sum('total_budget'))['total'] or 0
        ctx['budget_approved'] = camp_qs.filter(approval_status='approved').aggregate(total=Sum('total_budget'))['total'] or 0

        # Per-campaign KPIs
        ctx['campaign_kpis'] = list(
            CampaignKPIResult.objects.filter(campaign__company=company)
            .values(campaign_name=F('campaign__name'), metric=F('metric_code'))
            .annotate(total_value=Sum('metric_value'))
            .order_by('campaign_name', 'metric')
        ) if company else []

        # Top campaigns by lead count
        ctx['top_campaigns'] = list(
            camp_qs.annotate(
                lead_count=Count('lead_attributions'),
                total_budget_val=F('total_budget'),
            ).order_by('-lead_count')[:10]
        )

        # Leads per source from campaigns
        ctx['campaign_source_leads'] = list(
            LeadCampaignAttribution.objects.filter(campaign__company=company)
            .values(campaign_type_label=F('campaign_type'))
            .annotate(count=Count('id')).order_by('-count')
        ) if company else []

        # Platform performance (social media)
        ctx['platform_performance'] = list(
            LeadCampaignAttribution.objects.filter(campaign__company=company)
            .exclude(platform='')
            .values('platform')
            .annotate(leads=Count('id')).order_by('-leads')
        ) if company else []

        return ctx


class FinanceReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/finance_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        camp_qs = Campaign.objects.filter(company=company, is_archived=False) if company else Campaign.objects.filter(is_archived=False)

        # Budget summary by approval status
        ctx['budget_by_approval'] = list(
            camp_qs.values('approval_status')
            .annotate(total=Sum('total_budget'), count=Count('id'))
            .order_by('-total')
        )

        # Monthly spend trend (budget of campaigns that started each month)
        ctx['monthly_spend'] = list(
            camp_qs.annotate(month=TruncMonth('start_date'))
            .values('month').annotate(budget=Sum('total_budget'))
            .order_by('month')
        )

        # Pending approvals detail
        ctx['pending_campaigns'] = list(
            camp_qs.filter(approval_status='pending')
            .values('id', 'name', 'total_budget', 'start_date', 'end_date')
            .order_by('-total_budget')
        )

        # Average cost per lead across all approved campaigns
        approved = camp_qs.filter(approval_status='approved')
        ctx['avg_cost_per_lead'] = CampaignKPIResult.objects.filter(
            campaign__in=approved, metric_code='cost_per_lead',
        ).aggregate(avg=Avg('metric_value'))['avg'] or 0

        # Finance queue (semi_approved + not_approved)
        ctx['review_queue'] = list(
            camp_qs.filter(approval_status__in=['semi_approved', 'not_approved'])
            .values('id', 'name', 'total_budget', 'approval_status')
            .order_by('-updated_at')[:20]
        )

        return ctx
