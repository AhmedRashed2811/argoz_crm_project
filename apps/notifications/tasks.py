from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from apps.notifications.services.notifications import EmailOutboxService, ReminderService


@shared_task(name='apps.notifications.tasks.send_email_outbox')
def send_email_outbox():
    return EmailOutboxService.deliver_pending()


@shared_task(name='apps.notifications.tasks.send_due_reminders')
def send_due_reminders():
    return ReminderService.send_due_reminders()


@shared_task(name='apps.notifications.tasks.cleanup_notifications')
def cleanup_notifications(days=90):
    """Archive read notifications older than `days` days."""
    from apps.notifications.models import Notification
    cutoff = timezone.now() - timedelta(days=days)
    updated = Notification.objects.filter(status='read', read_at__lt=cutoff).update(status='archived')
    return updated


@shared_task(name='apps.notifications.tasks.generate_export_file')
def generate_export_file(job_id):
    """Process an ExportJob: generate the file, update job status, notify requester."""
    import csv
    import io
    from apps.notifications.models import ExportJob
    from apps.leads.selectors import get_leads_report_queryset
    from apps.notifications.services.notifications import NotificationService

    try:
        job = ExportJob.objects.select_related('company', 'requested_by').get(pk=job_id)
    except ExportJob.DoesNotExist:
        return

    job.status = 'processing'
    job.save(update_fields=['status', 'updated_at'])

    try:
        if job.export_type == 'leads':
            qs = get_leads_report_queryset(job.company).select_related('source', 'current_stage', 'current_salesman')
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(['ID', 'Full Name', 'Phone', 'Stage', 'Source', 'Salesman', 'Created'])
            row_count = 0
            for lead in qs.iterator(chunk_size=500):
                writer.writerow([
                    str(lead.id), lead.full_name, lead.phone_number,
                    lead.current_stage.name if lead.current_stage else '',
                    lead.source.name if lead.source else '',
                    lead.current_salesman.email if lead.current_salesman else '',
                    lead.created_at.isoformat() if lead.created_at else '',
                ])
                row_count += 1
        else:
            row_count = 0

        job.status = 'done'
        job.row_count = row_count
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'row_count', 'completed_at', 'updated_at'])

        if job.requested_by:
            NotificationService.notify(
                company=job.company,
                recipient=job.requested_by,
                type_code='export_ready',
                title='Export Ready',
                message=f'Your {job.export_type} export ({row_count} rows) is ready.',
            )
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message', 'updated_at'])
