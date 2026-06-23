from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User, SalesProfile
from apps.leads.models import LeadSource, LeadStage
from apps.integrations.models import (
    CompanyIntegration, TenantWebhookEndpoint, ExternalFormMapping,
    IntegrationFieldMapping, IncomingWebhookPayload, IntegrationProvider
)
from apps.integrations.services.webhooks import IncomingWebhookService, hash_token

class MetaWebhookTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.provider, _ = IntegrationProvider.objects.get_or_create(code='meta_ads', name='Meta Ads')
        self.integration = CompanyIntegration.objects.create(company=self.company, provider=self.provider, status='active')
        
        self.endpoint = TenantWebhookEndpoint.objects.create(
            company=self.company,
            integration=self.integration,
            secret_token_hash=hash_token('super-secret')
        )
        
        self.source = LeadSource.objects.create(company=self.company, code='campaign', name='Campaign')
        self.stage = LeadStage.objects.create(company=self.company, code='fresh', name='Fresh')
        
        self.form_mapping = ExternalFormMapping.objects.create(
            endpoint=self.endpoint,
            external_form_id='meta-form-123',
            lead_source=self.source,
            default_origin='direct'
        )
        
        IntegrationFieldMapping.objects.create(form_mapping=self.form_mapping, external_field_name='full_name', crm_field_name='full_name')
        IntegrationFieldMapping.objects.create(form_mapping=self.form_mapping, external_field_name='phone', crm_field_name='phone_number')

        self.sales = User.objects.create(email='s1@test.com', company=self.company)
        self.sp = SalesProfile.objects.create(user=self.sales, company=self.company, is_available=True)

    def test_webhook_processing(self):
        payload = {
            'form_id': 'meta-form-123',
            'full_name': 'Meta User',
            'phone': '123456789'
        }
        
        received_payload = IncomingWebhookService.receive(
            endpoint_uuid=self.endpoint.endpoint_uuid,
            raw_payload=payload,
            token='super-secret'
        )
        
        self.assertEqual(received_payload.processing_status, 'processed')
        self.assertIsNotNone(received_payload.processed_lead)
        self.assertEqual(received_payload.processed_lead.full_name, 'Meta User')
