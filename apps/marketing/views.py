from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
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
from .services.campaigns import CampaignBudgetService, CampaignApprovalService, CampaignService
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


class CampaignListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Campaign
    template_name = 'marketing/campaign_list.html'
    context_object_name = 'campaigns'
    permission_required = 'marketing.view_campaigns'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_campaigns_list(
            company=company,
            search_query=self.request.GET.get('q'),
            status=self.request.GET.get('status'),
            approval=self.request.GET.get('approval')
        )


class CampaignDetailView(LoginRequiredMixin, DetailView):
    model = Campaign
    template_name = 'marketing/campaign_detail.html'
    context_object_name = 'campaign'

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


class CampaignCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'marketing.create_campaign'
    template_name = 'marketing/campaign_form.html'

    def get(self, request):
        return render(request, self.template_name, self.get_context())

    def post(self, request):
        try:
            with transaction.atomic():
                company = self._resolve_company(request)
                campaign = Campaign.objects.create(
                    company=company,
                    name=request.POST.get('name','').strip(),
                    description=request.POST.get('description','').strip(),
                    start_date=parse_date(request.POST.get('start_date')),
                    end_date=parse_date(request.POST.get('end_date')),
                    target_type=request.POST.get('target_type') or 'other',
                    created_by_user=request.user,
                )
                selected = request.POST.getlist('campaign_types')
                for code in selected:
                    CampaignTypeSelection.objects.get_or_create(campaign=campaign, type_code=code)
                if 'events' in selected:
                    self._create_events(campaign, request)
                if 'tv_ads' in selected:
                    self._create_tv_ads(campaign, request)
                if 'street_ads' in selected:
                    self._create_street_ads(campaign, request)
                if 'exhibition' in selected:
                    self._create_exhibitions(campaign, request)
                if 'social_media' in selected:
                    self._create_social_ads(campaign, request)
                self._create_other_costs(campaign, request)
                CampaignBudgetService.refresh_total(campaign)
                AuditService.log(
                    company=campaign.company, actor=request.user, action='campaign.created',
                    obj=campaign, after={'name': campaign.name, 'target_type': campaign.target_type}
                )
            messages.success(request, 'Campaign created with all selected marketing type details.')
            return redirect('marketing:campaign_detail', pk=campaign.pk)
        except Exception as exc:
            messages.error(request, f'Campaign could not be created: {exc}')
            return render(request, self.template_name, self.get_context())

    def get_context(self):
        return {
            'companies': Company.objects.all(),
            'target_choices': Campaign.TARGET_CHOICES,
            'campaign_type_choices': CampaignTypeSelection.TYPE_CHOICES,
            'ad_type_choices': StreetAdTypeLine.AD_TYPE_CHOICES,
            'platform_choices': SocialMediaPlatformLine.PLATFORM_CHOICES,
            'page_title': 'Campaign Builder',
        }

    def _resolve_company(self, request):
        company_id = request.POST.get('company')
        if company_id:
            return Company.objects.get(pk=company_id)
        if request.user.company_id:
            return request.user.company
        return Company.objects.first()

    def _create_events(self, campaign, request):
        names = request.POST.getlist('event_name[]')
        for i, name in enumerate(names):
            if not name.strip():
                continue
            event = CampaignEvent.objects.create(
                campaign=campaign,
                event_name=name.strip(),
                venue_place=list_at(request.POST.getlist('event_venue[]'), i),
                event_date=parse_date(list_at(request.POST.getlist('event_date[]'), i)),
                budget=as_decimal(list_at(request.POST.getlist('event_budget[]'), i, '0')),
                target_attendees=as_int(list_at(request.POST.getlist('event_attendees[]'), i, '0')) or None,
                description=list_at(request.POST.getlist('event_description[]'), i),
            )
            for cname, cbudget in zip(request.POST.getlist(f'event_celebrity_name_{i}[]'), request.POST.getlist(f'event_celebrity_budget_{i}[]')):
                if cname.strip(): EventCelebrity.objects.create(event=event, name=cname.strip(), budget=as_decimal(cbudget))
            for gname, gbudget in zip(request.POST.getlist(f'event_giveaway_name_{i}[]'), request.POST.getlist(f'event_giveaway_budget_{i}[]')):
                if gname.strip(): EventGiveaway.objects.create(event=event, name=gname.strip(), budget=as_decimal(gbudget))
            for cname, cbudget in zip(request.POST.getlist(f'event_catering_name_{i}[]'), request.POST.getlist(f'event_catering_budget_{i}[]')):
                if cname.strip(): EventCatering.objects.create(event=event, name=cname.strip(), budget=as_decimal(cbudget))

    def _create_tv_ads(self, campaign, request):
        names = request.POST.getlist('tv_name[]')
        for i, name in enumerate(names):
            if not name.strip(): continue
            tv = TVAd.objects.create(
                campaign=campaign, name=name.strip(),
                start_date=parse_date(list_at(request.POST.getlist('tv_start_date[]'), i)),
                end_date=parse_date(list_at(request.POST.getlist('tv_end_date[]'), i)),
                budget=as_decimal(list_at(request.POST.getlist('tv_budget[]'), i, '0')),
                description=list_at(request.POST.getlist('tv_description[]'), i),
            )
            for ch, budget in zip(request.POST.getlist(f'tv_channel_name_{i}[]'), request.POST.getlist(f'tv_channel_budget_{i}[]')):
                if ch.strip(): TVAdChannel.objects.create(tv_ad=tv, channel_name=ch.strip(), channel_budget=as_decimal(budget))
            for t, n in zip(request.POST.getlist(f'tv_slot_time_{i}[]'), request.POST.getlist(f'tv_slot_count_{i}[]')):
                if t: TVAdSlot.objects.create(tv_ad=tv, appearance_time=parse_time(t), number_of_appearances=as_int(n,1) or 1)

    def _create_street_ads(self, campaign, request):
        names = request.POST.getlist('street_name[]')
        for i, name in enumerate(names):
            if not name.strip(): continue
            street = StreetAd.objects.create(
                campaign=campaign, name=name.strip(),
                start_date=parse_date(list_at(request.POST.getlist('street_start_date[]'), i)),
                end_date=parse_date(list_at(request.POST.getlist('street_end_date[]'), i)),
                budget=as_decimal(list_at(request.POST.getlist('street_budget[]'), i, '0')),
                description=list_at(request.POST.getlist('street_description[]'), i),
            )
            types = request.POST.getlist(f'street_type_{i}[]')
            numbers = request.POST.getlist(f'street_type_number_{i}[]')
            budgets = request.POST.getlist(f'street_type_budget_{i}[]')
            locations = request.POST.getlist(f'street_type_location_{i}[]')
            location_budgets = request.POST.getlist(f'street_type_location_budget_{i}[]')
            for j, ad_type in enumerate(types):
                if not ad_type: continue
                line = StreetAdTypeLine.objects.create(street_ad=street, ad_type=ad_type, total_number=as_int(numbers[j] if j < len(numbers) else 1, 1), budget=as_decimal(budgets[j] if j < len(budgets) else 0))
                loc = locations[j] if j < len(locations) else ''
                if loc.strip(): StreetAdLocation.objects.create(type_line=line, location=loc.strip(), budget=as_decimal(location_budgets[j] if j < len(location_budgets) else 0))

    def _create_exhibitions(self, campaign, request):
        names = request.POST.getlist('exhibition_name[]')
        for i, name in enumerate(names):
            if not name.strip(): continue
            ExhibitionRecord.objects.create(
                campaign=campaign, name=name.strip(), place=list_at(request.POST.getlist('exhibition_place[]'), i),
                start_date=parse_date(list_at(request.POST.getlist('exhibition_start_date[]'), i)),
                end_date=parse_date(list_at(request.POST.getlist('exhibition_end_date[]'), i)),
                budget=as_decimal(list_at(request.POST.getlist('exhibition_budget[]'), i, '0')),
            )

    def _create_social_ads(self, campaign, request):
        names = request.POST.getlist('social_name[]')
        for i, name in enumerate(names):
            if not name.strip(): continue
            ad = SocialMediaAd.objects.create(campaign=campaign, name=name.strip(), target_kpi=list_at(request.POST.getlist('social_target_kpi[]'), i), description=list_at(request.POST.getlist('social_description[]'), i))
            platforms = request.POST.getlist(f'social_platform_{i}[]')
            budgets = request.POST.getlist(f'social_platform_budget_{i}[]')
            targets = request.POST.getlist(f'social_platform_target_{i}[]')
            for j, platform in enumerate(platforms):
                if platform: SocialMediaPlatformLine.objects.create(social_ad=ad, platform=platform, budget=as_decimal(budgets[j] if j < len(budgets) else 0), target_value=as_decimal(targets[j] if j < len(targets) else 0))

    def _create_other_costs(self, campaign, request):
        values = request.POST.getlist('other_cost_value[]')
        reasons = request.POST.getlist('other_cost_reason[]')
        for i, value in enumerate(values):
            reason = reasons[i] if i < len(reasons) else ''
            if value and reason.strip(): CampaignOtherCost.objects.create(campaign=campaign, value=as_decimal(value), reason=reason.strip(), cost_created_by=request.user)


class CampaignUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'marketing/campaign_edit.html'
    success_url = reverse_lazy('marketing:campaign_list')
    permission_required = 'marketing.update_campaign'

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


class CampaignDuplicateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'marketing.create_campaign'

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        try:
            new_campaign = CampaignService.duplicate_campaign(campaign, actor=request.user)
            messages.success(request, f'Campaign duplicated successfully as "{new_campaign.name}".')
            return redirect('marketing:campaign_detail', pk=new_campaign.pk)
        except Exception as exc:
            messages.error(request, f'Failed to duplicate campaign: {exc}')
            return redirect('marketing:campaign_detail', pk=campaign.pk)


class CampaignArchiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'marketing.delete_campaign'

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        try:
            CampaignService.archive_campaign(campaign, actor=request.user)
            messages.success(request, f'Campaign "{campaign.name}" archived successfully.')
        except Exception as exc:
            messages.error(request, f'Failed to archive campaign: {exc}')
        return redirect('marketing:campaign_list')


class ApprovalQueueView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Campaign
    template_name = 'marketing/approval_queue.html'
    context_object_name = 'campaigns'
    permission_required = 'finance.approve_campaign'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_pending_approvals_list(company)

    def post(self, request):
        campaign = get_object_or_404(Campaign, pk=request.POST.get('campaign_id'))
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


class ROIReportView(LoginRequiredMixin, TemplateView):
    template_name = 'marketing/roi_report.html'

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
