from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.marketing.models import (
    Campaign, CampaignEvent, EventCelebrity, EventGiveaway, EventCatering,
    TVAd, TVAdChannel, StreetAd, StreetAdTypeLine, StreetAdLocation,
    ExhibitionRecord, SocialMediaPlatformLine, CampaignOtherCost
)
from apps.marketing.services.campaigns import CampaignBudgetService

def _refresh_campaign_budget(instance):
    campaign = None
    try:
        if isinstance(instance, Campaign):
            campaign = instance
        elif isinstance(instance, (CampaignEvent, TVAd, StreetAd, ExhibitionRecord, CampaignOtherCost)):
            campaign = instance.campaign
        elif isinstance(instance, (EventCelebrity, EventGiveaway, EventCatering)):
            campaign = instance.event.campaign
        elif isinstance(instance, TVAdChannel):
            campaign = instance.tv_ad.campaign
        elif isinstance(instance, StreetAdTypeLine):
            campaign = instance.street_ad.campaign
        elif isinstance(instance, StreetAdLocation):
            campaign = instance.type_line.street_ad.campaign
        elif isinstance(instance, SocialMediaPlatformLine):
            campaign = instance.social_ad.campaign
    except Exception:
        pass

    if campaign:
        try:
            CampaignBudgetService.refresh_total(campaign)
        except Exception:
            pass

@receiver(post_save, sender=CampaignEvent)
@receiver(post_save, sender=EventCelebrity)
@receiver(post_save, sender=EventGiveaway)
@receiver(post_save, sender=EventCatering)
@receiver(post_save, sender=TVAd)
@receiver(post_save, sender=TVAdChannel)
@receiver(post_save, sender=StreetAd)
@receiver(post_save, sender=StreetAdTypeLine)
@receiver(post_save, sender=StreetAdLocation)
@receiver(post_save, sender=ExhibitionRecord)
@receiver(post_save, sender=SocialMediaPlatformLine)
@receiver(post_save, sender=CampaignOtherCost)
def budget_item_saved(sender, instance, **kwargs):
    _refresh_campaign_budget(instance)

@receiver(post_delete, sender=CampaignEvent)
@receiver(post_delete, sender=EventCelebrity)
@receiver(post_delete, sender=EventGiveaway)
@receiver(post_delete, sender=EventCatering)
@receiver(post_delete, sender=TVAd)
@receiver(post_delete, sender=TVAdChannel)
@receiver(post_delete, sender=StreetAd)
@receiver(post_delete, sender=StreetAdTypeLine)
@receiver(post_delete, sender=StreetAdLocation)
@receiver(post_delete, sender=ExhibitionRecord)
@receiver(post_delete, sender=SocialMediaPlatformLine)
@receiver(post_delete, sender=CampaignOtherCost)
def budget_item_deleted(sender, instance, **kwargs):
    _refresh_campaign_budget(instance)
