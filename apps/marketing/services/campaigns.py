from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time

def as_decimal(value, default='0'):
    try:
        from decimal import Decimal, InvalidOperation
        return Decimal(str(value or default).replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal(default)

def as_int(value, default=0):
    try:
        return int(value or default)
    except ValueError:
        return default

def list_at(values, index, default=''):
    return values[index] if index < len(values) else default
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
        active_types = set(campaign.type_selections.filter(is_active=True).values_list('type_code', flat=True))
        if not active_types:
            raise ValueError('At least one campaign type must be selected before submission/completion.')
        if campaign.events.exists() and 'events' not in active_types:
            raise ValueError('Campaign contains events but does not select "events" type.')
        if campaign.tv_ads.exists() and 'tv_ads' not in active_types:
            raise ValueError('Campaign contains TV ads but does not select "tv_ads" type.')
        if campaign.street_ads.exists() and 'street_ads' not in active_types:
            raise ValueError('Campaign contains street ads but does not select "street_ads" type.')
        if campaign.exhibitions.exists() and 'exhibition' not in active_types:
            raise ValueError('Campaign contains exhibitions but does not select "exhibition" type.')
        if campaign.social_ads.exists() and 'social_media' not in active_types:
            raise ValueError('Campaign contains social media ads but does not select "social_media" type.')
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


class CampaignCreationService:
    @staticmethod
    @transaction.atomic
    def create_campaign(company, user, data):
        campaign = Campaign.objects.create(
            company=company,
            name=data.get('name', '').strip(),
            description=data.get('description', '').strip(),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            target_type=data.get('target_type') or 'other',
            created_by_user=user,
            approval_status=data.get('approval_status') or 'draft',
        )

        campaign_types = data.get('campaign_types', [])
        for code in campaign_types:
            CampaignTypeSelection.objects.get_or_create(campaign=campaign, type_code=code)

        if 'events' in campaign_types:
            for event_data in data.get('events', []):
                event_name = event_data.get('event_name', '').strip()
                if not event_name:
                    continue
                event = CampaignEvent.objects.create(
                    campaign=campaign,
                    event_name=event_name,
                    venue_place=event_data.get('venue_place', ''),
                    event_date=event_data.get('event_date'),
                    budget=event_data.get('budget', Decimal('0.00')),
                    target_attendees=event_data.get('target_attendees') or None,
                    description=event_data.get('description', ''),
                )
                for celeb in event_data.get('celebrities', []):
                    cname = celeb.get('name', '').strip()
                    if cname:
                        EventCelebrity.objects.create(event=event, name=cname, budget=celeb.get('budget', Decimal('0.00')))
                for giveaway in event_data.get('giveaways', []):
                    gname = giveaway.get('name', '').strip()
                    if gname:
                        EventGiveaway.objects.create(event=event, name=gname, budget=giveaway.get('budget', Decimal('0.00')))
                for cater in event_data.get('catering', []):
                    cname = cater.get('name', '').strip()
                    if cname:
                        EventCatering.objects.create(event=event, name=cname, budget=cater.get('budget', Decimal('0.00')))

        if 'tv_ads' in campaign_types:
            for tv_data in data.get('tv_ads', []):
                tv_name = tv_data.get('name', '').strip()
                if not tv_name:
                    continue
                tv = TVAd.objects.create(
                    campaign=campaign,
                    name=tv_name,
                    start_date=tv_data.get('start_date'),
                    end_date=tv_data.get('end_date'),
                    budget=tv_data.get('budget', Decimal('0.00')),
                    description=tv_data.get('description', ''),
                )
                for ch in tv_data.get('channels', []):
                    ch_name = ch.get('channel_name', '').strip()
                    if ch_name:
                        TVAdChannel.objects.create(tv_ad=tv, channel_name=ch_name, channel_budget=ch.get('channel_budget', Decimal('0.00')))
                for slot in tv_data.get('slots', []):
                    app_time = slot.get('appearance_time')
                    if app_time:
                        TVAdSlot.objects.create(tv_ad=tv, appearance_time=app_time, number_of_appearances=slot.get('number_of_appearances', 1) or 1)

        if 'street_ads' in campaign_types:
            for street_data in data.get('street_ads', []):
                street_name = street_data.get('name', '').strip()
                if not street_name:
                    continue
                street = StreetAd.objects.create(
                    campaign=campaign,
                    name=street_name,
                    start_date=street_data.get('start_date'),
                    end_date=street_data.get('end_date'),
                    budget=street_data.get('budget', Decimal('0.00')),
                    description=street_data.get('description', ''),
                )
                for type_line in street_data.get('type_lines', []):
                    ad_type = type_line.get('ad_type')
                    if not ad_type:
                        continue
                    line = StreetAdTypeLine.objects.create(
                        street_ad=street,
                        ad_type=ad_type,
                        total_number=type_line.get('total_number', 1) or 1,
                        budget=type_line.get('budget', Decimal('0.00')),
                    )
                    loc = type_line.get('location', '').strip()
                    if loc:
                        StreetAdLocation.objects.create(type_line=line, location=loc, budget=type_line.get('location_budget', Decimal('0.00')))

        if 'exhibition' in campaign_types:
            for ex_data in data.get('exhibitions', []):
                ex_name = ex_data.get('name', '').strip()
                if not ex_name:
                    continue
                ExhibitionRecord.objects.create(
                    campaign=campaign,
                    name=ex_name,
                    place=ex_data.get('place', ''),
                    start_date=ex_data.get('start_date'),
                    end_date=ex_data.get('end_date'),
                    budget=ex_data.get('budget', Decimal('0.00')),
                )

        if 'social_media' in campaign_types:
            for social_data in data.get('social_ads', []):
                social_name = social_data.get('name', '').strip()
                if not social_name:
                    continue
                ad = SocialMediaAd.objects.create(
                    campaign=campaign,
                    name=social_name,
                    target_kpi=social_data.get('target_kpi', ''),
                    description=social_data.get('description', ''),
                )
                for line in social_data.get('platforms', []):
                    platform = line.get('platform')
                    if platform:
                        SocialMediaPlatformLine.objects.create(
                            social_ad=ad,
                            platform=platform,
                            budget=line.get('budget', Decimal('0.00')),
                            target_value=line.get('target_value', Decimal('0.00')),
                        )

        for cost_data in data.get('other_costs', []):
            cost_val = cost_data.get('value')
            cost_reason = cost_data.get('reason', '').strip()
            if cost_val is not None:
                if not cost_reason:
                    raise ValueError("Other cost reason is required.")
                CampaignOtherCost.objects.create(
                    campaign=campaign,
                    value=cost_val,
                    reason=cost_reason,
                    cost_created_by=user,
                )

        CampaignBudgetService.refresh_total(campaign, actor=user)

        if campaign.approval_status != 'draft':
            CampaignValidationService.validate_has_type_selection(campaign)

        AuditService.log(
            company=campaign.company,
            actor=user,
            action='campaign.created',
            obj=campaign,
            after={'name': campaign.name, 'target_type': campaign.target_type}
        )
        return campaign

    @classmethod
    @transaction.atomic
    def create_campaign_from_post(cls, company, user, post_data):
        selected = post_data.getlist('campaign_types')

        events_payload = []
        if 'events' in selected:
            names = post_data.getlist('event_name[]')
            for i, name in enumerate(names):
                if not name.strip():
                    continue
                celebrities = []
                for cname, cbudget in zip(post_data.getlist(f'event_celebrity_name_{i}[]'), post_data.getlist(f'event_celebrity_budget_{i}[]')):
                    if cname.strip():
                        celebrities.append({'name': cname.strip(), 'budget': as_decimal(cbudget)})
                giveaways = []
                for gname, gbudget in zip(post_data.getlist(f'event_giveaway_name_{i}[]'), post_data.getlist(f'event_giveaway_budget_{i}[]')):
                    if gname.strip():
                        giveaways.append({'name': gname.strip(), 'budget': as_decimal(gbudget)})
                catering = []
                for cname, cbudget in zip(post_data.getlist(f'event_catering_name_{i}[]'), post_data.getlist(f'event_catering_budget_{i}[]')):
                    if cname.strip():
                        catering.append({'name': cname.strip(), 'budget': as_decimal(cbudget)})

                events_payload.append({
                    'event_name': name.strip(),
                    'venue_place': list_at(post_data.getlist('event_venue[]'), i),
                    'event_date': parse_date(list_at(post_data.getlist('event_date[]'), i)),
                    'budget': as_decimal(list_at(post_data.getlist('event_budget[]'), i, '0')),
                    'target_attendees': as_int(list_at(post_data.getlist('event_attendees[]'), i, '0')) or None,
                    'description': list_at(post_data.getlist('event_description[]'), i),
                    'celebrities': celebrities,
                    'giveaways': giveaways,
                    'catering': catering,
                })

        tv_payload = []
        if 'tv_ads' in selected:
            names = post_data.getlist('tv_name[]')
            for i, name in enumerate(names):
                if not name.strip():
                    continue
                channels = []
                for ch, budget in zip(post_data.getlist(f'tv_channel_name_{i}[]'), post_data.getlist(f'tv_channel_budget_{i}[]')):
                    if ch.strip():
                        channels.append({'channel_name': ch.strip(), 'channel_budget': as_decimal(budget)})
                slots = []
                for t, n in zip(post_data.getlist(f'tv_slot_time_{i}[]'), post_data.getlist(f'tv_slot_count_{i}[]')):
                    if t:
                        slots.append({'appearance_time': parse_time(t), 'number_of_appearances': as_int(n, 1) or 1})
                tv_payload.append({
                    'name': name.strip(),
                    'start_date': parse_date(list_at(post_data.getlist('tv_start_date[]'), i)),
                    'end_date': parse_date(list_at(post_data.getlist('tv_end_date[]'), i)),
                    'budget': as_decimal(list_at(post_data.getlist('tv_budget[]'), i, '0')),
                    'description': list_at(post_data.getlist('tv_description[]'), i),
                    'channels': channels,
                    'slots': slots,
                })

        street_payload = []
        if 'street_ads' in selected:
            names = post_data.getlist('street_name[]')
            for i, name in enumerate(names):
                if not name.strip():
                    continue
                type_lines = []
                types = post_data.getlist(f'street_type_{i}[]')
                numbers = post_data.getlist(f'street_type_number_{i}[]')
                budgets = post_data.getlist(f'street_type_budget_{i}[]')
                locations = post_data.getlist(f'street_type_location_{i}[]')
                location_budgets = post_data.getlist(f'street_type_location_budget_{i}[]')
                for j, ad_type in enumerate(types):
                    if not ad_type:
                        continue
                    type_lines.append({
                        'ad_type': ad_type,
                        'total_number': as_int(numbers[j] if j < len(numbers) else 1, 1),
                        'budget': as_decimal(budgets[j] if j < len(budgets) else 0),
                        'location': locations[j] if j < len(locations) else '',
                        'location_budget': as_decimal(location_budgets[j] if j < len(location_budgets) else 0),
                    })
                street_payload.append({
                    'name': name.strip(),
                    'start_date': parse_date(list_at(post_data.getlist('street_start_date[]'), i)),
                    'end_date': parse_date(list_at(post_data.getlist('street_end_date[]'), i)),
                    'budget': as_decimal(list_at(post_data.getlist('street_budget[]'), i, '0')),
                    'description': list_at(post_data.getlist('street_description[]'), i),
                    'type_lines': type_lines,
                })

        exhibition_payload = []
        if 'exhibition' in selected:
            names = post_data.getlist('exhibition_name[]')
            for i, name in enumerate(names):
                if not name.strip():
                    continue
                exhibition_payload.append({
                    'name': name.strip(),
                    'place': list_at(post_data.getlist('exhibition_place[]'), i),
                    'start_date': parse_date(list_at(post_data.getlist('exhibition_start_date[]'), i)),
                    'end_date': parse_date(list_at(post_data.getlist('exhibition_end_date[]'), i)),
                    'budget': as_decimal(list_at(post_data.getlist('exhibition_budget[]'), i, '0')),
                })

        social_payload = []
        if 'social_media' in selected:
            names = post_data.getlist('social_name[]')
            for i, name in enumerate(names):
                if not name.strip():
                    continue
                platforms = []
                plat_names = post_data.getlist(f'social_platform_{i}[]')
                plat_budgets = post_data.getlist(f'social_platform_budget_{i}[]')
                plat_targets = post_data.getlist(f'social_platform_target_{i}[]')
                for j, platform in enumerate(plat_names):
                    if platform:
                        platforms.append({
                            'platform': platform,
                            'budget': as_decimal(plat_budgets[j] if j < len(plat_budgets) else 0),
                            'target_value': as_decimal(plat_targets[j] if j < len(plat_targets) else 0),
                        })
                social_payload.append({
                    'name': name.strip(),
                    'target_kpi': list_at(post_data.getlist('social_target_kpi[]'), i),
                    'description': list_at(post_data.getlist('social_description[]'), i),
                    'platforms': platforms,
                })

        other_payload = []
        values = post_data.getlist('other_cost_value[]')
        reasons = post_data.getlist('other_cost_reason[]')
        for i, value in enumerate(values):
            reason = reasons[i] if i < len(reasons) else ''
            if value or reason.strip():
                other_payload.append({
                    'value': as_decimal(value) if value else None,
                    'reason': reason.strip(),
                })

        payload = {
            'name': post_data.get('name', '').strip(),
            'description': post_data.get('description', '').strip(),
            'start_date': parse_date(post_data.get('start_date')),
            'end_date': parse_date(post_data.get('end_date')),
            'target_type': post_data.get('target_type') or 'other',
            'campaign_types': selected,
            'events': events_payload,
            'tv_ads': tv_payload,
            'street_ads': street_payload,
            'exhibitions': exhibition_payload,
            'social_ads': social_payload,
            'other_costs': other_payload,
        }

        return cls.create_campaign(company=company, user=user, data=payload)
