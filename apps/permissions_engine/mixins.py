from django.contrib.auth.mixins import AccessMixin
from apps.permissions_engine.services.engine import PermissionEngine

class CRMPermissionRequiredMixin(AccessMixin):
    permission_required = None

    def get_permission_required(self):
        if self.permission_required is None:
            raise NotImplementedError(
                '{0} is missing the permission_required attribute. Define {0}.permission_required.'.format(self.__class__.__name__)
            )
        if isinstance(self.permission_required, str):
            return [self.permission_required]
        return self.permission_required

    def has_permission(self):
        perms = self.get_permission_required()
        return all(PermissionEngine.has_perm(self.request.user, perm) for perm in perms)

    def dispatch(self, request, *args, **kwargs):
        if not self.has_permission():
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)
