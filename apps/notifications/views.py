from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import ListView, TemplateView
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from apps.audit.services.audit import AuditService
from .models import Notification, NotificationPreference, NotificationType, Reminder, EmailOutbox


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'

    def get_queryset(self):
        return Notification.objects.select_related('type').filter(recipient=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        company = user.company if not user.is_superuser else None
        
        reminders_qs = Reminder.objects.filter(recipient=user)
        outbox_qs = EmailOutbox.objects.all()
        if company:
            reminders_qs = reminders_qs.filter(company=company)
            outbox_qs = outbox_qs.filter(company=company)
            
        ctx['types'] = NotificationType.objects.all()
        ctx['reminders'] = reminders_qs.order_by('due_at')[:20]
        ctx['outbox'] = outbox_qs.order_by('-created_at')[:20] if user.is_staff else []
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


@login_required
@require_POST
def ajax_dismiss_reminder(request, pk):
    user = request.user
    company = user.company if not user.is_superuser else None
    
    if company:
        reminder = get_object_or_404(Reminder, pk=pk, company=company)
    else:
        reminder = get_object_or_404(Reminder, pk=pk)
        
    old_status = reminder.status
    reminder.status = 'dismissed'
    reminder.save(update_fields=['status', 'updated_at'])
    
    AuditService.log(
        company=reminder.company,
        actor=user,
        action='reminder.dismissed',
        obj=reminder,
        before={'status': old_status},
        after={'status': 'dismissed'}
    )
    
    return JsonResponse({'status': 'success', 'message': 'Reminder dismissed.'})

