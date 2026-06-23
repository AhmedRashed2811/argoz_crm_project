from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.audit.services.audit import AuditService
from apps.permissions_engine.models import (
    CRMGroupTemplatePermission,
    PermissionChangeLog,
    UserPermissionOverride,
)


@receiver(post_save, sender=UserPermissionOverride)
def audit_user_permission_override(sender, instance, created, **kwargs):
    PermissionChangeLog.objects.create(
        company=getattr(instance.user, 'company', None),
        target_user=instance.user,
        permission_codename=instance.permission_codename,
        old_value=None,
        new_value=instance.is_allowed,
        actor=instance.changed_by,
        metadata={'source': 'user_override', 'created': created, 'reason': instance.reason},
    )
    AuditService.log(
        company=getattr(instance.user, 'company', None),
        actor=instance.changed_by,
        action='permission.user_override_changed',
        obj=instance.user,
        after={'permission': instance.permission_codename, 'is_allowed': instance.is_allowed},
        metadata={'created': created, 'reason': instance.reason},
    )


@receiver(post_save, sender=CRMGroupTemplatePermission)
def audit_group_template_permission(sender, instance, created, **kwargs):
    AuditService.log(
        company=instance.group_template.company,
        actor_type='system',
        action='permission.group_template_changed',
        obj=instance.group_template,
        after={'permission': instance.permission_codename, 'is_allowed': instance.is_allowed},
        metadata={'created': created},
    )
