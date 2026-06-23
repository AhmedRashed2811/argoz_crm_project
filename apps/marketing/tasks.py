from celery import shared_task
from apps.marketing.models import Campaign


@shared_task
def update_campaign_lifecycles_task():
    campaigns = Campaign.objects.filter(is_archived=False)
    count = 0
    for campaign in campaigns:
        old_status = campaign.lifecycle_status_cache
        new_status = campaign.update_lifecycle_status(save=True)
        if old_status != new_status:
            count += 1
    return count


@shared_task(name='apps.marketing.tasks.recalculate_campaign_metrics')
def recalculate_campaign_metrics():
    from apps.marketing.services.roi_service import ROIService
    campaigns = Campaign.objects.filter(is_archived=False, lifecycle_status_cache='active')
    count = 0
    for campaign in campaigns:
        ROIService.recalculate_all_kpis(campaign)
        count += 1
    return count
