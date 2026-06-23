from django.db.models import Count
from apps.accounts.models import SalesProfile, Team
from apps.distribution.models import RotationPointer

def get_eligible_sales_profiles(company, team=None, language=None):
    """Retrieves available sales profiles scoped to a company and optionally team/language."""
    qs = SalesProfile.objects.select_related('user').filter(company=company, is_available=True, user__is_active=True)
    if team:
        qs = qs.filter(user__team_memberships__team=team, user__team_memberships__is_active=True)
    if language:
        qs = qs.filter(languages=language)
    return qs.distinct()

def get_least_busy_team(company):
    """Retrieves the team with the minimum active leads count."""
    return Team.objects.filter(company=company, is_active=True).annotate(
        active_leads=Count('current_leads')
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
