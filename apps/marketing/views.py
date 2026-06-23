from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, UpdateView, TemplateView
from django.utils.dateparse import parse_date, parse_time
from django.db import transaction
from apps.companies.models import Company
from .models import (
    Campaign, CampaignTypeSelection, CampaignEvent, EventCelebrity, EventGiveaway, EventCatering,
    TVAd, TVAdChannel, TVAdSlot, StreetAd, StreetAdTypeLine, StreetAdLocation,
    ExhibitionRecord, SocialMediaAd, SocialMediaPlatformLine, CampaignOtherCost
)
from .forms import CampaignForm, CampaignApprovalForm
from .services.campaigns import CampaignBudgetService, CampaignApprovalService, CampaignService, CampaignCreationService
from apps.audit.services.audit import AuditService
from .selectors import (
    get_campaigns_list,
    get_campaign_by_id,
    get_campaign_with_budget_details,
    get_pending_approvals_list,
)


def as_decimal(value, default='0'):
    try:
        return Decimal(str(value or default).replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def as_int(value, default=0):
    try:
        return int(value or default)
    except ValueError:
        return default


def list_at(values, index, default=''):
    return values[index] if index < len(values) else default


class CampaignListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = Campaign
    template_name = 'marketing/campaign_list.html'
    context_object_name = 'campaigns'
    permission_required = 'marketing.view_campaign'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_campaigns_list(
            company=company,
            search_query=self.request.GET.get('q'),
            status=self.request.GET.get('status'),
            approval=self.request.GET.get('approval')
        )


class CampaignDetailView(LoginRequiredMixin, CRMPermissionRequiredMixin, DetailView):
    model = Campaign
    template_name = 'marketing/campaign_detail.html'
    context_object_name = 'campaign'
    permission_required = 'marketing.view_campaign'

    def get_object(self, queryset=None):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        campaign = get_campaign_with_budget_details(company, self.kwargs.get('pk'))
        if not campaign:
            raise Http404("Campaign not found or access denied.")
        return campaign

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        CampaignBudgetService.refresh_total(self.object)
        from apps.marketing.services.roi_service import ROIService
        ROIService.recalculate_all_kpis(self.object)
        ctx['approval_form'] = CampaignApprovalForm()
        return ctx


class CampaignCreateView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'marketing.create_campaign'
    template_name = 'marketing/campaign_form.html'

    def get(self, request):
        return render(request, self.template_name, self.get_context())

    def post(self, request):
        try:
            company = self._resolve_company(request)
            campaign = CampaignCreationService.create_campaign_from_post(company, request.user, request.POST)
            messages.success(request, 'Campaign created with all selected marketing type details.')
            return redirect('marketing:campaign_detail', pk=campaign.pk)
        except Exception as exc:
            messages.error(request, f'Campaign could not be created: {exc}')
            return render(request, self.template_name, self.get_context())

    def get_context(self):
        user = self.request.user
        companies = Company.objects.all()
        if not user.is_superuser:
            companies = companies.filter(pk=user.company_id)
        return {
            'companies': companies,
            'target_choices': Campaign.TARGET_CHOICES,
            'campaign_type_choices': CampaignTypeSelection.TYPE_CHOICES,
            'ad_type_choices': StreetAdTypeLine.AD_TYPE_CHOICES,
            'platform_choices': SocialMediaPlatformLine.PLATFORM_CHOICES,
            'page_title': 'Campaign Builder',
        }

    def _resolve_company(self, request):
        company_id = request.POST.get('company')
        if not request.user.is_superuser:
            if company_id and str(company_id) != str(request.user.company_id):
                raise ValueError("You are not authorized to create campaigns for another company.")
            return request.user.company
        if company_id:
            return Company.objects.get(pk=company_id)
        if request.user.company_id:
            return request.user.company
        return Company.objects.first()


class CampaignUpdateView(LoginRequiredMixin, CRMPermissionRequiredMixin, UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'marketing/campaign_edit.html'
    success_url = reverse_lazy('marketing:campaign_list')
    permission_required = 'marketing.update_campaign'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = Campaign.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs

    def form_valid(self, form):
        before = {}
        after = {}
        for field in form.changed_data:
            before[field] = str(form.initial.get(field))
            after[field] = str(form.cleaned_data.get(field))
        response = super().form_valid(form)
        AuditService.log(
            company=self.object.company, actor=self.request.user, action='campaign.updated',
            obj=self.object, before=before, after=after
        )
        return response


class CampaignDuplicateView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'marketing.create_campaign'

    def post(self, request, pk):
        user = request.user
        company = user.company if not user.is_superuser else None
        campaign = get_campaign_by_id(company, pk)
        if not campaign:
            raise Http404("Campaign not found or access denied.")
        try:
            new_campaign = CampaignService.duplicate_campaign(campaign, actor=request.user)
            messages.success(request, f'Campaign duplicated successfully as "{new_campaign.name}".')
            return redirect('marketing:campaign_detail', pk=new_campaign.pk)
        except Exception as exc:
            messages.error(request, f'Failed to duplicate campaign: {exc}')
            return redirect('marketing:campaign_detail', pk=campaign.pk)


class CampaignArchiveView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'marketing.update_campaign'

    def post(self, request, pk):
        user = request.user
        company = user.company if not user.is_superuser else None
        campaign = get_campaign_by_id(company, pk)
        if not campaign:
            raise Http404("Campaign not found or access denied.")
        try:
            CampaignService.archive_campaign(campaign, actor=request.user)
            messages.success(request, f'Campaign "{campaign.name}" archived successfully.')
        except Exception as exc:
            messages.error(request, f'Failed to archive campaign: {exc}')
        return redirect('marketing:campaign_list')


class ApprovalQueueView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = Campaign
    template_name = 'marketing/approval_queue.html'
    context_object_name = 'campaigns'
    permission_required = 'finance.approve_campaign'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_pending_approvals_list(company)

    def post(self, request):
        user = request.user
        company = user.company if not user.is_superuser else None
        campaign = get_campaign_by_id(company, request.POST.get('campaign_id'))
        if not campaign:
            raise Http404("Campaign not found or access denied.")
        try:
            CampaignApprovalService.decide(campaign=campaign, new_status=request.POST.get('new_status'), actor=request.user, reason=request.POST.get('reason',''))
            if request.headers.get('X-Requested-With'):
                return JsonResponse({'message':'Approval decision saved.', 'reload': True})
            messages.success(request, 'Approval decision saved.')
        except Exception as exc:
            if request.headers.get('X-Requested-With'):
                return JsonResponse({'error': str(exc)}, status=400)
            messages.error(request, str(exc))
        return redirect('marketing:approval_queue')


class ROIReportView(LoginRequiredMixin, CRMPermissionRequiredMixin, TemplateView):
    template_name = 'marketing/roi_report.html'
    permission_required = 'marketing.view_campaign_roi'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        company = user.company if not user.is_superuser else None
        ctx['campaigns'] = get_campaigns_list(company)[:100]
        return ctx


def ajax_budget_preview(request):
    total = Decimal('0')
    for key, values in request.GET.lists():
        if 'budget' in key or 'cost_value' in key:
            for v in values:
                total += as_decimal(v)
    return JsonResponse({'total': str(total), 'formatted': f'{total:,.2f} EGP'})
