from celery import shared_task
from apps.notifications.services.notifications import EmailOutboxService, ReminderService


@shared_task(name='apps.notifications.tasks.send_email_outbox')
def send_email_outbox():
    return EmailOutboxService.deliver_pending()


@shared_task(name='apps.notifications.tasks.send_due_reminders')
def send_due_reminders():
    return ReminderService.send_due_reminders()
