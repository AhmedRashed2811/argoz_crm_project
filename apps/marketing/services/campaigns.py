from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.core.services.policies import PolicyResolver
from apps.marketing.models import (
    Campaign, CampaignTypeSelection, CampaignEvent, EventCelebrity, EventGiveaway, EventCatering,
    TVAd, TVAdChannel, TVAdSlot, StreetAd, StreetAdTypeLine, StreetAdLocation,
    ExhibitionRecord, SocialMediaAd, SocialMediaPlatformLine, CampaignOtherCost,
    CampaignApprovalHistory, LeadCampaignAttribution,
)
from apps.audit.services.audit import AuditService
from apps.notifications.services.notifications import NotificationService


class CampaignValidationService:
    """Backend validation rules from the Marketing Functional Specification."""

    @staticmethod
    def _assert_non_negative(value, label):
        if value is not None and Decimal(value) < Decimal('0'):
            raise ValueError(f'{label} must be non-negative EGP value.')

    @classmethod
    def validate_master(cls, campaign: Campaign):
        if not campaign.name:
            raise ValueError('Campaign name is required.')
        if campaign.start_date and campaign.end_date and campaign.end_date < campaign.start_date:
            raise ValueError('Campaign end date must be equal to or after the start date.')
        return True

    @classmethod
    def validate_has_type_selection(cls, campaign: Campaign):
        if not campaign.type_selections.filter(is_active=True).exists():
            raise ValueError('At least one campaign type must be selected before submission/completion.')
        return True

    @classmethod
    def validate_child_dates(cls, campaign: Campaign):
        def check_range(label, start_date=None, end_date=None, exact_date=None):
            if exact_date and campaign.start_date and campaign.end_date:
                if not (campaign.start_date <= exact_date <= campaign.end_date):
                    raise ValueError(f'{label} date must be inside the campaign period.')
            if start_date and end_date and end_date < start_date:
                raise ValueError(f'{label} end date must be equal to or after start date.')
            if start_date and campaign.start_date and start_date < campaign.start_date:
                raise ValueError(f'{label} start date must not be before campaign start date.')
            if end_date and campaign.end_date and end_date > campaign.end_date:
                raise ValueError(f'{label} end date must not be after campaign end date.')

        for event in campaign.events.all():
            check_range(f'Event "{event.event_name}"', exact_date=event.event_date)
        for tv in campaign.tv_ads.all():
            check_range(f'TV Ad "{tv.name}"', tv.start_date, tv.end_date)
        for street in campaign.street_ads.all():
            check_range(f'Street Ad "{street.name}"', street.start_date, street.end_date)
        for ex in campaign.exhibitions.all():
            check_range(f'Exhibition "{ex.name}"', ex.start_date, ex.end_date)
        return True

    @classmethod
    def validate_budgets(cls, campaign: Campaign):
        cls._assert_non_negative(campaign.total_budget, 'Campaign total budget')
        for event in campaign.events.all():
            cls._assert_non_negative(event.budget, f'Event {event.event_name} budget')
            for child in list(event.celebrities.all()) + list(event.giveaways.all()) + list(event.catering_items.all()):
                cls._assert_non_negative(child.budget, f'{child.__class__.__name__} budget')
        for tv in campaign.tv_ads.all():
            cls._assert_non_negative(tv.budget, f'TV Ad {tv.name} budget')
            for ch in tv.channels.all():
                cls._assert_non_negative(ch.channel_budget, f'TV channel {ch.channel_name} budget')
        for st in campaign.street_ads.all():
            cls._assert_non_negative(st.budget, f'Street Ad {st.name} budget')
            for line in st.type_lines.all():
                cls._assert_non_negative(line.budget, f'Street ad type {line.ad_type} budget')
                for loc in line.locations.all():
                    cls._assert_non_negative(loc.budget, f'Street ad location budget')
        for ex in campaign.exhibitions.all():
            cls._assert_non_negative(ex.budget, f'Exhibition {ex.name} budget')
        for ad in campaign.social_ads.all():
            for line in ad.platform_lines.all():
                cls._assert_non_negative(line.budget, f'Social platform {line.platform} budget')
        for cost in campaign.other_costs.all():
            cls._assert_non_negative(cost.value, 'Other cost')
            if not cost.reason or not cost.reason.strip():
                raise ValueError("Other cost reason is required.")
        return True

    @classmethod
    def validate_assets(cls, campaign: Campaign):
        for event in campaign.events.all():
            if event.campaign != campaign:
                raise ValueError("Event does not belong to the correct campaign.")
            for celeb in event.celebrities.all():
                if celeb.event.campaign != campaign:
                    raise ValueError("Event Celebrity does not belong to the correct campaign.")
            for giveaway in event.giveaways.all():
                if giveaway.event.campaign != campaign:
                    raise ValueError("Event Giveaway does not belong to the correct campaign.")
            for catering in event.catering_items.all():
                if catering.event.campaign != campaign:
                    raise ValueError("Event Catering does not belong to the correct campaign.")
        for tv in campaign.tv_ads.all():
            if tv.campaign != campaign:
                raise ValueError("TV Ad does not belong to the correct campaign.")
            for ch in tv.channels.all():
                if ch.tv_ad.campaign != campaign:
                    raise ValueError("TV Ad Channel does not belong to the correct campaign.")
            for slot in tv.slots.all():
                if slot.tv_ad.campaign != campaign:
                    raise ValueError("TV Ad Slot does not belong to the correct campaign.")
        for st in campaign.street_ads.all():
            if st.campaign != campaign:
                raise ValueError("Street Ad does not belong to the correct campaign.")
            for line in st.type_lines.all():
                if line.street_ad.campaign != campaign:
                    raise ValueError("Street Ad Type Line does not belong to the correct campaign.")
                for loc in line.locations.all():
                    if loc.type_line.street_ad.campaign != campaign:
                        raise ValueError("Street Ad Location does not belong to the correct campaign.")
        for ex in campaign.exhibitions.all():
            if ex.campaign != campaign:
                raise ValueError("Exhibition does not belong to the correct campaign.")
        for ad in campaign.social_ads.all():
            if ad.campaign != campaign:
                raise ValueError("Social Ad does not belong to the correct campaign.")
            if ad.linked_event and ad.linked_event.campaign != campaign:
                raise ValueError(f"Social Media Ad '{ad.name}' is linked to an Event '{ad.linked_event.event_name}' from a different campaign.")
            for line in ad.platform_lines.all():
                if line.social_ad.campaign != campaign:
                    raise ValueError("Social Ad Platform Line does not belong to the correct campaign.")
        return True

    @classmethod
    def validate_for_submission(cls, campaign: Campaign):
        cls.validate_master(campaign)
        cls.validate_has_type_selection(campaign)
        cls.validate_child_dates(campaign)
        cls.validate_budgets(campaign)
        cls.validate_assets(campaign)
        return True


class CampaignBudgetService:
    @staticmethod
    def calculate(campaign: Campaign):
        total = Decimal('0')
        total += sum((e.budget or Decimal('0')) for e in campaign.events.all())
        for event in campaign.events.all():
            total += sum((x.budget or Decimal('0')) for x in event.celebrities.all())
            total += sum((x.budget or Decimal('0')) for x in event.giveaways.all())
            total += sum((x.budget or Decimal('0')) for x in event.catering_items.all())
        total += sum((tv.budget or Decimal('0')) for tv in campaign.tv_ads.all())
        for tv in campaign.tv_ads.all():
            total += sum((ch.channel_budget or Decimal('0')) for ch in tv.channels.all())
        total += sum((st.budget or Decimal('0')) for st in campaign.street_ads.all())
        for st in campaign.street_ads.all():
            total += sum((line.budget or Decimal('0')) for line in st.type_lines.all())
            for line in st.type_lines.all():
                total += sum((loc.budget or Decimal('0')) for loc in line.locations.all())
        total += sum((ex.budget or Decimal('0')) for ex in campaign.exhibitions.all())
        for ad in campaign.social_ads.all():
            total += sum((line.budget or Decimal('0')) for line in ad.platform_lines.all())
        total += sum((cost.value or Decimal('0')) for cost in campaign.other_costs.all())
        return total.quantize(Decimal('0.01'))

    @staticmethod
    def refresh_total(campaign: Campaign, *, actor=None):
        CampaignValidationService.validate_master(campaign)
        CampaignValidationService.validate_budgets(campaign)
        old_total = campaign.total_budget
        campaign.total_budget = CampaignBudgetService.calculate(campaign)
        campaign.save(update_fields=['total_budget', 'updated_at'])
        if old_total != campaign.total_budget:
            AuditService.log(
                company=campaign.company, actor=actor, actor_type='system' if actor is None else 'user',
                action='campaign.budget_recalculated', obj=campaign,
                before={'total_budget': str(old_total)},
                after={'total_budget': str(campaign.total_budget)},
            )
        return campaign.total_budget


class CampaignApprovalService:
    @staticmethod
    @transaction.atomic
    def submit_for_approval(*, campaign: Campaign, actor=None):
        CampaignValidationService.validate_for_submission(campaign)
        CampaignBudgetService.refresh_total(campaign, actor=actor)
        old_status = campaign.approval_status
        campaign.approval_status = 'pending'
        campaign.save(update_fields=['approval_status', 'updated_at'])
        AuditService.log(
            company=campaign.company, actor=actor, action='campaign.submitted_for_approval',
            obj=campaign, before={'approval_status': old_status}, after={'approval_status': campaign.approval_status},
        )
        return campaign

    @staticmethod
    @transaction.atomic
    def decide(*, campaign: Campaign, new_status: str, actor=None, reason=''):
        if new_status not in dict(Campaign.APPROVAL_CHOICES):
            raise ValueError('Invalid campaign approval status.')
        if PolicyResolver.approval_reason_required(campaign.company, new_status) and not reason:
            raise ValueError('Reason is mandatory for this approval decision.')
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


class CampaignService:
    @staticmethod
    @transaction.atomic
    def duplicate_campaign(campaign: Campaign, *, actor=None):
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
        for ts in CampaignTypeSelection.objects.filter(campaign_id=original_id):
            CampaignTypeSelection.objects.create(campaign=new_campaign, type_code=ts.type_code, is_active=ts.is_active)
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
        for tv in TVAd.objects.filter(campaign_id=original_id):
            new_tv = TVAd.objects.create(
                campaign=new_campaign, name=tv.name, start_date=tv.start_date,
                end_date=tv.end_date, budget=tv.budget, description=tv.description,
            )
            for ch in tv.channels.all():
                TVAdChannel.objects.create(tv_ad=new_tv, channel_name=ch.channel_name, channel_budget=ch.channel_budget)
            for slot in tv.slots.all():
                TVAdSlot.objects.create(tv_ad=new_tv, appearance_time=slot.appearance_time, number_of_appearances=slot.number_of_appearances)
        for st in StreetAd.objects.filter(campaign_id=original_id):
            new_st = StreetAd.objects.create(
                campaign=new_campaign, name=st.name, start_date=st.start_date,
                end_date=st.end_date, budget=st.budget, description=st.description,
            )
            for line in st.type_lines.all():
                new_line = StreetAdTypeLine.objects.create(street_ad=new_st, ad_type=line.ad_type, total_number=line.total_number, budget=line.budget)
                for loc in line.locations.all():
                    StreetAdLocation.objects.create(type_line=new_line, location=loc.location, budget=loc.budget)
        for ex in ExhibitionRecord.objects.filter(campaign_id=original_id):
            ExhibitionRecord.objects.create(
                campaign=new_campaign, name=ex.name, place=ex.place,
                start_date=ex.start_date, end_date=ex.end_date, budget=ex.budget,
            )
        for ad in SocialMediaAd.objects.filter(campaign_id=original_id):
            new_ad = SocialMediaAd.objects.create(
                campaign=new_campaign, name=ad.name, target_kpi=ad.target_kpi,
                linked_event=None, description=ad.description,
            )
            for pl in ad.platform_lines.all():
                SocialMediaPlatformLine.objects.create(social_ad=new_ad, platform=pl.platform, budget=pl.budget, target_value=pl.target_value)
        for cost in CampaignOtherCost.objects.filter(campaign_id=original_id):
            CampaignOtherCost.objects.create(campaign=new_campaign, value=cost.value, reason=cost.reason, cost_created_by=actor)
        CampaignBudgetService.refresh_total(new_campaign, actor=actor)
        AuditService.log(
            company=new_campaign.company, actor=actor, action='campaign.duplicated',
            obj=new_campaign, metadata={'original_campaign_id': str(original_id)},
        )
        return new_campaign

    @staticmethod
    @transaction.atomic
    def archive_campaign(campaign: Campaign, *, actor=None):
        campaign.is_archived = True
        if hasattr(campaign, 'archived_at'):
            campaign.archived_at = timezone.now()
            campaign.save(update_fields=['is_archived', 'archived_at', 'updated_at'])
        else:
            campaign.save(update_fields=['is_archived', 'updated_at'])
        AuditService.log(company=campaign.company, actor=actor, action='campaign.archived', obj=campaign)
        return campaign


class CampaignAttributionService:
    """Service to manage lead-to-campaign attribution."""

    @staticmethod
    def attribute_lead(*, lead, campaign, campaign_type='', child_object_id=None,
                       platform='', tracking_method='manual'):
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
        AuditService.log(
            company=campaign.company, actor_type='system', action='campaign.lead_attributed',
            obj=lead, metadata={'campaign_id': str(campaign.id), 'campaign_type': campaign_type, 'platform': platform},
        )
        return attr

    @staticmethod
    def leads_for_campaign(campaign):
        from apps.leads.models import Lead
        return Lead.objects.filter(campaign_attributions__campaign=campaign).distinct()
