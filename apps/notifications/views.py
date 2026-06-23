from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import ListView, TemplateView
from .models import Notification, NotificationPreference, NotificationType, Reminder, EmailOutbox


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'

    def get_queryset(self):
        return Notification.objects.select_related('type').filter(recipient=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['types'] = NotificationType.objects.all()
        ctx['reminders'] = Reminder.objects.filter(recipient=self.request.user).order_by('due_at')[:20]
        ctx['outbox'] = EmailOutbox.objects.all().order_by('-created_at')[:20] if self.request.user.is_staff else []
        return ctx


class NotificationPreferenceView(LoginRequiredMixin, TemplateView):
    template_name = 'notifications/preferences.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['types'] = NotificationType.objects.all()
        ctx['preferences'] = NotificationPreference.objects.filter(user=self.request.user)
        return ctx


def ajax_mark_read(request):
    Notification.objects.filter(recipient=request.user, status='unread').update(status='read')
    return JsonResponse({'message':'Notifications marked as read.', 'reload': True})
