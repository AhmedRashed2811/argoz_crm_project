from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib import messages
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from .models import ManualDistributionRequest
from .services.distribution import ManualDistributionService
from .selectors import get_eligible_sales_profiles, get_active_teams
from apps.accounts.models import User, Team


class ManualDistributionListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = ManualDistributionRequest
    template_name = 'distribution/manual_list.html'
    context_object_name = 'requests'
    permission_required = 'distribution.run_manual_distribution'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = ManualDistributionRequest.objects.filter(status='pending')
        if company:
            qs = qs.filter(company=company)
        return qs


class ManualDistributionDetailView(LoginRequiredMixin, CRMPermissionRequiredMixin, DetailView):
    model = ManualDistributionRequest
    template_name = 'distribution/manual_detail.html'
    context_object_name = 'request_obj'
    permission_required = 'distribution.run_manual_distribution'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = ManualDistributionRequest.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.object.company
        ctx['sales_profiles'] = get_eligible_sales_profiles(company)
        ctx['teams'] = get_active_teams(company)
        return ctx


class ManualDistributionAssignView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'distribution.run_manual_distribution'

    def post(self, request, pk):
        user = request.user
        company = user.company if not user.is_superuser else None
        if company:
            request_obj = get_object_or_404(ManualDistributionRequest, pk=pk, company=company)
        else:
            request_obj = get_object_or_404(ManualDistributionRequest, pk=pk)

        salesman_id = request.POST.get('salesman')
        team_id = request.POST.get('team')

        if not salesman_id:
            messages.error(request, "Salesman is required for assignment.")
            return redirect('distribution:detail', pk=pk)

        salesman = get_object_or_404(User, pk=salesman_id, company=request_obj.company)
        team = get_object_or_404(Team, pk=team_id, company=request_obj.company) if team_id else None

        try:
            ManualDistributionService.assign_request(
                request_obj=request_obj,
                salesman=salesman,
                team=team,
                actor=user
            )
            messages.success(request, f"Lead successfully assigned to {salesman.email}.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

        return redirect('distribution:list')


class ManualDistributionIgnoreView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'distribution.run_manual_distribution'

    def post(self, request, pk):
        user = request.user
        company = user.company if not user.is_superuser else None
        if company:
            request_obj = get_object_or_404(ManualDistributionRequest, pk=pk, company=company)
        else:
            request_obj = get_object_or_404(ManualDistributionRequest, pk=pk)

        reason = request.POST.get('reason', '')
        if not reason:
            messages.error(request, "Reason is required to ignore request.")
            return redirect('distribution:detail', pk=pk)

        try:
            ManualDistributionService.ignore_request(
                request_obj=request_obj,
                actor=user,
                reason=reason
            )
            messages.success(request, "Manual distribution request ignored.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

        return redirect('distribution:list')
