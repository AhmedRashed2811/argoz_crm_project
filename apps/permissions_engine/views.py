from collections import OrderedDict
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.views.generic import TemplateView, ListView
from .models import UserPermissionOverride


class PermissionMatrixView(LoginRequiredMixin, CRMPermissionRequiredMixin, TemplateView):
    template_name = 'permissions_engine/permission_matrix.html'
    permission_required = 'companies.manage_company_policy'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        groups = Group.objects.prefetch_related('permissions__content_type').order_by('name')
        permissions = Permission.objects.select_related('content_type').order_by('content_type__app_label','codename')
        by_module = OrderedDict()
        for p in permissions:
            by_module.setdefault(p.content_type.app_label, []).append(p)
        ctx['groups'] = groups
        ctx['permissions_by_module'] = by_module
        ctx['group_perm_ids'] = {g.id: set(p.id for p in g.permissions.all()) for g in groups}
        return ctx


class UserOverrideListView(LoginRequiredMixin, CRMPermissionRequiredMixin, ListView):
    model = UserPermissionOverride
    template_name = 'permissions_engine/user_overrides.html'
    context_object_name = 'overrides'
    permission_required = 'companies.manage_company_policy'

    def get_queryset(self):
        user = self.request.user
        company = user.company if not user.is_superuser else None
        qs = UserPermissionOverride.objects.all()
        if company:
            qs = qs.filter(user__company=company)
        return qs
