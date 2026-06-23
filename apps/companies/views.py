from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from apps.core.models import CompanyPolicy, PolicyDefinition, PolicyOption
from .models import Company, Branch, Language
from .forms import CompanyForm, BranchForm, LanguageForm


class CompanyListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = Company
    template_name = 'companies/company_list.html'
    permission_required = 'companies.manage_company_policy'

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return Company.objects.filter(pk=user.company_id)
        return Company.objects.all()


class CompanyCreateView(LoginRequiredMixin, CRMPermissionRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'
    success_url = reverse_lazy('companies:list')
    permission_required = 'companies.manage_company_policy'


class CompanyUpdateView(LoginRequiredMixin, CRMPermissionRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'
    success_url = reverse_lazy('companies:list')
    permission_required = 'companies.manage_company_policy'

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return Company.objects.filter(pk=user.company_id)
        return Company.objects.all()


class BranchListView(LoginRequiredMixin, ListView):
    model = Branch
    template_name = 'companies/branch_list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser:
            if user.company:
                qs = qs.filter(company=user.company)
            else:
                qs = qs.none()
        return qs


class LanguageListView(LoginRequiredMixin, ListView):
    model = Language
    template_name = 'companies/language_list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser:
            if user.company:
                qs = qs.filter(company=user.company)
            else:
                qs = qs.none()
        return qs


class PolicyConsoleView(LoginRequiredMixin, TemplateView):
    template_name = 'companies/policy_console.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company or Company.objects.first()
        ctx['company'] = company
        ctx['policies'] = CompanyPolicy.objects.select_related('policy_definition','selected_option').filter(company=company) if company else []
        ctx['definitions'] = PolicyDefinition.objects.prefetch_related('options').all()
        return ctx

    @transaction.atomic
    def post(self, request):
        company = request.user.company or Company.objects.first()
        from apps.core.models import PolicyChangeHistory
        from apps.audit.services.audit import AuditService
        
        for definition in PolicyDefinition.objects.all():
            option_id = request.POST.get(f'policy_{definition.id}')
            if option_id:
                option = PolicyOption.objects.filter(pk=option_id).first()
                if not option:
                    continue
                policy, created = CompanyPolicy.objects.get_or_create(
                    company=company, policy_definition=definition, is_active=True,
                    defaults={'selected_option': option, 'value': option.value if option else {}}
                )
                if created or policy.selected_option != option:
                    old_opt_code = policy.selected_option.code if (not created and policy.selected_option) else None
                    old_val = policy.value if not created else {}
                    new_val = option.value if option else {}

                    policy.selected_option = option
                    policy.value = new_val
                    policy.save()

                    PolicyChangeHistory.objects.create(
                        company_policy=policy,
                        old_value={'option_code': old_opt_code, 'value': old_val},
                        new_value={'option_code': option.code, 'value': new_val},
                        changed_by=request.user,
                        reason=request.POST.get('reason', '')
                    )
                    AuditService.log(
                        company=company, actor=request.user, action='policy.changed',
                        obj=policy, before={'option_code': old_opt_code, 'value': old_val},
                        after={'option_code': option.code, 'value': new_val}
                    )
        messages.success(request, 'Company policies updated.')
        return redirect('companies:policy_console')
