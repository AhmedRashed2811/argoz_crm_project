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

    def test_roi_calculations(self):
        from apps.marketing.services.roi_service import ROIService
        from apps.marketing.models import CampaignEvent, SocialMediaAd, SocialMediaPlatformLine, LeadCampaignAttribution, CampaignKPIResult
        from apps.leads.models import Lead
        
        # Setup budget
        CampaignEvent.objects.create(
            campaign=self.campaign,
            event_name='Launch',
            venue_place='HQ',
            event_date='2026-06-15',
            budget=Decimal('1000.00'),
            target_attendees=500
        )
        
        social = SocialMediaAd.objects.create(
            campaign=self.campaign,
            name='FB Ads'
        )
        SocialMediaPlatformLine.objects.create(
            social_ad=social,
            platform='facebook',
            budget=Decimal('600.00'),
            target_value=1000
        )
        
        # Calculate total campaign budget: 1000 + 600 = 1600
        CampaignBudgetService.refresh_total(self.campaign)
        self.assertEqual(self.campaign.total_budget, Decimal('1600.00'))
        
        # Setup attribution
        from apps.leads.models import LeadSource
        source = LeadSource.objects.create(company=self.company, name='Facebook ad')
        lead = Lead.objects.create(
            company=self.company,
            full_name='Lead One',
            phone_number='123456789',
            normalized_phone='123456789',
            source=source
        )
        LeadCampaignAttribution.objects.create(
            lead=lead,
            campaign=self.campaign,
            campaign_type='social_media',
            platform='facebook'
        )
        
        # Recalculate KPIs
        res = ROIService.recalculate_all_kpis(self.campaign)
        self.assertEqual(res['lead_count'], 1)
        self.assertEqual(res['cpl'], Decimal('1600.00'))
        self.assertEqual(res['total_attendees'], 500)
        self.assertEqual(res['cpa'], Decimal('3.20'))
        self.assertEqual(res['platform_metrics']['facebook']['leads'], 1)
        self.assertEqual(res['platform_metrics']['facebook']['cpl'], Decimal('600.00'))
        
        # Verify database records
        leads_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='leads')
        self.assertEqual(leads_kpi.metric_value, Decimal('1.00'))
        
        cpl_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='cost_per_lead')
        self.assertEqual(cpl_kpi.metric_value, Decimal('1600.00'))
        
        attendees_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='attendees')
        self.assertEqual(attendees_kpi.metric_value, Decimal('500.00'))
        
        cpa_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='cost_per_attendee')
        self.assertEqual(cpa_kpi.metric_value, Decimal('3.20'))
        
        fb_leads_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='platform_facebook_leads')
        self.assertEqual(fb_leads_kpi.metric_value, Decimal('1.00'))
        
        fb_cpl_kpi = CampaignKPIResult.objects.get(campaign=self.campaign, metric_code='platform_facebook_cpl')
        self.assertEqual(fb_cpl_kpi.metric_value, Decimal('600.00'))

