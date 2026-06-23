from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from apps.notifications.models import Notification, NotificationType, NotificationDelivery, EmailOutbox, Reminder


class NotificationService:
    @staticmethod
    def notify(*, company, recipient, type_code, title, message, related_object=None, channels=None):
        ntype, _ = NotificationType.objects.get_or_create(
            code=type_code,
            defaults={'name': type_code.replace('_', ' ').title(), 'category': 'system', 'default_channels': ['in_app'], 'severity': 'info'},
        )
        notification = Notification.objects.create(
            company=company,
            type=ntype,
            recipient=recipient,
            title=title,
            message=message,
            related_object_type=related_object.__class__.__name__ if related_object else '',
            related_object_id=str(getattr(related_object, 'pk', '')) if related_object else '',
        )
        for channel in channels or ntype.default_channels or ['in_app']:
            NotificationDelivery.objects.create(notification=notification, channel=channel)
            if channel == 'email' and recipient.email:
                EmailOutbox.objects.create(company=company, to_email=recipient.email, subject=title, body=message)
            elif channel == 'realtime_ws' or channel == 'in_app':
                # Try sending realtime WebSocket message
                try:
                    from asgiref.sync import async_to_sync
                    from channels.layers import get_channel_layer
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f'user_notifications_{recipient.id}',
                            {
                                'type': 'notification_message',
                                'payload': {
                                    'id': str(notification.id),
                                    'title': title,
                                    'message': message,
                                    'type_code': type_code,
                                    'severity': ntype.severity,
                                    'created_at': notification.created_at.isoformat() if notification.created_at else timezone.now().isoformat(),
                                }
                            }
                        )
                except Exception:
                    pass  # Ensure robust execution even if channels layer is not configured / running in some contexts
        return notification

    @staticmethod
    def create_reminder(*, company, recipient, title, message, due_at, reminder_type='generic', lead=None):
        reminder = Reminder.objects.create(company=company, recipient=recipient, title=title, message=message, due_at=due_at, reminder_type=reminder_type, lead=lead)
        from apps.audit.services.audit import AuditService
        AuditService.log(
            company=company,
            action='reminder.created',
            obj=reminder,
            metadata={'recipient_id': str(recipient.pk) if recipient else None, 'due_at': due_at.isoformat() if hasattr(due_at, 'isoformat') else str(due_at)}
        )
        return reminder


class EmailOutboxService:
    @staticmethod
    def deliver_pending(limit=100):
        now = timezone.now()
        sent = 0
        for email in EmailOutbox.objects.filter(status='pending', scheduled_at__lte=now).order_by('scheduled_at')[:limit]:
            try:
                send_mail(email.subject, email.body or str(email.context), settings.DEFAULT_FROM_EMAIL, [email.to_email], fail_silently=False)
                email.status = 'sent'
                email.sent_at = now
                email.save(update_fields=['status', 'sent_at', 'updated_at'])
                sent += 1
            except Exception as exc:
                email.retry_count += 1
                email.status = 'failed' if email.retry_count >= 3 else 'pending'
                email.error_message = str(exc)
                email.save(update_fields=['retry_count', 'status', 'error_message', 'updated_at'])
        return sent


class ReminderService:
    @staticmethod
    def send_due_reminders(limit=100):
        now = timezone.now()
        count = 0
        for reminder in Reminder.objects.select_related('recipient').filter(status='pending', due_at__lte=now)[:limit]:
            NotificationService.notify(
                company=reminder.company,
                recipient=reminder.recipient,
                type_code=reminder.reminder_type,
                title=reminder.title,
                message=reminder.message,
                related_object=reminder.lead,
            )
            reminder.status = 'sent'
            reminder.sent_at = now
            reminder.save(update_fields=['status', 'sent_at', 'updated_at'])
            
            from apps.audit.services.audit import AuditService
            AuditService.log(
                company=reminder.company,
                action='reminder.sent',
                obj=reminder,
                actor_type='system',
                metadata={'recipient_id': str(reminder.recipient.pk) if reminder.recipient else None}
            )
            count += 1
        return count
