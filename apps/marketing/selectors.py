from apps.marketing.models import Campaign, CampaignTypeSelection, CampaignEvent, SocialMediaAd, ExhibitionRecord

def get_campaigns_list(company, search_query=None, status=None, approval=None):
    """Retrieves list of active campaigns scoped to a company."""
    qs = Campaign.objects.filter(is_archived=False).select_related('company').prefetch_related('type_selections').order_by('-created_at')
    
    if company:
        qs = qs.filter(company=company)
        
    if search_query:
        qs = qs.filter(name__icontains=search_query)
    if status:
        qs = qs.filter(lifecycle_status_cache=status)
    if approval:
        qs = qs.filter(approval_status=approval)
        
    return qs

def get_campaign_by_id(company, campaign_id):
    """Retrieves a single campaign scoped to a company."""
    if company:
        return Campaign.objects.filter(company=company, pk=campaign_id).first()
    return Campaign.objects.filter(pk=campaign_id).first()

def get_campaign_with_budget_details(company, campaign_id):
    """Retrieves a campaign with all nested type lists prefetched."""
    qs = Campaign.objects.select_related('company').prefetch_related(
        'events', 'events__celebrities', 'events__giveaways', 'events__catering_items',
        'tv_ads', 'tv_ads__channels', 'tv_ads__slots',
        'street_ads', 'street_ads__type_lines', 'street_ads__type_lines__locations',
        'exhibitions', 'social_ads', 'social_ads__platform_lines', 'other_costs'
    )
    if company:
        qs = qs.filter(company=company)
    return qs.filter(pk=campaign_id).first()

def get_pending_approvals_list(company):
    """Retrieves campaigns awaiting finance approval scoped to a company."""
    qs = Campaign.objects.exclude(approval_status='approved').order_by('-created_at')
    if company:
        qs = qs.filter(company=company)
    return qs

def get_campaigns_report_queryset(company, include_archived=False):
    """Retrieves basic campaign queryset for reports."""
    qs = Campaign.objects.all()
    if not include_archived:
        qs = qs.filter(is_archived=False)
    if company:
        qs = qs.filter(company=company)
    return qs

def get_campaign_kpi_results(company):
    """Retrieves KPI metric values aggregated per campaign."""
    from apps.marketing.models import CampaignKPIResult
    from django.db.models import Sum, F
    if not company:
        return []
    return list(
        CampaignKPIResult.objects.filter(campaign__company=company)
        .values(campaign_name=F('campaign__name'), metric=F('metric_code'))
        .annotate(total_value=Sum('metric_value'))
        .order_by('campaign_name', 'metric')
    )

def get_top_campaigns(company, limit=10):
    """Retrieves campaigns with most lead attributions."""
    from django.db.models import Count, F
    qs = get_campaigns_report_queryset(company)
    return list(
        qs.annotate(
            lead_count=Count('lead_attributions'),
            total_budget_val=F('total_budget'),
        ).order_by('-lead_count')[:limit]
    )

def get_campaign_source_leads(company):
    """Retrieves campaign source leads distribution."""
    from apps.marketing.models import LeadCampaignAttribution
    from django.db.models import Count, F
    if not company:
        return []
    return list(
        LeadCampaignAttribution.objects.filter(campaign__company=company)
        .values(campaign_type_label=F('campaign_type'))
        .annotate(count=Count('id')).order_by('-count')
    )

def get_campaign_platform_performance(company):
    """Retrieves campaign platform performance lead counts."""
    from apps.marketing.models import LeadCampaignAttribution
    from django.db.models import Count
    if not company:
        return []
    return list(
        LeadCampaignAttribution.objects.filter(campaign__company=company)
        .exclude(platform='')
        .values('platform')
        .annotate(leads=Count('id')).order_by('-leads')
    )

def get_budget_by_approval(company):
    """Retrieves aggregated budget sums grouped by approval status."""
    from django.db.models import Sum, Count
    qs = get_campaigns_report_queryset(company)
    return list(
        qs.values('approval_status')
        .annotate(total=Sum('total_budget'), count=Count('id'))
        .order_by('-total')
    )

def get_monthly_spend(company):
    """Retrieves monthly budget totals based on start date."""
    from django.db.models import Sum
    from django.db.models.functions import TruncMonth
    qs = get_campaigns_report_queryset(company)
    return list(
        qs.annotate(month=TruncMonth('start_date'))
        .values('month').annotate(budget=Sum('total_budget'))
        .order_by('month')
    )

def get_pending_campaigns_detail(company):
    """Retrieves details of pending campaigns."""
    qs = get_campaigns_report_queryset(company)
    return list(
        qs.filter(approval_status='pending')
        .values('id', 'name', 'total_budget', 'start_date', 'end_date')
        .order_by('-total_budget')
    )

def get_average_cost_per_lead(company):
    """Retrieves aggregate average Cost Per Lead across approved campaigns."""
    from apps.marketing.models import CampaignKPIResult
    from django.db.models import Avg
    qs = get_campaigns_report_queryset(company)
    approved = qs.filter(approval_status='approved')
    return CampaignKPIResult.objects.filter(
        campaign__in=approved, metric_code='cost_per_lead',
    ).aggregate(avg=Avg('metric_value'))['avg'] or 0

def get_campaign_review_queue(company, limit=20):
    """Retrieves semi-approved or not-approved campaigns queue."""
    qs = get_campaigns_report_queryset(company)
    return list(
        qs.filter(approval_status__in=['semi_approved', 'not_approved'])
        .values('id', 'name', 'total_budget', 'approval_status')
        .order_by('-updated_at')[:limit]
    )

def get_total_campaign_budget(company):
    """Retrieves sum of budgets of all active campaigns."""
    from django.db.models import Sum
    return get_campaigns_report_queryset(company).aggregate(total=Sum('total_budget'))['total'] or 0

def get_approved_campaign_budget(company):
    """Retrieves sum of budgets of approved campaigns."""
    from django.db.models import Sum
    return get_campaigns_report_queryset(company).filter(approval_status='approved').aggregate(total=Sum('total_budget'))['total'] or 0


