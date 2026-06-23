from django.db.models import Count, Q
from apps.accounts.models import SalesProfile, Team
from apps.distribution.models import RotationPointer

def get_eligible_sales_profiles(company, team=None, language=None):
    """Retrieves available sales profiles scoped to a company and optionally team/language."""
    qs = SalesProfile.objects.select_related('user').filter(company=company, is_available=True, user__is_active=True)
    from django.db.models import F
    qs = qs.filter(
        Q(max_active_leads__isnull=True) | Q(active_lead_count_cache__lt=F('max_active_leads'))
    )
    if team:
        qs = qs.filter(user__team_memberships__team=team, user__team_memberships__is_active=True)
    if language:
        qs = qs.filter(languages=language)
    return qs.distinct()

def get_least_busy_team(company):
    """Retrieves the team with the minimum active leads count."""
    return Team.objects.filter(company=company, is_active=True).annotate(
        active_leads=Count('current_leads', filter=Q(current_leads__status='active'))
    ).order_by('active_leads', 'sort_order', 'name').first()

def get_active_teams(company):
    """Retrieves all active teams scoped to a company."""
    return Team.objects.filter(company=company, is_active=True).order_by('sort_order', 'name')

def get_rotation_pointer_for_update(company, strategy_code, scope_mode, team=None):
    """Retrieves or creates a rotation pointer for update (row lock)."""
    pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
        company=company,
        strategy_code=strategy_code,
        scope_mode=scope_mode,
        team=team,
        defaults={'position': 0},
    )
    return pointer

def get_last_assignment_attempt(lead):
    """Retrieves the most recent assignment attempt for a lead."""
    return lead.assignment_attempts.order_by('-attempt_no').first()


def resolve_distribution_language(lead):
    """Resolve the language used to filter the eligible salesman pool.

    Doc 1 §3.2.3: the automatic distribution language pre-check defaults to the
    company default language (Arabic) when the lead has no explicit language.
    The default is only applied when at least one available salesman actually
    supports it, so distribution never empties the pool for companies that have
    not configured salesman languages yet.
    """
    if lead.language:
        return lead.language
    from apps.companies.models import Language
    default = Language.objects.filter(company=lead.company, is_default=True, is_active=True).first()
    if default and SalesProfile.objects.filter(
        company=lead.company, is_available=True, user__is_active=True, languages=default,
    ).exists():
        return default
    return None
