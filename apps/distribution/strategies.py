from dataclasses import dataclass
from typing import Optional
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from apps.accounts.models import SalesProfile, Team
from apps.leads.models import LeadAssignment
from apps.distribution.models import RotationPointer, AssignmentAttempt


@dataclass
class AssignmentResult:
    lead: object
    team: Optional[Team]
    salesman: object | None
    strategy_code: str
    assignment_type: str = 'automatic'
    reason: str = ''


class DistributionStrategy:
    code = 'base'
    name = 'Base Strategy'

    def assign(self, *, lead, actor=None, scope_mode='all_salesmen', team=None, language=None, **kwargs) -> AssignmentResult:
        raise NotImplementedError

    def eligible_sales_profiles(self, *, lead, team=None, language=None):
        from apps.distribution.selectors import get_eligible_sales_profiles
        language = language or lead.language
        return get_eligible_sales_profiles(lead.company, team=team, language=language)

    def persist_assignment(self, *, lead, result: AssignmentResult, actor=None):
        LeadAssignment.objects.filter(lead=lead, is_current=True).update(is_current=False)
        assignment = LeadAssignment.objects.create(
            lead=lead,
            team=result.team,
            salesman=result.salesman,
            assignment_type=result.assignment_type,
            strategy_code=result.strategy_code,
            assigned_by=actor,
            reason=result.reason,
        )
        lead.current_team = result.team
        lead.current_salesman = result.salesman
        lead.save(update_fields=['current_team', 'current_salesman', 'updated_at'])
        if result.salesman and hasattr(result.salesman, 'sales_profile'):
            profile = result.salesman.sales_profile
            profile.last_received_lead_at = timezone.now()
            profile.active_lead_count_cache = max(0, profile.user.current_leads.filter(status='active').count())
            profile.save(update_fields=['last_received_lead_at', 'active_lead_count_cache', 'updated_at'])

        # Cancel any active distribution attempts if this is a manual or non-retry assignment
        if result.strategy_code != 'retry_team_escalation':
            lead.assignment_attempts.filter(status='active').update(
                status='skipped', ended_at=timezone.now()
            )
        return assignment


class RoundRobinLoadBalancedStrategy(DistributionStrategy):
    code = 'round_robin_load_balanced'
    name = 'Round Robin Load Balanced'

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='all_salesmen', team=None, language=None, **kwargs):
        selected_team = team
        if scope_mode in ('team_then_salesman', 'team_then_sales_head') and selected_team is None:
            from apps.distribution.selectors import get_least_busy_team
            selected_team = get_least_busy_team(lead.company)
        if scope_mode == 'team_then_sales_head':
            result = AssignmentResult(lead=lead, team=selected_team, salesman=None, strategy_code=self.code, reason='Assigned to team; Sales Head decides.')
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result
        
        from django.db.models import F
        candidates = self.eligible_sales_profiles(lead=lead, team=selected_team, language=language)
        candidates = candidates.order_by(
            'active_lead_count_cache',
            F('last_received_lead_at').asc(nulls_first=True),
            'user__date_joined'
        )
        profile = candidates.first()
        if not profile:
            raise ValueError('No eligible salesman found for lead distribution.')
        result = AssignmentResult(lead=lead, team=selected_team, salesman=profile.user, strategy_code=self.code, reason='Fewest active leads; earliest last received lead tie-break.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class ByTurnSequentialStrategy(DistributionStrategy):
    code = 'by_turn'
    name = 'By Turn Sequential'

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='all_salesmen', team=None, language=None, **kwargs):
        selected_team = team
        if scope_mode in ('team_then_salesman', 'team_then_sales_head') and selected_team is None:
            from apps.distribution.selectors import get_active_teams, get_rotation_pointer_for_update
            teams = list(get_active_teams(lead.company))
            if not teams:
                raise ValueError('No active teams available.')
            pointer = get_rotation_pointer_for_update(lead.company, self.code, 'teams')
            selected_team = teams[pointer.position % len(teams)]
            pointer.position = (pointer.position + 1) % len(teams)
            pointer.last_team = selected_team
            pointer.save(update_fields=['position', 'last_team', 'updated_at'])
        if scope_mode == 'team_then_sales_head':
            result = AssignmentResult(lead=lead, team=selected_team, salesman=None, strategy_code=self.code, reason='Sequential team rotation; Sales Head decides.')
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result

        # Get all sales profiles for company/team to keep the index stable
        all_profiles = SalesProfile.objects.select_related('user').filter(company=lead.company)
        if selected_team:
            all_profiles = all_profiles.filter(user__team_memberships__team=selected_team, user__team_memberships__is_active=True)
        all_profiles = list(all_profiles.order_by('user__email'))

        if not all_profiles:
            raise ValueError('No sales profiles found for sequential distribution.')

        from apps.distribution.selectors import get_rotation_pointer_for_update
        pointer = get_rotation_pointer_for_update(lead.company, self.code, scope_mode, team=selected_team)
        attempts = 0
        profile = None
        while attempts < len(all_profiles):
            candidate = all_profiles[pointer.position % len(all_profiles)]
            # Advance position in pointer
            pointer.position = (pointer.position + 1) % len(all_profiles)
            
            # Check eligibility: is active, available, language matches, and workload limit not exceeded
            is_active = candidate.user.is_active
            is_available = candidate.is_available
            matches_lang = (not language) or candidate.languages.filter(pk=language.pk).exists()
            limit_ok = (candidate.max_active_leads is None) or (candidate.active_lead_count_cache < candidate.max_active_leads)
            
            if is_active and is_available and matches_lang and limit_ok:
                profile = candidate
                break
            attempts += 1

        if not profile:
            raise ValueError('No eligible salesman found for sequential distribution.')

        pointer.last_user = profile.user
        pointer.save(update_fields=['position', 'last_user', 'updated_at'])
        result = AssignmentResult(lead=lead, team=selected_team, salesman=profile.user, strategy_code=self.code, reason='Fixed sequential rotation.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class ManualAssignmentStrategy(DistributionStrategy):
    code = 'manual_assignment'
    name = 'Manual Assignment'

    def assign(self, *, lead, actor=None, scope_mode='manual', team=None, salesman=None, **kwargs):
        from apps.permissions_engine.services.engine import PermissionEngine
        
        # Validate actor permission
        if actor and not actor.is_superuser and not actor.is_staff:
            if not (PermissionEngine.has_perm(actor, 'leads.assign_lead_manual') or PermissionEngine.has_perm(actor, 'distribution.run_manual_distribution')):
                raise ValueError("Actor does not have permission to manually assign leads.")

        # Validate team
        if team:
            if team.company != lead.company:
                raise ValueError("Team must belong to the same company as the lead.")
            if not team.is_active:
                raise ValueError("Team must be active.")

        # Validate salesman
        if salesman:
            if not hasattr(salesman, 'sales_profile') or salesman.sales_profile.company != lead.company:
                raise ValueError("Salesman must belong to the same company as the lead.")
            if not salesman.is_active:
                raise ValueError("Salesman must be active.")
            
            # Validate team membership
            if team:
                if not salesman.team_memberships.filter(team=team, is_active=True).exists():
                    raise ValueError(f"Salesman {salesman.email} is not an active member of team {team.name}.")
            
            # Validate language match
            if lead.language:
                if not salesman.sales_profile.languages.filter(pk=lead.language.pk).exists():
                    raise ValueError(f"Salesman {salesman.email} does not support language {lead.language.name}.")

        result = AssignmentResult(lead=lead, team=team, salesman=salesman, strategy_code=self.code, assignment_type='manual', reason='Manual assignment by authorized user.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class RetryTeamEscalationStrategy(ByTurnSequentialStrategy):
    code = 'retry_team_escalation'
    name = 'Retry Attempts and Team Escalation'

    def _attempt_due_at(self, lead):
        from apps.core.services.policies import PolicyResolver
        return timezone.now() + PolicyResolver.get_retry_attempt_window(lead.company)

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='team_then_salesman', team=None, language=None, **kwargs):
        from apps.leads.models import Lead
        # Acquire row lock on lead to prevent concurrency race conditions during retry cycle updates
        lead = Lead.objects.select_for_update().get(pk=lead.pk)
        
        from apps.core.services.policies import PolicyResolver
        from apps.distribution.selectors import get_last_assignment_attempt
        
        # Verify lead.origin != 'broker'
        if lead.origin == 'broker':
            raise ValueError("Broker escalation must be manual.")

        n = max(1, PolicyResolver.get_int(lead.company, 'retry_attempts_per_team', default=3))
        
        last_attempt = get_last_assignment_attempt(lead)
        
        # Scenario 1: Initial assignment (no previous attempts)
        if not last_attempt:
            # Seed attempt 1 from the currently assigned salesman on SLA expiry
            if lead.current_salesman:
                selected_team = lead.current_team
                salesman = lead.current_salesman
            else:
                selected_team = team
                if scope_mode in ('team_then_salesman', 'team_then_sales_head') and selected_team is None:
                    from apps.distribution.selectors import get_active_teams, get_rotation_pointer_for_update
                    teams = list(get_active_teams(lead.company))
                    if not teams:
                        raise ValueError('No active teams available for distribution.')
                    pointer = get_rotation_pointer_for_update(lead.company, self.code, 'teams')
                    selected_team = teams[pointer.position % len(teams)]
                    pointer.position = (pointer.position + 1) % len(teams)
                    pointer.last_team = selected_team
                    pointer.save(update_fields=['position', 'last_team', 'updated_at'])
                else:
                    from apps.distribution.selectors import get_active_teams
                    selected_team = selected_team or get_active_teams(lead.company).first()
                
                candidates = list(self.eligible_sales_profiles(lead=lead, team=selected_team, language=language).order_by('user__email'))
                if not candidates:
                    raise ValueError(f'No available salesman in team {selected_team.name if selected_team else "None"}.')
                salesman = candidates[0].user
            
            # Create attempt 1
            new_attempt = AssignmentAttempt.objects.create(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                attempt_no=1,
                status='active',
                due_at=self._attempt_due_at(lead)
            )
            result = AssignmentResult(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                strategy_code=self.code,
                assignment_type='automatic',
                reason=f"Initial retry team escalation routing: Team {selected_team.name if selected_team else 'None'}, Salesman {salesman.email} (Attempt 1)"
            )
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result
            
        # Scenario 2: Active or expired attempt exists
        else:
            # Mark previous attempt as ended if not already done
            if last_attempt.status == 'active':
                last_attempt.status = 'expired'
                last_attempt.ended_at = timezone.now()
                last_attempt.save(update_fields=['status', 'ended_at', 'updated_at'])
                
            # If current attempt number is less than allowed limit, try next salesman in same team
            if last_attempt.attempt_no < n:
                candidates = list(self.eligible_sales_profiles(lead=lead, team=last_attempt.team, language=language).order_by('user__email'))
                if not candidates:
                    # No salesmen available, trigger escalation to next team
                    last_attempt.attempt_no = n # Force escalation trigger in the next block
                else:
                    # Find next sequential salesman in same team.
                    next_salesman = None
                    if last_attempt.salesman:
                        for cand in candidates:
                            if cand.user.email > last_attempt.salesman.email:
                                next_salesman = cand.user
                                break
                    if not next_salesman:
                        next_salesman = candidates[0].user
                        
                    new_attempt = AssignmentAttempt.objects.create(
                        lead=lead,
                        team=last_attempt.team,
                        salesman=next_salesman,
                        attempt_no=last_attempt.attempt_no + 1,
                        status='active',
                        due_at=self._attempt_due_at(lead)
                    )
                    result = AssignmentResult(
                        lead=lead,
                        team=last_attempt.team,
                        salesman=next_salesman,
                        strategy_code=self.code,
                        assignment_type='retry',
                        reason=f"Retry sequential assignment: Team {last_attempt.team.name}, Salesman {next_salesman.email} (Attempt {new_attempt.attempt_no})"
                    )
                    self.persist_assignment(lead=lead, result=result, actor=actor)
                    return result
            
            # Scenario 3: Attempts exceeded or no salesman available, escalate to next team
            from apps.distribution.selectors import get_active_teams, get_rotation_pointer_for_update
            teams = list(get_active_teams(lead.company))
            if not teams:
                raise ValueError('No active teams available for escalation.')
                
            # Rotate to next team sequentially, skipping teams with no available salesmen
            next_team_idx = 0
            for idx, t in enumerate(teams):
                if t == last_attempt.team:
                    next_team_idx = (idx + 1) % len(teams)
                    break
            
            selected_team = None
            candidates = []
            attempts_teams = 0
            while attempts_teams < len(teams):
                team_to_try = teams[(next_team_idx + attempts_teams) % len(teams)]
                cands = list(self.eligible_sales_profiles(lead=lead, team=team_to_try, language=language).order_by('user__email'))
                if cands:
                    selected_team = team_to_try
                    candidates = cands
                    next_team_idx = (next_team_idx + attempts_teams) % len(teams)
                    break
                attempts_teams += 1
                
            if not selected_team:
                raise ValueError('No active teams with available salesmen for escalation.')
                
            pointer = get_rotation_pointer_for_update(lead.company, self.code, 'teams')
            pointer.position = (next_team_idx + 1) % len(teams)
            pointer.last_team = selected_team
            pointer.save(update_fields=['position', 'last_team', 'updated_at'])
            
            salesman = candidates[0].user
            
            new_attempt = AssignmentAttempt.objects.create(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                attempt_no=1,
                status='active',
                due_at=self._attempt_due_at(lead)
            )
            result = AssignmentResult(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                strategy_code=self.code,
                assignment_type='escalation',
                reason=f"Escalated to next team: Team {selected_team.name}, Salesman {salesman.email} (Attempt 1)"
            )
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result


class WalkInOpenFloorStrategy(DistributionStrategy):
    """Policy 1 – Open Floor: any available salesman from any team may meet the walk-in lead."""
    code = 'walkin_open_floor'
    name = 'Walk-in – Open Floor (Any Available Salesman)'

    def assign(self, *, lead, actor=None, scope_mode='all_salesmen', team=None, language=None, salesman=None, **kwargs):
        if salesman:
            result = AssignmentResult(lead=lead, team=team, salesman=salesman, strategy_code=self.code, assignment_type='manual', reason='Walk-in open floor – receptionist selected salesman.')
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result
        candidates = self.eligible_sales_profiles(lead=lead, team=None, language=language).order_by('active_lead_count_cache', 'last_received_lead_at')
        profile = candidates.first()
        if not profile:
            raise ValueError('No available salesman found for walk-in (open floor).')
        result = AssignmentResult(lead=lead, team=None, salesman=profile.user, strategy_code=self.code, reason='Walk-in open floor – assigned to least busy available salesman.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class WalkInTeamTurnStrategy(DistributionStrategy):
    """Policy 2 – Team Turn: sequential team rotation; the Sales Head of the selected team manually assigns."""
    code = 'walkin_team_turn'
    name = 'Walk-in – Team Turn (Sales Head Assigns)'

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='team_then_sales_head', team=None, language=None, salesman=None, **kwargs):
        from apps.distribution.selectors import get_active_teams, get_rotation_pointer_for_update
        teams = list(get_active_teams(lead.company))
        if not teams:
            raise ValueError('No active teams available for walk-in team turn.')
        pointer = get_rotation_pointer_for_update(lead.company, self.code, 'walkin_teams')
        attempts = 0
        selected_team = None
        while attempts < len(teams):
            candidate_team = teams[pointer.position % len(teams)]
            pointer.position = (pointer.position + 1) % len(teams)
            has_available = self.eligible_sales_profiles(lead=lead, team=candidate_team, language=language).exists()
            if has_available:
                selected_team = candidate_team
                break
            attempts += 1
        if not selected_team:
            raise ValueError('No team has available salesmen for walk-in (team turn).')
        pointer.last_team = selected_team
        pointer.save(update_fields=['position', 'last_team', 'updated_at'])

        if salesman:
            result = AssignmentResult(lead=lead, team=selected_team, salesman=salesman, strategy_code=self.code, assignment_type='manual', reason=f'Walk-in team turn – team {selected_team.name}, salesman selected by Sales Head.')
        else:
            result = AssignmentResult(lead=lead, team=selected_team, salesman=None, strategy_code=self.code, reason=f'Walk-in team turn – assigned to team {selected_team.name}; Sales Head decides salesman.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class WalkInFullRotationStrategy(DistributionStrategy):
    """Policy 3 – Full Rotation: single sequential rotation across all salesmen company-wide."""
    code = 'walkin_full_rotation'
    name = 'Walk-in – Full Rotation (All Salesmen)'

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='all_salesmen', team=None, language=None, **kwargs):
        candidates = list(self.eligible_sales_profiles(lead=lead, team=None, language=language).order_by('user__email'))
        if not candidates:
            raise ValueError('No eligible salesman found for walk-in full rotation.')
        from apps.distribution.selectors import get_rotation_pointer_for_update
        pointer = get_rotation_pointer_for_update(lead.company, self.code, 'walkin_all')
        attempts = 0
        profile = None
        while attempts < len(candidates):
            candidate = candidates[pointer.position % len(candidates)]
            pointer.position = (pointer.position + 1) % len(candidates)
            if candidate.is_available and candidate.user.is_active:
                profile = candidate
                break
            attempts += 1
        if not profile:
            raise ValueError('No available salesman found in walk-in full rotation.')
        pointer.last_user = profile.user
        pointer.save(update_fields=['position', 'last_user', 'updated_at'])
        team_of_salesman = profile.user.team_memberships.filter(is_active=True).values_list('team', flat=True).first()
        assigned_team = Team.objects.filter(pk=team_of_salesman).first() if team_of_salesman else None
        result = AssignmentResult(lead=lead, team=assigned_team, salesman=profile.user, strategy_code=self.code, reason='Walk-in full rotation – sequential assignment across all salesmen.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result
