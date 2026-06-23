from apps.audit.models import AuditLog
from apps.core.middleware import get_current_request


class AuditService:
    @staticmethod
    def log(*, company=None, actor=None, actor_type='user', action='', obj=None, object_type='', object_id='', before=None, after=None, metadata=None, reason=''):
        app_label = ''
        model_name = ''
        object_repr = ''
        
        if obj is not None:
            object_type = object_type or obj.__class__.__name__
            object_id = object_id or str(getattr(obj, 'pk', ''))
            company = company or getattr(obj, 'company', None)
            object_repr = str(obj)[:255]
            if hasattr(obj, '_meta'):
                app_label = obj._meta.app_label
                model_name = obj._meta.model_name
            
        correlation_id = None
        ip_address = None
        user_agent = ''
        request_path = ''
        
        request = get_current_request()
        if request:
            correlation_id = getattr(request, 'correlation_id', None)
            request_path = getattr(request, 'path', '')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded:
                ip_address = x_forwarded.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
                
            if not actor and hasattr(request, 'user') and request.user and request.user.is_authenticated:
                actor = request.user
                
        # Determine actor_user
        from django.contrib.auth import get_user_model
        User = get_user_model()
        actor_user = actor if isinstance(actor, User) else None

        # Resolve reason from metadata if not explicitly provided
        if not reason and metadata and isinstance(metadata, dict):
            reason = metadata.get('reason', '')

        # Calculate diffs
        before_dict = before or {}
        after_dict = after or {}
        changes = {}
        all_keys = set(before_dict.keys()) | set(after_dict.keys())
        for key in all_keys:
            val_before = before_dict.get(key)
            val_after = after_dict.get(key)
            if val_before != val_after:
                changes[key] = [val_before, val_after]

        return AuditLog.objects.create(
            company=company,
            actor=actor,
            actor_user=actor_user,
            actor_type=actor_type,
            action=action,
            object_type=object_type,
            object_id=object_id,
            app_label=app_label,
            model_name=model_name,
            object_repr=object_repr,
            before=before_dict,
            after=after_dict,
            before_json=before_dict,
            after_json=after_dict,
            changes_json=changes,
            reason=reason,
            metadata=metadata or {},
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
        )
