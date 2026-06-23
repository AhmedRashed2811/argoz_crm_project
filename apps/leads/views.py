from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, DetailView, UpdateView
from apps.accounts.models import User, Team, BrokerProfile
from apps.companies.models import Company, Language
from apps.marketing.models import Campaign, CampaignEvent, SocialMediaAd, ExhibitionRecord
from .models import Lead, LeadSource, LeadStage, HowDidYouKnowOption, LeadActivity, LeadFollowUp, Meeting
from .forms import LeadForm
from .services.leads import LeadService, normalize_phone
from .selectors import (
    get_leads_list,
    get_lead_stages,
    get_lead_sources,
    get_languages,
    get_brokers,
    get_campaigns,
    get_how_options,
    get_teams,
    get_salesmen,
)

SOURCE_RULES = {
    'self_generated': {'title':'Self Generated', 'distribution':'Sales Head can assign within team or automatic within team. Salesman owns by default unless policy redistributes after SLA.', 'show':['self_owner_mode']},
    'campaign': {'title':'Campaign', 'distribution':'Manual or automatic per company policy. Campaign and child type attribution are required when available.', 'show':['campaign','campaign_child','distribution']},
    'broker': {'title':'Broker', 'distribution':'Broker leads may remain with broker only or also be assigned to company sales per policy.', 'show':['broker','broker_assign_mode','distribution']},
    'walkin': {'title':'Walk-in', 'distribution':'Manual only. Receptionist records how the visitor knew the company and the active reception policy decides who meets them.', 'show':['how_did_you_know','walkin_policy','manual_assignment']},
    'call_center': {'title':'Call Center', 'distribution':'Manual or automatic per company policy. The caller source prompt must be captured.', 'show':['how_did_you_know','distribution']},
    'exhibition': {'title':'Exhibition', 'distribution':'Manual only and a salesman must be selected. The exhibition record is required.', 'show':['campaign','exhibition','manual_assignment']},
    'referral': {'title':'Referral', 'distribution':'Manual or automatic per company policy. Referrer name is captured as free text.', 'show':['referrer_name','distribution']},
    'existing_client': {'title':'Existing Client', 'distribution':'The system can preserve the original salesman relationship or redistribute per policy.', 'show':['existing_client_phone','distribution']},
}


class LeadListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = Lead
    template_name = 'leads/lead_list.html'
    context_object_name = 'leads'
    paginate_by = 30
    permission_required = 'leads.view_lead'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        return get_leads_list(
            company=company,
            search_query=self.request.GET.get('q'),
            stage_id=self.request.GET.get('stage'),
            source_id=self.request.GET.get('source'),
            status=self.request.GET.get('status'),
            user=user
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['stages'] = get_lead_stages(None)
        ctx['sources'] = get_lead_sources(None)
        return ctx


class LeadDetailView(LoginRequiredMixin, CRMPermissionRequiredMixin, DetailView):
    model = Lead
    template_name = 'leads/lead_detail.html'
    context_object_name = 'lead'
    permission_required = 'leads.view_lead'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = Lead.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs

    def post(self, request, *args, **kwargs):
        lead = self.get_object()
        action = request.POST.get('action')
        if action == 'stage':
            stage = get_object_or_404(LeadStage, pk=request.POST.get('stage'), company=lead.company)
            LeadService.change_stage(lead=lead, new_stage=stage, actor=request.user, reason=request.POST.get('reason',''))
            msg = 'Lead stage updated.'
        elif action == 'activity':
            LeadActivity.objects.create(lead=lead, activity_type=request.POST.get('activity_type','note'), subject=request.POST.get('subject',''), body=request.POST.get('body',''), result=request.POST.get('result',''), created_by=request.user)
            msg = 'Activity added.'
        elif action == 'followup':
            LeadFollowUp.objects.create(lead=lead, assigned_to=request.user, due_at=request.POST.get('due_at'), reminder_at=request.POST.get('reminder_at') or None, notes=request.POST.get('notes',''))
            msg = 'Follow-up scheduled.'
        elif action == 'meeting':
            Meeting.objects.create(lead=lead, assigned_to=request.user, scheduled_at=request.POST.get('scheduled_at'), location=request.POST.get('location',''), meeting_type=request.POST.get('meeting_type','office'), notes=request.POST.get('notes',''))
            msg = 'Meeting scheduled.'
        else:
            msg = 'No action selected.'
        if request.headers.get('X-Requested-With'):
            return JsonResponse({'message': msg, 'reload': True})
        messages.success(request, msg)
        return redirect('leads:detail', pk=lead.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['stages'] = get_lead_stages(self.object.company)
        return ctx


class LeadCreateView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    permission_required = 'leads.create_lead'
    template_name = 'leads/lead_form.html'

    def get(self, request):
        return render(request, self.template_name, self.context())

    def post(self, request):
        try:
            company = self._resolve_company(request)
            source = LeadSource.objects.get(pk=request.POST.get('source'))
            stage = get_lead_stages(company).filter(code='fresh').first() or get_lead_stages(company).first()
            lang = get_languages(company).filter(pk=request.POST.get('language')).first()
            campaign = get_campaigns(company).filter(pk=request.POST.get('campaign')).first()
            broker = get_brokers(company).filter(pk=request.POST.get('broker')).first()
            how = get_how_options(company).filter(pk=request.POST.get('how_did_you_know')).first()
            metadata = {
                'source_code': source.code,
                'distribution_mode': request.POST.get('distribution_mode'),
                'campaign_child_type': request.POST.get('campaign_child_type'),
                'campaign_child_id': request.POST.get('campaign_child_id'),
                'referrer_name': request.POST.get('referrer_name'),
                'existing_client_phone': request.POST.get('existing_client_phone'),
                'self_owner_mode': request.POST.get('self_owner_mode'),
                'broker_assign_mode': request.POST.get('broker_assign_mode'),
            }
            lead, created = LeadService.create_lead(
                company=company,
                full_name=request.POST.get('full_name','').strip(),
                phone_country_code=request.POST.get('phone_country_code','+20'),
                phone_number=request.POST.get('phone_number','').strip(),
                source=source,
                origin=request.POST.get('origin','direct'),
                actor=request.user,
                email=request.POST.get('email',''),
                current_stage=stage,
                language=lang,
                campaign=campaign,
                broker=broker,
                how_did_you_know=how,
                metadata=metadata,
            )
            if created:
                assignment_mode = request.POST.get('distribution_mode')
                team = get_teams(company).filter(pk=request.POST.get('manual_team')).first()
                salesman = get_salesmen(company).filter(pk=request.POST.get('manual_salesman')).first()
                if assignment_mode == 'manual' and (team or salesman):
                    LeadService.assign_lead(lead=lead, actor=request.user, strategy_code='manual_assignment', team=team, salesman=salesman)
                elif assignment_mode == 'automatic':
                    LeadService.assign_lead(lead=lead, actor=request.user, strategy_code=request.POST.get('strategy_code') or None)
                messages.success(request, 'Lead created and routed according to selected distribution policy.')
            else:
                messages.warning(request, 'Duplicate lead detected. Existing lead opened instead.')
            return redirect('leads:detail', pk=lead.pk)
        except Exception as exc:
            messages.error(request, f'Lead could not be created: {exc}')
            return render(request, self.template_name, self.context())

    def _resolve_company(self, request):
        if not request.user.is_superuser:
            return request.user.company
        company_id = request.POST.get('company')
        if company_id: return Company.objects.get(pk=company_id)
        if request.user.company_id: return request.user.company
        return Company.objects.first()

    def context(self):
        user = self.request.user
        if not user.is_superuser:
            companies = Company.objects.filter(pk=user.company_id) if user.company_id else Company.objects.none()
            company = user.company
        else:
            companies = Company.objects.all()
            company = user.company or companies.first()
        return {
            'companies': companies,
            'sources': get_lead_sources(company),
            'stages': get_lead_stages(company),
            'languages': get_languages(company),
            'brokers': get_brokers(company),
            'campaigns': get_campaigns(company),
            'how_options': get_how_options(company),
            'teams': get_teams(company),
            'salesmen': get_salesmen(company),
            'source_rules': SOURCE_RULES,
        }


class LeadUpdateView(LoginRequiredMixin, CRMPermissionRequiredMixin, UpdateView):
    model = Lead
    form_class = LeadForm
    template_name = 'leads/lead_edit.html'
    permission_required = 'leads.update_lead'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = Lead.objects.all()
        if company:
            qs = qs.filter(company=company)
        return qs


def ajax_source_rules(request):
    source_id = request.GET.get('source_id')
    source = LeadSource.objects.filter(pk=source_id).first()
    rule = SOURCE_RULES.get(source.code if source else '', {'title':'Unknown source','distribution':'Select a source.','show':[]})
    return JsonResponse(rule)


def ajax_campaign_children(request):
    campaign = get_object_or_404(Campaign, pk=request.GET.get('campaign_id'))
    data = []
    for e in campaign.events.all(): data.append({'type':'event','id':str(e.id),'label':f'Event: {e.event_name}'})
    for s in campaign.social_ads.all(): data.append({'type':'social_media','id':str(s.id),'label':f'Social: {s.name}'})
    for ex in campaign.exhibitions.all(): data.append({'type':'exhibition','id':str(ex.id),'label':f'Exhibition: {ex.name}'})
    return JsonResponse({'children': data})


def ajax_eligible_sales(request):
    user = request.user
    company = user.company if (user.is_authenticated and user.company) else None
    if not company and user.is_superuser:
        company = Company.objects.first()
    if not company:
        return JsonResponse({'users': []})
    users = get_salesmen(company).order_by('first_name','email')[:100]
    return JsonResponse({'users':[{'id':str(u.id),'name':u.get_full_name() or u.email,'email':u.email} for u in users]})

