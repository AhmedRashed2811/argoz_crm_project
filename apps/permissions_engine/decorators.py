from django.core.exceptions import PermissionDenied
from functools import wraps
from .services.engine import PermissionEngine


def crm_permission_required(permission_code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not PermissionEngine.has_perm(request.user, permission_code):
                raise PermissionDenied(f'Missing permission: {permission_code}')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
