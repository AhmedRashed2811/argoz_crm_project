import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'argoz_crm.settings')

app = Celery('argoz_crm')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
