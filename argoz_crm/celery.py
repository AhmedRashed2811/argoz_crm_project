import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'argoz_crm.settings')

app = Celery('argoz_crm')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Every 5 minutes
    'check-sla-expiry': {
        'task': 'apps.sla.tasks.check_sla_expiry',
        'schedule': crontab(minute='*/5'),
    },
    'send-email-outbox': {
        'task': 'apps.notifications.tasks.send_email_outbox',
        'schedule': crontab(minute='*/5'),
    },
    'send-due-reminders': {
        'task': 'apps.notifications.tasks.send_due_reminders',
        'schedule': crontab(minute='*/5'),
    },
    'retry-failed-webhooks': {
        'task': 'apps.integrations.tasks.retry_failed_webhooks',
        'schedule': crontab(minute='*/10'),
    },
    # Every hour
    'update-campaign-lifecycles': {
        'task': 'apps.marketing.tasks.update_campaign_lifecycles_task',
        'schedule': crontab(minute=0),
    },
    # Daily
    'recalculate-campaign-metrics': {
        'task': 'apps.marketing.tasks.recalculate_campaign_metrics',
        'schedule': crontab(hour=2, minute=0),
    },
    'cleanup-notifications': {
        'task': 'apps.notifications.tasks.cleanup_notifications',
        'schedule': crontab(hour=3, minute=0),
    },
}
