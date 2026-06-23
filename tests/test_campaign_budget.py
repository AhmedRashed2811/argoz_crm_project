from django.test import TestCase
from decimal import Decimal
from apps.companies.models import Company
from apps.marketing.models import (
    Campaign, CampaignEvent, EventCelebrity, EventGiveaway, EventCatering,
    TVAd, TVAdChannel, StreetAd, StreetAdTypeLine, StreetAdLocation,
    ExhibitionRecord, SocialMediaAd, SocialMediaPlatformLine, CampaignOtherCost
)
from apps.marketing.services.campaigns import CampaignBudgetService, CampaignService

class CampaignBudgetTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.campaign = Campaign.objects.create(
            company=self.company,
            name='Summer Campaign',
            start_date='2026-06-01',
            end_date='2026-08-31'
        )

    def test_budget_calculation(self):
        # 1. Event budget: 1000 + 500 (celeb) + 200 (giveaway) + 300 (catering) = 2000
        event = CampaignEvent.objects.create(campaign=self.campaign, event_name='Launch', venue_place='HQ', event_date='2026-06-15', budget=Decimal('1000.00'))
        EventCelebrity.objects.create(event=event, name='Star', budget=Decimal('500.00'))
        EventGiveaway.objects.create(event=event, name='Pens', budget=Decimal('200.00'))
        EventCatering.objects.create(event=event, name='Catering', budget=Decimal('300.00'))
        
        # 2. TV Ad budget: 5000 + 1500 (channel) = 6500
        tv = TVAd.objects.create(campaign=self.campaign, name='TV Spot', start_date='2026-06-01', end_date='2026-06-30', budget=Decimal('5000.00'))
        TVAdChannel.objects.create(tv_ad=tv, channel_name='Channel 1', channel_budget=Decimal('1500.00'))
        
        # 3. Other cost budget: 1500
        CampaignOtherCost.objects.create(campaign=self.campaign, value=Decimal('1500.00'), reason='Print items')
        
        # Total expected budget = 2000 + 6500 + 1500 = 10000
        total = CampaignBudgetService.calculate(self.campaign)
        self.assertEqual(total, Decimal('10000.00'))

    def test_campaign_duplication(self):
        CampaignEvent.objects.create(campaign=self.campaign, event_name='Launch', venue_place='HQ', event_date='2026-06-15', budget=Decimal('1000.00'))
        
        new_camp = CampaignService.duplicate_campaign(self.campaign)
        self.assertEqual(new_camp.name, 'Summer Campaign (Copy)')
        self.assertEqual(new_camp.events.count(), 1)
