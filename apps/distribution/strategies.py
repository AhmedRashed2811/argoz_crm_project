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
        qs = SalesProfile.objects.select_related('user').filter(company=lead.company, is_available=True, user__is_active=True)
        if team:
            qs = qs.filter(user__team_memberships__team=team, user__team_memberships__is_active=True)
        language = language or lead.language
        if language:
            qs = qs.filter(languages=language)
        return qs.distinct()

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
            selected_team = Team.objects.filter(company=lead.company, is_active=True).annotate(
                active_leads=Count('current_leads')
            ).order_by('active_leads', 'sort_order', 'name').first()
        if scope_mode == 'team_then_sales_head':
            result = AssignmentResult(lead=lead, team=selected_team, salesman=None, strategy_code=self.code, reason='Assigned to team; Sales Head decides.')
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result
        candidates = self.eligible_sales_profiles(lead=lead, team=selected_team, language=language).order_by('active_lead_count_cache', 'last_received_lead_at', 'user__date_joined')
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
            teams = list(Team.objects.filter(company=lead.company, is_active=True).order_by('sort_order', 'name'))
            if not teams:
                raise ValueError('No active teams available.')
            pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
                company=lead.company,
                strategy_code=self.code,
                scope_mode='teams',
                team=None,
                defaults={'position': 0},
            )
            selected_team = teams[pointer.position % len(teams)]
            pointer.position = (pointer.position + 1) % len(teams)
            pointer.last_team = selected_team
            pointer.save(update_fields=['position', 'last_team', 'updated_at'])
        if scope_mode == 'team_then_sales_head':
            result = AssignmentResult(lead=lead, team=selected_team, salesman=None, strategy_code=self.code, reason='Sequential team rotation; Sales Head decides.')
            self.persist_assignment(lead=lead, result=result, actor=actor)
            return result
        candidates = list(self.eligible_sales_profiles(lead=lead, team=selected_team, language=language).order_by('user__email'))
        if not candidates:
            raise ValueError('No eligible salesman found for sequential distribution.')
        pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
            company=lead.company,
            strategy_code=self.code,
            scope_mode=scope_mode,
            team=selected_team,
            defaults={'position': 0},
        )
        profile = candidates[pointer.position % len(candidates)]
        pointer.position = (pointer.position + 1) % len(candidates)
        pointer.last_user = profile.user
        pointer.save(update_fields=['position', 'last_user', 'updated_at'])
        result = AssignmentResult(lead=lead, team=selected_team, salesman=profile.user, strategy_code=self.code, reason='Fixed sequential rotation.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class ManualAssignmentStrategy(DistributionStrategy):
    code = 'manual_assignment'
    name = 'Manual Assignment'

    def assign(self, *, lead, actor=None, scope_mode='manual', team=None, salesman=None, **kwargs):
        result = AssignmentResult(lead=lead, team=team, salesman=salesman, strategy_code=self.code, assignment_type='manual', reason='Manual assignment by authorized user.')
        self.persist_assignment(lead=lead, result=result, actor=actor)
        return result


class RetryTeamEscalationStrategy(ByTurnSequentialStrategy):
    code = 'retry_team_escalation'
    name = 'Retry Attempts and Team Escalation'

    @transaction.atomic
    def assign(self, *, lead, actor=None, scope_mode='team_then_salesman', team=None, language=None, **kwargs):
        from apps.core.services.policies import PolicyResolver
        n = int(PolicyResolver.get(lead.company, 'retry_attempts_per_team', default=3))
        
        last_attempt = lead.assignment_attempts.order_by('-attempt_no').first()
        
        # Scenario 1: Initial assignment (no previous attempts)
        if not last_attempt:
            selected_team = team
            if scope_mode in ('team_then_salesman', 'team_then_sales_head') and selected_team is None:
                teams = list(Team.objects.filter(company=lead.company, is_active=True).order_by('sort_order', 'name'))
                if not teams:
                    raise ValueError('No active teams available for distribution.')
                pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
                    company=lead.company,
                    strategy_code=self.code,
                    scope_mode='teams',
                    team=None,
                    defaults={'position': 0},
                )
                selected_team = teams[pointer.position % len(teams)]
                pointer.position = (pointer.position + 1) % len(teams)
                pointer.last_team = selected_team
                pointer.save(update_fields=['position', 'last_team', 'updated_at'])
            else:
                selected_team = selected_team or Team.objects.filter(company=lead.company, is_active=True).first()
            
            # Select the first salesman sequentially in the selected team
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
                due_at=timezone.now()
            )
            result = AssignmentResult(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                strategy_code=self.code,
                assignment_type='automatic',
                reason=f"Initial retry team escalation routing: Team {selected_team.name}, Salesman {salesman.email} (Attempt 1)"
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
                    # Find next sequential salesman in same team
                    next_salesman = None
                    for idx, cand in enumerate(candidates):
                        if cand.user == last_attempt.salesman:
                            next_salesman = candidates[(idx + 1) % len(candidates)].user
                            break
                    if not next_salesman:
                        next_salesman = candidates[0].user
                        
                    new_attempt = AssignmentAttempt.objects.create(
                        lead=lead,
                        team=last_attempt.team,
                        salesman=next_salesman,
                        attempt_no=last_attempt.attempt_no + 1,
                        status='active',
                        due_at=timezone.now()
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
            teams = list(Team.objects.filter(company=lead.company, is_active=True).order_by('sort_order', 'name'))
            if not teams:
                raise ValueError('No active teams available for escalation.')
                
            # Rotate to next team sequentially
            pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
                company=lead.company,
                strategy_code=self.code,
                scope_mode='teams',
                team=None,
                defaults={'position': 0},
            )
            next_team_idx = 0
            for idx, t in enumerate(teams):
                if t == last_attempt.team:
                    next_team_idx = (idx + 1) % len(teams)
                    break
            selected_team = teams[next_team_idx]
            pointer.position = (next_team_idx + 1) % len(teams)
            pointer.last_team = selected_team
            pointer.save(update_fields=['position', 'last_team', 'updated_at'])
            
            candidates = list(self.eligible_sales_profiles(lead=lead, team=selected_team, language=language).order_by('user__email'))
            if not candidates:
                raise ValueError(f'No available salesman in escalated team {selected_team.name}.')
            salesman = candidates[0].user
            
            new_attempt = AssignmentAttempt.objects.create(
                lead=lead,
                team=selected_team,
                salesman=salesman,
                attempt_no=1,
                status='active',
                due_at=timezone.now()
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
        teams = list(Team.objects.filter(company=lead.company, is_active=True).order_by('sort_order', 'name'))
        if not teams:
            raise ValueError('No active teams available for walk-in team turn.')
        pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
            company=lead.company, strategy_code=self.code, scope_mode='walkin_teams', team=None,
            defaults={'position': 0},
        )
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
        pointer, _ = RotationPointer.objects.select_for_update().get_or_create(
            company=lead.company, strategy_code=self.code, scope_mode='walkin_all', team=None,
            defaults={'position': 0},
        )
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
