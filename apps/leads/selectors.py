from django.db.models import Q
from apps.leads.models import Lead, LeadSource, LeadStage, HowDidYouKnowOption
from apps.accounts.models import User, Team, BrokerProfile
from apps.companies.models import Language
from apps.marketing.models import Campaign
from apps.permissions_engine.services.engine import PermissionEngine

def get_leads_list(company, search_query=None, stage_id=None, source_id=None, status=None, user=None):
    """
    Retrieves and filters Lead records scoped to a company, with select_related/prefetch_related.
    """
    qs = Lead.objects.select_related('source', 'current_stage', 'current_salesman', 'current_team', 'campaign').all()
    
    if not user or not user.is_superuser:
        if company:
            qs = qs.filter(company=company)
        else:
            qs = qs.none()
            
    if search_query:
        qs = qs.filter(Q(full_name__icontains=search_query) | Q(phone_number__icontains=search_query))
    if stage_id:
        qs = qs.filter(current_stage_id=stage_id)
    if source_id:
        qs = qs.filter(source_id=source_id)
    if status:
        qs = qs.filter(status=status)
        
    if user:
        if PermissionEngine.has_perm(user, 'leads.view_all'):
            return qs.distinct()
        if PermissionEngine.has_perm(user, 'leads.view_team'):
            return qs.filter(current_team__memberships__user=user).distinct()
        if hasattr(user, 'broker_profile') and user.broker_profile.is_active:
            return qs.filter(broker=user.broker_profile).distinct()
        return qs.filter(current_salesman=user).distinct()
        
    return qs.distinct()

def get_lead_by_id(company, lead_id):
    """Retrieves a single lead scoped to a company."""
    if company:
        return Lead.objects.filter(company=company, pk=lead_id).first()
    return Lead.objects.filter(pk=lead_id).first()

def get_lead_stages(company):
    """Retrieves lead stages scoped to a company."""
    if company:
        return LeadStage.objects.filter(company=company)
    return LeadStage.objects.all()

def get_lead_sources(company):
    """Retrieves lead sources scoped to a company."""
    if company:
        return LeadSource.objects.filter(company=company)
    return LeadSource.objects.all()

def get_how_options(company):
    """Retrieves HowDidYouKnowOption scoped to a company."""
    if company:
        return HowDidYouKnowOption.objects.filter(company=company)
    return HowDidYouKnowOption.objects.all()

def get_languages(company):
    """Retrieves Language scoped to a company."""
    if company:
        return Language.objects.filter(company=company)
    return Language.objects.all()

def get_brokers(company):
    """Retrieves BrokerProfile scoped to a company."""
    if company:
        return BrokerProfile.objects.filter(company=company)
    return BrokerProfile.objects.all()

def get_campaigns(company):
    """Retrieves Campaign scoped to a company."""
    if company:
        return Campaign.objects.filter(company=company)
    return Campaign.objects.all()

def get_teams(company):
    """Retrieves Team scoped to a company."""
    if company:
        return Team.objects.filter(company=company)
    return Team.objects.all()

def get_salesmen(company):
    """Retrieves active salesmen scoped to a company."""
    if company:
        return User.objects.filter(company=company, is_active=True, sales_profile__isnull=False)
    return User.objects.filter(is_active=True, sales_profile__isnull=False)

def get_duplicate_lead_for_existing_client(company, existing_phone, exclude_lead_id=None):
    """Checks for duplicate lead for existing client phone."""
    from apps.leads.services.leads import normalize_phone
    qs = Lead.objects.filter(
        company=company,
        normalized_phone=normalize_phone('+20', existing_phone)
    )
    if exclude_lead_id:
        qs = qs.exclude(pk=exclude_lead_id)
    return qs.order_by('-created_at').select_related('current_salesman').first()

def get_leads_report_queryset(company):
    """Retrieves lead report base query scoped to company."""
    qs = Lead.objects.all()
    if company:
        qs = qs.filter(company=company)
    return qs

def get_lead_stage_distribution(company):
    """Retrieves lead stage distribution count for active leads."""
    from django.db.models import Count, F
    qs = get_leads_report_queryset(company)
    return list(
        qs.filter(status='active')
        .values(stage_name=F('current_stage__name'))
        .annotate(count=Count('id'))
        .order_by('-count')
    )

def get_lead_trend(company, start_date):
    """Retrieves weekly lead trend counts."""
    from django.db.models import Count
    from django.db.models.functions import TruncWeek
    qs = get_leads_report_queryset(company)
    return list(
        qs.filter(created_at__gte=start_date)
        .annotate(week=TruncWeek('created_at'))
        .values('week')
        .annotate(count=Count('id'))
        .order_by('week')
    )

def get_salesman_performance(company):
    """Retrieves salesmen active lead statistics."""
    from django.db.models import Count, F, Q
    qs = get_leads_report_queryset(company)
    return list(
        qs.filter(status='active', current_salesman__isnull=False)
        .values(salesman_name=F('current_salesman__email'))
        .annotate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
        )
        .order_by('-total')[:20]
    )

def get_lead_source_breakdown(company):
    """Retrieves leads count breakdown by source."""
    from django.db.models import Count, F
    qs = get_leads_report_queryset(company)
    return list(
        qs.values(source_name=F('source__name'))
        .annotate(count=Count('id'))
        .order_by('-count')
    )

def get_lead_stage_funnel(company):
    """Retrieves funnel lead counts per stage."""
    from django.db.models import Count, F
    qs = get_leads_report_queryset(company)
    return list(
        qs.filter(status='active')
        .values(stage_name=F('current_stage__name'), stage_order=F('current_stage__sort_order'))
        .annotate(count=Count('id'))
        .order_by('stage_order')
    )

def get_lead_followups_queryset(company):
    """Retrieves follow-up records query scoped to company."""
    from apps.leads.models import LeadFollowUp
    qs = LeadFollowUp.objects.all()
    if company:
        qs = qs.filter(lead__company=company)
    return qs

def get_meetings_queryset(company):
    """Retrieves meetings query scoped to company."""
    from apps.leads.models import Meeting
    qs = Meeting.objects.all()
    if company:
        qs = qs.filter(lead__company=company)
    return qs

def get_assignments_this_month(company, year, month):
    """Retrieves lead assignments breakdown for current month."""
    from apps.leads.models import LeadAssignment
    from django.db.models import Count, F
    if not company:
        return []
    return list(
        LeadAssignment.objects.filter(
            lead__company=company,
            created_at__month=month,
            created_at__year=year,
        )
        .values(type=F('assignment_type'))
        .annotate(count=Count('id'))
        .order_by('-count')
    )

