from collections import OrderedDict
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.views.generic import TemplateView, ListView
from .models import UserPermissionOverride


class PermissionMatrixView(LoginRequiredMixin, TemplateView):
    template_name = 'permissions_engine/permission_matrix.html'

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


class UserOverrideListView(LoginRequiredMixin, ListView):
    model = UserPermissionOverride
    template_name = 'permissions_engine/user_overrides.html'
    context_object_name = 'overrides'
