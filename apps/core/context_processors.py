def crm_context(request):
    user = getattr(request, 'user', None)
    return {
        'active_company': getattr(user, 'company', None) if getattr(user, 'is_authenticated', False) else None,
        'crm_product_name': 'Argoz CRM',
    }
