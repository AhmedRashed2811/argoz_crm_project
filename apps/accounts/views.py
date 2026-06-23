from collections import OrderedDict
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from .models import User, Team
from .forms import LoginForm, CRMUserCreationForm, CRMUserUpdateForm, TeamForm

ROLE_HELP = {
    'System Admins': 'Full platform configuration, user management, policies, audit, integrations and maintenance.',
    'Sales': 'Own lead pipeline, activities, stage movement, follow-ups and meetings.',
    'Sales Head': 'Team pipeline visibility, manual assignment and redistribution controls.',
    'Sales Operation': 'Operational control over lead import, assignment, SLA, sources and distribution setup.',
    'Directors': 'Executive visibility across leads, campaigns, finance and reporting without heavy operational editing.',
    'Call Center': 'Call-origin lead creation and follow-up queue management.',
    'Finance Managers': 'Campaign budget review, approval decisions and finance reports.',
    'Receptionists': 'Walk-in lead registration and reception queue actions.',
    'Brokers': 'Broker-owned leads and broker-facing updates.',
    'Marketing Members': 'Create campaigns, assets, attribution and marketing reporting.',
    'Marketing Managers': 'Full marketing setup, campaign budget management and integrations.',
}

MODULE_LABELS = {
    'leads': 'Lead Management', 'marketing': 'Marketing', 'finance': 'Finance', 'accounts': 'Users',
    'permissions': 'Permissions', 'company': 'Company Setup', 'policies': 'Policies', 'distribution': 'Distribution',
    'sla': 'SLA', 'integrations': 'Integrations', 'notifications': 'Notifications', 'reports': 'Reports',
    'audit': 'Audit', 'system': 'System', 'reception': 'Reception', 'callcenter': 'Call Center', 'brokers': 'Brokers',
    'reminders': 'Reminders', 'lead_sources': 'Lead Sources',
}


def permission_context(user_obj=None):
    groups = Group.objects.prefetch_related('permissions__content_type').order_by('name')
    permissions = Permission.objects.select_related('content_type').order_by('content_type__app_label', 'codename')
    by_app = OrderedDict()
    for perm in permissions:
        app = perm.content_type.app_label
        by_app.setdefault(app, {'label': MODULE_LABELS.get(app, app.replace('_',' ').title()), 'perms': []})['perms'].append(perm)
    selected_permission_ids = set()
    selected_group_ids = set()
    if user_obj and user_obj.pk:
        selected_permission_ids = set(str(p.id) for p in user_obj.user_permissions.all())
        selected_group_ids = set(str(g.id) for g in user_obj.groups.all())
    role_cards = []
    for group in groups:
        role_cards.append({
            'group': group,
            'help': ROLE_HELP.get(group.name, 'Configurable group template.'),
            'count': group.permissions.count(),
        })
    return {
        'role_cards': role_cards,
        'permissions_by_app': by_app,
        'selected_permission_ids': selected_permission_ids,
        'selected_group_ids': selected_group_ids,
        'module_labels': MODULE_LABELS,
    }


class CRMLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm


class CRMLogoutView(LogoutView):
    pass


class UserListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    permission_required = 'accounts.view_users'

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related('company').prefetch_related('groups').order_by('email')
        if not user.is_superuser:
            qs = qs.filter(company=user.company)
        q = self.request.GET.get('q')
        group = self.request.GET.get('group')
        if q:
            qs = qs.filter(email__icontains=q)
        if group:
            qs = qs.filter(groups__id=group)
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['groups'] = Group.objects.order_by('name')
        return ctx


class UserCreateView(LoginRequiredMixin, CRMPermissionRequiredMixin, CreateView):
    model = User
    form_class = CRMUserCreationForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    permission_required = 'accounts.create_user'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(permission_context())
        ctx['mode'] = 'create'
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        new_user = self.object
        from apps.audit.services.audit import AuditService
        AuditService.log(
            company=new_user.company, actor=self.request.user, action='user.created',
            obj=new_user, after={'email': new_user.email, 'is_active': new_user.is_active}
        )
        from apps.permissions_engine.models import PermissionChangeLog
        new_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in new_user.user_permissions.all())
        for p in new_perms:
            PermissionChangeLog.objects.create(
                company=new_user.company, target_user=new_user, permission_codename=p,
                old_value=None, new_value=True, actor=self.request.user,
                metadata={'trigger': 'user_create_form'}
            )
        return response


class UserUpdateView(LoginRequiredMixin, CRMPermissionRequiredMixin, UpdateView):
    model = User
    form_class = CRMUserUpdateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    permission_required = 'accounts.update_user'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return User.objects.filter(company=user.company)
        return User.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(permission_context(self.object))
        ctx['mode'] = 'edit'
        return ctx

    def form_valid(self, form):
        user = self.get_object()
        old_groups = set(user.groups.values_list('name', flat=True))
        old_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in user.user_permissions.all())
        old_is_active = user.is_active

        response = super().form_valid(form)

        new_user = self.object
        new_groups = set(new_user.groups.values_list('name', flat=True))
        new_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in new_user.user_permissions.all())

        from apps.audit.services.audit import AuditService
        AuditService.log(
            company=new_user.company, actor=self.request.user, action='user.updated',
            obj=new_user, before={'is_active': old_is_active}, after={'is_active': new_user.is_active}
        )

        from apps.permissions_engine.models import PermissionChangeLog
        added_perms = new_perms - old_perms
        removed_perms = old_perms - new_perms

        if added_perms or removed_perms:
            AuditService.log(
                company=new_user.company, actor=self.request.user, action='user.permissions_changed',
                obj=new_user, before={'permissions': list(old_perms)}, after={'permissions': list(new_perms)}
            )

        for p in added_perms:
            PermissionChangeLog.objects.create(
                company=new_user.company, target_user=new_user, permission_codename=p,
                old_value=False, new_value=True, actor=self.request.user,
                metadata={'trigger': 'user_edit_form', 'groups_changed': list(new_groups - old_groups)}
            )
        for p in removed_perms:
            PermissionChangeLog.objects.create(
                company=new_user.company, target_user=new_user, permission_codename=p,
                old_value=True, new_value=False, actor=self.request.user,
                metadata={'trigger': 'user_edit_form', 'groups_changed': list(old_groups - new_groups)}
            )
        return response


class UserDetailView(LoginRequiredMixin, CRMPermissionRequiredMixin, DetailView):
    model = User
    template_name = 'accounts/user_detail.html'
    context_object_name = 'crm_user'
    permission_required = 'accounts.view_users'

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return User.objects.filter(company=user.company)
        return User.objects.all()


class TeamListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = Team
    template_name = 'accounts/team_list.html'
    context_object_name = 'teams'
    permission_required = 'companies.manage_company_policy'

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return Team.objects.filter(company=user.company)
        return Team.objects.all()


class TeamCreateView(LoginRequiredMixin, CRMPermissionRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = 'accounts/team_form.html'
    success_url = reverse_lazy('accounts:team_list')
    permission_required = 'companies.manage_company_policy'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        return super().form_valid(form)


def ajax_group_permissions(request):
    ids = request.GET.getlist('groups[]') or request.GET.get('groups','').split(',')
    ids = [x for x in ids if x]
    qs = Group.objects.filter(id__in=ids).prefetch_related('permissions__content_type')
    perms = Permission.objects.filter(group__in=qs).select_related('content_type').distinct().order_by('content_type__app_label','codename')
    return JsonResponse({
        'permissions': [{'id': p.id, 'code': f'{p.content_type.app_label}.{p.codename}', 'name': p.name} for p in perms],
        'count': perms.count(),
    })
