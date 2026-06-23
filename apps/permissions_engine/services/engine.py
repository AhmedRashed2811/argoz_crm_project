from django.contrib.auth.models import Permission
from apps.permissions_engine.models import UserPermissionOverride, CRMGroupTemplatePermission
from apps.core.permissions import permission_candidates


class PermissionEngine:
    """Runtime authorization layer. It never checks hardcoded role names."""

    @staticmethod
    def normalize(code: str) -> str:
        return code.strip()

    @classmethod
    def has_perm(cls, user, permission_code: str) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission_codes = permission_candidates(cls.normalize(permission_code))

        # 1. User specific override has top priority.  An explicit deny on any
        # compatible code wins over template/native permissions.
        overrides = UserPermissionOverride.objects.filter(
            user=user, permission_codename__in=permission_codes,
        )
        for override in overrides:
            if not override.is_allowed:
                return False
        if overrides.filter(is_allowed=True).exists():
            return True

        # 2. Template-based permissions from user profile default_group_template
        if hasattr(user, 'profile') and user.profile and user.profile.default_group_template:
            tpl_perms = CRMGroupTemplatePermission.objects.filter(
                group_template=user.profile.default_group_template,
                permission_codename__in=permission_codes,
            )
            for tpl_perm in tpl_perms:
                if not tpl_perm.is_allowed:
                    return False
            if tpl_perms.filter(is_allowed=True).exists():
                return True

        # 3. Fallback to native Django permissions (e.g. from Django Groups).
        return any(user.has_perm(code) for code in permission_codes)

    @classmethod
    def effective_permissions(cls, user):
        if not user or not user.is_authenticated:
            return set()
        if user.is_superuser:
            return {f'{app}.{codename}' for app, codename in Permission.objects.values_list('content_type__app_label', 'codename')}
        
        # Native django permissions
        codes = set(user.get_all_permissions())

        # Merge defaults from the default_group_template
        if hasattr(user, 'profile') and user.profile and user.profile.default_group_template:
            tpl_perms = CRMGroupTemplatePermission.objects.filter(
                group_template=user.profile.default_group_template
            )
            for tp in tpl_perms:
                if tp.is_allowed:
                    codes.add(tp.permission_codename)
                else:
                    codes.discard(tp.permission_codename)

        # Overwrite with user overrides
        for override in UserPermissionOverride.objects.filter(user=user):
            if override.is_allowed:
                codes.add(override.permission_codename)
            else:
                codes.discard(override.permission_codename)

        # Expand aliases so callers can display/check either the document code
        # or an older seeded code.
        expanded = set(codes)
        for code in list(codes):
            expanded.update(permission_candidates(code))
        return expanded
