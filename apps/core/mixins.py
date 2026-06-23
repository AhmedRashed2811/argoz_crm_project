class TenantScopedViewMixin:
    """Mixin to automatically filter queryset by logged-in user's company."""
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and not user.is_superuser:
            company = user.company
            if company:
                if hasattr(qs.model, 'company'):
                    qs = qs.filter(company=company)
                elif hasattr(qs.model, 'lead') and hasattr(qs.model.lead.field.related_model, 'company'):
                    qs = qs.filter(lead__company=company)
                elif qs.model.__name__ == 'Company':
                    qs = qs.filter(pk=company.pk)
            else:
                # If non-superuser user is not assigned a company, return empty queryset
                qs = qs.none()
        return qs
