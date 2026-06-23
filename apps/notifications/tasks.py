from celery import shared_task
from apps.notifications.services.notifications import EmailOutboxService, ReminderService


@shared_task
def deliver_email_outbox_task():
    return EmailOutboxService.deliver_pending()


@shared_task
def send_due_reminders_task():
    return ReminderService.send_due_reminders()
