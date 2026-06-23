from apps.sla.models import LeadSLAInstance, SLADefinition

def get_sla_instances(company):
    """Retrieves all LeadSLAInstances scoped to a company."""
    qs = LeadSLAInstance.objects.select_related('lead', 'stage', 'assignment')
    if company:
        qs = qs.filter(lead__company=company)
    return qs

def get_sla_definitions(company):
    """Retrieves all SLADefinitions scoped to a company."""
    qs = SLADefinition.objects.select_related('source', 'stage')
    if company:
        qs = qs.filter(company=company)
    return qs

def resolve_sla_definition(lead):
    """Resolves the best matching SLADefinition for a lead."""
    qs = SLADefinition.objects.filter(company=lead.company, is_active=True)
    candidates = qs.filter(source=lead.source, stage=lead.current_stage, origin=lead.origin)
    definition = (
        candidates.first()
        or qs.filter(stage=lead.current_stage, origin='').first()
        or qs.filter(stage=lead.current_stage).first()
        or qs.first()
    )
    return definition

def get_expired_sla_instance_ids(limit, now):
    """Retrieves active SLA instance IDs that are expired."""
    return list(
        LeadSLAInstance.objects.filter(status='active', due_at__lte=now)
        .order_by('due_at').values_list('id', flat=True)[:limit]
    )

def get_sla_instance_for_update(sla_id):
    """Retrieves single SLA instance with lock for processing."""
    return (
        LeadSLAInstance.objects
        .select_for_update()
        .select_related('lead', 'lead__company', 'lead__current_stage', 'lead__source')
        .get(id=sla_id)
    )

def get_sla_compliance_rate(company):
    """Calculates compliance rate percentage of satisfied SLAs."""
    sla_qs = get_sla_instances(company)
    total_resolved = sla_qs.filter(status__in=['satisfied', 'expired', 'processed']).count()
    satisfied = sla_qs.filter(status='satisfied').count()
    return round(satisfied / total_resolved * 100, 1) if total_resolved else 0

