from decimal import Decimal
from django.db import transaction
from apps.marketing.models import Campaign, CampaignKPIResult, LeadCampaignAttribution, EventAttendance


class ROIService:
    @staticmethod
    def calculate_cpl(campaign: Campaign):
        lead_count = campaign.lead_attributions.count() or campaign.leads.count()
        cpl = Decimal('0.00')
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='leads',
            defaults={'metric_value': Decimal(lead_count)},
        )
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='total_cost',
            defaults={'metric_value': campaign.total_budget or Decimal('0.00')},
        )
        if lead_count > 0:
            total_budget = campaign.total_budget or Decimal('0.00')
            cpl = (Decimal(total_budget) / Decimal(lead_count)).quantize(Decimal('0.01'))
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='cost_per_lead',
                defaults={'metric_value': cpl},
            )
        else:
            CampaignKPIResult.objects.filter(campaign=campaign, metric_code='cost_per_lead').delete()
        return lead_count, cpl

    @staticmethod
    def calculate_event_roi(campaign: Campaign):
        total_attendees = sum(event.actual_attendees or 0 for event in campaign.events.all())
        # Also count the actual EventAttendance records if they exist to be safe and accurate
        attendance_count = 0
        for event in campaign.events.all():
            attendance_count += EventAttendance.objects.filter(company=campaign.company, event=event, attended=True).count()
        if attendance_count > 0:
            total_attendees = attendance_count

        cpa = Decimal('0.00')
        if total_attendees > 0:
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='attendees',
                defaults={'metric_value': Decimal(total_attendees)},
            )
            total_budget = campaign.total_budget or Decimal('0.00')
            cpa = (Decimal(total_budget) / Decimal(total_attendees)).quantize(Decimal('0.01'))
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code='cost_per_attendee',
                defaults={'metric_value': cpa},
            )
        else:
            CampaignKPIResult.objects.filter(campaign=campaign, metric_code__in=['attendees', 'cost_per_attendee']).delete()

        # Calculate campaign-level event attendance KPI metrics
        kpi_target = sum(event.target_attendees or 0 for event in campaign.events.all())
        kpi_actual = total_attendees
        kpi_achievement_pct = Decimal('0.00')
        if kpi_target > 0:
            kpi_achievement_pct = (Decimal(kpi_actual) / Decimal(kpi_target) * Decimal('100')).quantize(Decimal('0.01'))

        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='kpi_target',
            defaults={'metric_value': Decimal(kpi_target)},
        )
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='kpi_actual',
            defaults={'metric_value': Decimal(kpi_actual)},
        )
        CampaignKPIResult.objects.update_or_create(
            campaign=campaign,
            metric_code='kpi_achievement_pct',
            defaults={'metric_value': kpi_achievement_pct},
        )

        return total_attendees, cpa

    @staticmethod
    def calculate_platform_performance(campaign: Campaign):
        platform_metrics = {}
        active_platforms = set()
        for ad in campaign.social_ads.all():
            for platform_line in ad.platform_lines.all():
                platform = platform_line.platform
                if not platform:
                    continue
                active_platforms.add(platform)
                platform_leads = LeadCampaignAttribution.objects.filter(campaign=campaign, platform=platform).count()
                CampaignKPIResult.objects.update_or_create(
                    campaign=campaign,
                    metric_code=f'platform_{platform}_leads',
                    defaults={'metric_value': Decimal(platform_leads)},
                )
                platform_budget = platform_line.budget or Decimal('0.00')
                platform_cpl = Decimal('0.00')
                if platform_leads > 0:
                    platform_cpl = (Decimal(platform_budget) / Decimal(platform_leads)).quantize(Decimal('0.01'))
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign,
                        metric_code=f'platform_{platform}_cpl',
                        defaults={'metric_value': platform_cpl},
                    )
                else:
                    CampaignKPIResult.objects.filter(campaign=campaign, metric_code=f'platform_{platform}_cpl').delete()
                
                # Platform-level Event ROI (attributing platform budget vs event attendees referred by this platform)
                platform_attendees = EventAttendance.objects.filter(
                    company=campaign.company, event__campaign=campaign, platform=platform, attended=True
                ).count()
                platform_cpa = Decimal('0.00')
                if platform_attendees > 0:
                    platform_cpa = (Decimal(platform_budget) / Decimal(platform_attendees)).quantize(Decimal('0.01'))
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign,
                        metric_code=f'platform_{platform}_cpa',
                        defaults={'metric_value': platform_cpa},
                    )
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign,
                        metric_code=f'platform_{platform}_attendees',
                        defaults={'metric_value': Decimal(platform_attendees)},
                    )
                else:
                    CampaignKPIResult.objects.filter(campaign=campaign, metric_code__in=[f'platform_{platform}_cpa', f'platform_{platform}_attendees']).delete()

                achievement = None
                if platform_line.target_value:
                    achievement = (Decimal(platform_leads) / Decimal(platform_line.target_value) * Decimal('100')).quantize(Decimal('0.01'))
                    CampaignKPIResult.objects.update_or_create(
                        campaign=campaign,
                        metric_code=f'platform_{platform}_kpi_achievement_pct',
                        defaults={'metric_value': achievement},
                    )
                platform_metrics[platform] = {
                    'leads': platform_leads,
                    'attendees': platform_attendees,
                    'budget': platform_budget,
                    'cpl': platform_cpl,
                    'cpa': platform_cpa,
                    'target_value': platform_line.target_value,
                    'kpi_achievement_pct': achievement,
                }
        for kpi in CampaignKPIResult.objects.filter(campaign=campaign, metric_code__startswith='platform_'):
            if kpi.metric_code.endswith(('_leads', '_cpl', '_kpi_achievement_pct', '_cpa', '_attendees')):
                platform_name = kpi.metric_code[len('platform_'):]
                for suffix in ('_kpi_achievement_pct', '_leads', '_cpl', '_cpa', '_attendees'):
                    if platform_name.endswith(suffix):
                        platform_name = platform_name[:-len(suffix)]
                        break
                if platform_name not in active_platforms:
                    kpi.delete()
        return platform_metrics

    @staticmethod
    def calculate_source_performance(campaign: Campaign):
        metrics = {}
        rows = (
            LeadCampaignAttribution.objects
            .filter(campaign=campaign)
            .values_list('campaign_type', 'platform')
        )
        for campaign_type, platform in rows:
            key = campaign_type or platform or 'unspecified'
            metrics[key] = metrics.get(key, 0) + 1
        for key, count in metrics.items():
            CampaignKPIResult.objects.update_or_create(
                campaign=campaign,
                metric_code=f'source_{key}_leads',
                defaults={'metric_value': Decimal(count)},
            )
        return metrics

    @classmethod
    @transaction.atomic
    def recalculate_all_kpis(cls, campaign: Campaign):
        lead_count, cpl = cls.calculate_cpl(campaign)
        total_attendees, cpa = cls.calculate_event_roi(campaign)
        platform_metrics = cls.calculate_platform_performance(campaign)
        source_metrics = cls.calculate_source_performance(campaign)
        return {
            'total_cost': campaign.total_budget or Decimal('0.00'),
            'lead_count': lead_count,
            'cpl': cpl,
            'total_attendees': total_attendees,
            'cpa': cpa,
            'platform_metrics': platform_metrics,
            'source_metrics': source_metrics,
        }
