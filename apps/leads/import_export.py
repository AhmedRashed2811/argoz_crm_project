import csv
import io
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.permissions_engine.mixins import CRMPermissionRequiredMixin
from django.http import HttpResponse
from django.views.generic import FormView, View
from django.urls import reverse_lazy
from django.contrib import messages
from apps.leads.models import Lead, LeadSource, LeadStage
from apps.leads.services.leads import LeadService
from apps.audit.services.audit import AuditService


class LeadImportView(LoginRequiredMixin, CRMPermissionRequiredMixin, FormView):
    """Import leads from a CSV file."""
    template_name = 'leads/lead_import.html'
    permission_required = 'leads.create_lead'
    success_url = reverse_lazy('leads:list')

    def get_form_class(self):
        from django import forms

        class ImportForm(forms.Form):
            file = forms.FileField(label='CSV File', help_text='Required columns: full_name, phone_country_code, phone_number, source_code')
        return ImportForm

    def form_valid(self, form):
        file = form.cleaned_data['file']
        company = self.request.user.company
        if not company:
            messages.error(self.request, 'Cannot import without an active company.')
            return self.form_invalid(form)

        decoded = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        imported = 0
        duplicates = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            try:
                full_name = row.get('full_name', '').strip()
                phone_country_code = row.get('phone_country_code', '+20').strip()
                phone_number = row.get('phone_number', '').strip()
                source_code = row.get('source_code', '').strip()
                email = row.get('email', '').strip()
                origin = row.get('origin', 'direct').strip()

                if not full_name or not phone_number:
                    errors.append(f'Row {i}: Missing full_name or phone_number.')
                    continue

                source = LeadSource.objects.filter(company=company, code=source_code).first()
                if not source:
                    source = LeadSource.objects.filter(company=company).first()
                if not source:
                    errors.append(f'Row {i}: No lead source found for "{source_code}".')
                    continue

                stage = LeadStage.objects.filter(company=company, code='fresh').first()

                lead, created = LeadService.create_lead(
                    company=company,
                    full_name=full_name,
                    phone_country_code=phone_country_code,
                    phone_number=phone_number,
                    email=email,
                    source=source,
                    origin=origin,
                    current_stage=stage,
                    actor=self.request.user,
                )
                if created:
                    imported += 1
                else:
                    duplicates += 1
            except Exception as exc:
                errors.append(f'Row {i}: {str(exc)}')

        AuditService.log(
            company=company, actor=self.request.user, action='lead.import',
            metadata={'imported': imported, 'duplicates': duplicates, 'errors_count': len(errors)},
        )
        messages.success(self.request, f'Import complete: {imported} imported, {duplicates} duplicates, {len(errors)} errors.')
        if errors:
            messages.warning(self.request, 'Import errors: ' + '; '.join(errors[:10]))
        return super().form_valid(form)


class LeadExportView(LoginRequiredMixin, CRMPermissionRequiredMixin, View):
    """Export leads as CSV."""
    permission_required = 'leads.view_lead'

    def get(self, request):
        company = request.user.company
        lead_qs = Lead.objects.filter(company=company) if company else Lead.objects.all()
        lead_qs = lead_qs.select_related('source', 'current_stage', 'current_salesman')

        # Apply filters from querystring
        status = request.GET.get('status')
        if status:
            lead_qs = lead_qs.filter(status=status)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads_export.csv"'

        writer = csv.writer(response)
        writer.writerow(['Full Name', 'Phone', 'Email', 'Source', 'Origin', 'Stage', 'Status', 'Salesman', 'Created At'])
        for lead in lead_qs.iterator():
            writer.writerow([
                lead.full_name,
                f'{lead.phone_country_code}{lead.phone_number}',
                lead.email,
                lead.source.name if lead.source else '',
                lead.origin,
                lead.current_stage.name if lead.current_stage else '',
                lead.status,
                lead.current_salesman.email if lead.current_salesman else '',
                lead.created_at.isoformat(),
            ])

        AuditService.log(
            company=company, actor=request.user, action='lead.export',
            metadata={'count': lead_qs.count()},
        )
        return response
