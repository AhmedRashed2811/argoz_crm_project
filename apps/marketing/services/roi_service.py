from decimal import Decimal
from django.db import transaction
from apps.marketing.models import Campaign, CampaignKPIResult, LeadCampaignAttribution

class ROIService:
    @staticmethod
    def calculate_cpl(campaign: Campaign):
        """Calculates lead count and Cost Per Lead (CPL) for a campaign and updates CampaignKPIResult."""
        lead_count = campaign.lead_attributions.count() or campaign.leads.count()
        cpl = Decimal('0.00')
        
        # Save lead count KPI
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='leads',
            defaults={'metric_value': Decimal(lead_count)}
        )
        
        # Save CPL KPI
        if lead_count > 0:
            total_budget = campaign.total_budget or Decimal('0.00')
            cpl = Decimal(total_budget) / Decimal(lead_count)
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='cost_per_lead',
                defaults={'metric_value': cpl}
            )
        else:
            # Delete/remove CPL if no leads (or set to 0)
            CampaignKPIResult.objects.filter(campaign=campaign, metric_code='cost_per_lead').delete()
            
        return lead_count, cpl

    @staticmethod
    def calculate_event_roi(campaign: Campaign):
        """Calculates total event target attendees and Cost Per Attendee (CPA) and updates CampaignKPIResult."""
        total_attendees = sum(event.target_attendees or 0 for event in campaign.events.all())
        cpa = Decimal('0.00')
        
        # Save target attendees KPI
        if total_attendees > 0:
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='attendees',
                defaults={'metric_value': Decimal(total_attendees)}
            )
            
            # Save CPA KPI
            total_budget = campaign.total_budget or Decimal('0.00')
            cpa = Decimal(total_budget) / Decimal(total_attendees)
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='cost_per_attendee',
                defaults={'metric_value': cpa}
            )
        else:
            # Clean up event KPIs if no attendees
            CampaignKPIResult.objects.filter(campaign=campaign, metric_code__in=['attendees', 'cost_per_attendee']).delete()
            
        return total_attendees, cpa

    @staticmethod
    def calculate_platform_performance(campaign: Campaign):
        """Calculates leads and Cost Per Lead for each social media platform in the campaign."""
        platform_metrics = {}
        
        # Gather all platform metrics currently configured
        active_platforms = set()
        for ad in campaign.social_ads.all():
            for platform_line in ad.platform_lines.all():
                platform = platform_line.platform
                if not platform:
                    continue
                active_platforms.add(platform)
                
                # Count leads matching campaign and platform
                platform_leads = LeadCampaignAttribution.objects.filter(
                    campaign=campaign,
                    platform=platform
                ).count()
                
                # Update platform leads KPI
                CampaignKPIResult.objects.update_or_create(
                    campaign=campaign,
                    metric_code=f'platform_{platform}_leads',
                    defaults={'metric_value': Decimal(platform_leads)}
                )
                
                # Calculate and update platform CPL KPI
                platform_budget = platform_line.budget or Decimal('0.00')
                platform_cpl = Decimal('0.00')
                if platform_leads > 0:
                    platform_cpl = Decimal(platform_budget) / Decimal(platform_leads)
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign,
                        metric_code=f'platform_{platform}_cpl',
                        defaults={'metric_value': platform_cpl}
                    )
                else:
                    CampaignKPIResult.objects.filter(campaign=campaign, metric_code=f'platform_{platform}_cpl').delete()
                    
                platform_metrics[platform] = {
                    'leads': platform_leads,
                    'cpl': platform_cpl
                }
                
        # Clean up stale platform KPIs for platforms not in active platforms list
        all_platform_kpis = CampaignKPIResult.objects.filter(campaign=campaign, metric_code__startswith='platform_')
        for kpi in all_platform_kpis:
            # Expose platform name from metric_code
            parts = kpi.metric_code.split('_')
            if len(parts) >= 3:
                platform_name = parts[1]
                if platform_name not in active_platforms:
                    kpi.delete()
                    
        return platform_metrics

    @classmethod
    @transaction.atomic
    def recalculate_all_kpis(cls, campaign: Campaign):
        """Recalculates CPL, Event ROI, and Platform Performance and updates KPI results."""
        lead_count, cpl = cls.calculate_cpl(campaign)
        total_attendees, cpa = cls.calculate_event_roi(campaign)
        platform_metrics = cls.calculate_platform_performance(campaign)
        
        return {
            'lead_count': lead_count,
            'cpl': cpl,
            'total_attendees': total_attendees,
            'cpa': cpa,
            'platform_metrics': platform_metrics
        }
