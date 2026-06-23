from apps.audit.models import AuditLog
from apps.core.middleware import get_current_request


class AuditService:
    @staticmethod
    def log(*, company=None, actor=None, actor_type='user', action='', obj=None, object_type='', object_id='', before=None, after=None, metadata=None):
        if obj is not None:
            object_type = object_type or obj.__class__.__name__
            object_id = object_id or str(getattr(obj, 'pk', ''))
            company = company or getattr(obj, 'company', None)
            
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
                
        return AuditLog.objects.create(
            company=company,
            actor=actor,
            actor_type=actor_type,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before or {},
            after=after or {},
            metadata=metadata or {},
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
        )
