from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.marketing.models import (
    Campaign, CampaignTypeSelection, CampaignEvent, EventCelebrity, EventGiveaway, EventCatering,
    TVAd, TVAdChannel, TVAdSlot, StreetAd, StreetAdTypeLine, StreetAdLocation,
    ExhibitionRecord, SocialMediaAd, SocialMediaPlatformLine, CampaignOtherCost,
    CampaignApprovalHistory, CampaignKPIResult, CampaignAsset, LeadCampaignAttribution,
)
from apps.audit.services.audit import AuditService
from apps.notifications.services.notifications import NotificationService


class CampaignBudgetService:
    @staticmethod
    def calculate(campaign: Campaign):
        total = Decimal('0')
        total += sum(e.budget for e in campaign.events.all())
        for event in campaign.events.all():
            total += sum(x.budget for x in event.celebrities.all())
            total += sum(x.budget for x in event.giveaways.all())
            total += sum(x.budget for x in event.catering_items.all())
        total += sum(tv.budget for tv in campaign.tv_ads.all())
        for tv in campaign.tv_ads.all():
            total += sum(ch.channel_budget for ch in tv.channels.all())
        total += sum(st.budget for st in campaign.street_ads.all())
        for st in campaign.street_ads.all():
            total += sum(line.budget for line in st.type_lines.all())
            for line in st.type_lines.all():
                total += sum(loc.budget for loc in line.locations.all())
        total += sum(ex.budget for ex in campaign.exhibitions.all())
        for ad in campaign.social_ads.all():
            total += sum(line.budget for line in ad.platform_lines.all())
        total += sum(cost.value for cost in campaign.other_costs.all())
        return total

    @staticmethod
    def refresh_total(campaign: Campaign):
        old_total = campaign.total_budget
        campaign.total_budget = CampaignBudgetService.calculate(campaign)
        campaign.save(update_fields=['total_budget', 'updated_at'])
        if old_total != campaign.total_budget:
            AuditService.log(
                company=campaign.company, actor_type='system',
                action='campaign.budget_recalculated', obj=campaign,
                before={'total_budget': str(old_total)},
                after={'total_budget': str(campaign.total_budget)},
            )
        return campaign.total_budget


class CampaignApprovalService:
    @staticmethod
    @transaction.atomic
    def decide(*, campaign: Campaign, new_status: str, actor=None, reason=''):
        if new_status in ('semi_approved', 'not_approved') and not reason:
            raise ValueError('Reason is mandatory for Semi Approved and Not Approved decisions.')
        old_status = campaign.approval_status
        campaign.approval_status = new_status
        campaign.save(update_fields=['approval_status', 'updated_at'])
        CampaignApprovalHistory.objects.create(
            campaign=campaign, old_status=old_status, new_status=new_status,
            reason=reason, decided_by=actor,
        )
        AuditService.log(
            company=campaign.company, actor=actor, action='campaign.approval_decided',
            obj=campaign, before={'approval_status': old_status},
            after={'approval_status': new_status, 'reason': reason},
        )
        # Notify campaign creator about the decision
        if campaign.created_by_user and campaign.created_by_user != actor:
            status_labels = dict(Campaign.APPROVAL_CHOICES)
            NotificationService.notify(
                company=campaign.company,
                recipient=campaign.created_by_user,
                type_code='campaign_approval_decided',
                title=f'Campaign "{campaign.name}" – {status_labels.get(new_status, new_status)}',
                message=f'Campaign "{campaign.name}" has been {status_labels.get(new_status, new_status).lower()}. Reason: {reason or "N/A"}',
                related_object=campaign,
                channels=['in_app', 'email'],
            )
        return campaign


class CampaignROIService:
    @staticmethod
    def refresh_basic_metrics(campaign: Campaign):
        lead_count = campaign.lead_attributions.count() or campaign.leads.count()
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign, metric_code='leads',
            defaults={'metric_value': lead_count},
        )
        if lead_count and campaign.total_budget:
            cpl = campaign.total_budget / lead_count
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign, metric_code='cost_per_lead',
                defaults={'metric_value': cpl},
            )

        # --- Attendee metrics for events ---
        total_attendees = 0
        for event in campaign.events.all():
            attendees = event.target_attendees or 0
            total_attendees += attendees
        if total_attendees:
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign, metric_code='attendees',
                defaults={'metric_value': total_attendees},
            )
            if campaign.total_budget:
                cpa = campaign.total_budget / total_attendees
                CampaignKPIResult.objects.update_or_create(
                    campaign=campaign, metric_code='cost_per_attendee',
                    defaults={'metric_value': cpa},
                )

        # --- Platform performance ---
        for ad in campaign.social_ads.all():
            for platform_line in ad.platform_lines.all():
                platform_leads = LeadCampaignAttribution.objects.filter(
                    campaign=campaign, platform=platform_line.platform,
                ).count()
                metric_key = f'platform_{platform_line.platform}_leads'
                CampaignKPIResult.objects.update_or_create(
                    campaign=campaign, metric_code=metric_key,
                    defaults={'metric_value': platform_leads},
                )
                if platform_line.budget and platform_leads:
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign, metric_code=f'platform_{platform_line.platform}_cpl',
                        defaults={'metric_value': platform_line.budget / platform_leads},
                    )

        return lead_count


class CampaignService:
    @staticmethod
    @transaction.atomic
    def duplicate_campaign(campaign: Campaign, *, actor=None):
        """Duplicate a campaign with all child records (events, TV ads, street ads, exhibitions, social ads, other costs)."""
        original_id = campaign.pk
        new_campaign = Campaign.objects.create(
            company=campaign.company,
            name=f'{campaign.name} (Copy)',
            description=campaign.description,
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            target_type=campaign.target_type,
            target_object_id=campaign.target_object_id,
            total_budget=Decimal('0'),
            approval_status='pending',
            created_by_user=actor,
        )
        # Type selections
        for ts in CampaignTypeSelection.objects.filter(campaign_id=original_id):
            CampaignTypeSelection.objects.create(campaign=new_campaign, type_code=ts.type_code, is_active=ts.is_active)

        # Events + sub-records
        for event in CampaignEvent.objects.filter(campaign_id=original_id):
            new_event = CampaignEvent.objects.create(
                campaign=new_campaign, event_name=event.event_name, venue_place=event.venue_place,
                event_date=event.event_date, budget=event.budget, target_attendees=event.target_attendees,
                description=event.description,
            )
            for celeb in event.celebrities.all():
                EventCelebrity.objects.create(event=new_event, name=celeb.name, budget=celeb.budget)
            for giveaway in event.giveaways.all():
                EventGiveaway.objects.create(event=new_event, name=giveaway.name, budget=giveaway.budget)
            for catering in event.catering_items.all():
                EventCatering.objects.create(event=new_event, name=catering.name, budget=catering.budget)

        # TV Ads + channels + slots
        for tv in TVAd.objects.filter(campaign_id=original_id):
            new_tv = TVAd.objects.create(
                campaign=new_campaign, name=tv.name, start_date=tv.start_date,
                end_date=tv.end_date, budget=tv.budget, description=tv.description,
            )
            for ch in tv.channels.all():
                TVAdChannel.objects.create(tv_ad=new_tv, channel_name=ch.channel_name, channel_budget=ch.channel_budget)
            for slot in tv.slots.all():
                TVAdSlot.objects.create(tv_ad=new_tv, appearance_time=slot.appearance_time, number_of_appearances=slot.number_of_appearances)

        # Street Ads + type lines + locations
        for st in StreetAd.objects.filter(campaign_id=original_id):
            new_st = StreetAd.objects.create(
                campaign=new_campaign, name=st.name, start_date=st.start_date,
                end_date=st.end_date, budget=st.budget, description=st.description,
            )
            for line in st.type_lines.all():
                new_line = StreetAdTypeLine.objects.create(street_ad=new_st, ad_type=line.ad_type, total_number=line.total_number, budget=line.budget)
                for loc in line.locations.all():
                    StreetAdLocation.objects.create(type_line=new_line, location=loc.location, budget=loc.budget)

        # Exhibitions
        for ex in ExhibitionRecord.objects.filter(campaign_id=original_id):
            ExhibitionRecord.objects.create(
                campaign=new_campaign, name=ex.name, place=ex.place,
                start_date=ex.start_date, end_date=ex.end_date, budget=ex.budget,
            )

        # Social Media Ads + platform lines
        for ad in SocialMediaAd.objects.filter(campaign_id=original_id):
            new_ad = SocialMediaAd.objects.create(
                campaign=new_campaign, name=ad.name, target_kpi=ad.target_kpi, description=ad.description,
            )
            for pl in ad.platform_lines.all():
                SocialMediaPlatformLine.objects.create(social_ad=new_ad, platform=pl.platform, budget=pl.budget, target_value=pl.target_value)

        # Other Costs
        for cost in CampaignOtherCost.objects.filter(campaign_id=original_id):
            CampaignOtherCost.objects.create(campaign=new_campaign, value=cost.value, reason=cost.reason, cost_created_by=actor)

        CampaignBudgetService.refresh_total(new_campaign)
        AuditService.log(
            company=new_campaign.company, actor=actor, action='campaign.duplicated',
            obj=new_campaign, metadata={'original_campaign_id': str(original_id)},
        )
        return new_campaign

    @staticmethod
    @transaction.atomic
    def archive_campaign(campaign: Campaign, *, actor=None):
        """Archive a campaign – soft-delete."""
        campaign.is_archived = True
        campaign.save(update_fields=['is_archived', 'updated_at'])
        AuditService.log(
            company=campaign.company, actor=actor, action='campaign.archived',
            obj=campaign,
        )
        return campaign


class CampaignAttributionService:
    """Service to manage lead-to-campaign attribution."""

    @staticmethod
    def attribute_lead(*, lead, campaign, campaign_type='', child_object_id=None,
                       platform='', tracking_method='manual'):
        """Create or update a lead-campaign attribution record."""
        attr, created = LeadCampaignAttribution.objects.get_or_create(
            lead=lead, campaign=campaign,
            defaults={
                'campaign_type': campaign_type,
                'child_object_id': child_object_id,
                'platform': platform,
                'tracking_method': tracking_method,
            },
        )
        if not created:
            attr.campaign_type = campaign_type or attr.campaign_type
            attr.child_object_id = child_object_id or attr.child_object_id
            attr.platform = platform or attr.platform
            attr.tracking_method = tracking_method
            attr.save(update_fields=['campaign_type', 'child_object_id', 'platform', 'tracking_method', 'updated_at'])
        return attr

    @staticmethod
    def leads_for_campaign(campaign):
        """Return all leads attributed to a campaign."""
        from apps.leads.models import Lead
        return Lead.objects.filter(campaign_attributions__campaign=campaign).distinct()
