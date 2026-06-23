from celery import shared_task
from apps.sla.services.sla import SLAService


@shared_task(name='apps.sla.tasks.check_sla_expiry')
def check_sla_expiry():
    return SLAService.process_expired_slas()
