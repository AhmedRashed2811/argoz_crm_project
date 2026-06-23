import threading

_thread_locals = threading.local()


def get_current_request():
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    request = get_current_request()
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        return request.user
    return None


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import uuid
        if not hasattr(request, 'correlation_id'):
            request.correlation_id = uuid.uuid4()
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request = None
