from django.contrib.auth.models import Permission
from apps.permissions_engine.models import UserPermissionOverride, CRMGroupTemplatePermission


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
        permission_code = cls.normalize(permission_code)

        # 1. User specific override has top priority
        override = UserPermissionOverride.objects.filter(user=user, permission_codename=permission_code).first()
        if override is not None:
            return override.is_allowed

        # 2. Template-based permissions from user profile default_group_template
        if hasattr(user, 'profile') and user.profile and user.profile.default_group_template:
            tpl_perm = CRMGroupTemplatePermission.objects.filter(
                group_template=user.profile.default_group_template,
                permission_codename=permission_code
            ).first()
            if tpl_perm is not None:
                return tpl_perm.is_allowed

        # 3. Fallback to native Django permissions (e.g. from Django Groups)
        return user.has_perm(permission_code)

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
        return codes
