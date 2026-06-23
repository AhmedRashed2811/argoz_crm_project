from celery import shared_task
from apps.sla.services.sla import SLAService


@shared_task
def process_expired_slas_task():
    return SLAService.process_expired_slas()
