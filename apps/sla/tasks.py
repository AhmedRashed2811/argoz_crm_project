from celery import shared_task
from django.utils import timezone
from apps.sla.services.sla import SLAService


@shared_task(name='apps.sla.tasks.check_sla_expiry')
def check_sla_expiry():
    """Find expired SLA IDs and dispatch one task per instance."""
    from apps.sla.selectors import get_expired_sla_instance_ids
    ids = get_expired_sla_instance_ids(limit=200, now=timezone.now())
    for sla_id in ids:
        process_single_sla.delay(str(sla_id))
    return len(ids)


@shared_task(name='apps.sla.tasks.process_single_sla', max_retries=2, default_retry_delay=60)
def process_single_sla(sla_id):
    """Process one expired SLA instance in isolation."""
    from apps.sla.models import LeadSLAInstance
    from apps.sla.selectors import get_sla_instance_for_update
    from django.db import transaction

    with transaction.atomic():
        try:
            sla = get_sla_instance_for_update(sla_id)
        except LeadSLAInstance.DoesNotExist:
            return
        if sla.status != 'active' or sla.due_at > timezone.now():
            return
        SLAService.process_single_expired_sla(sla)
