from django.test import TestCase
from django.test import RequestFactory
from django.utils import timezone
from apps.companies.models import Company
from apps.leads.models import Lead, LeadSource, LeadStage
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.core.middleware import _thread_locals

class AuditEngineTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co', slug='test-co')
        self.source = LeadSource.objects.create(company=self.company, code='self_generated', name='Self Generated')
        self.stage = LeadStage.objects.create(company=self.company, code='fresh', name='Fresh')
        self.factory = RequestFactory()

    def test_audit_log_snapshots(self):
        lead = Lead.objects.create(company=self.company, full_name='L1', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        log = AuditService.log(
            company=self.company,
            action='lead.updated',
            obj=lead,
            before={'full_name': 'Old Name'},
            after={'full_name': 'L1'}
        )
        self.assertEqual(log.action, 'lead.updated')
        self.assertEqual(log.before['full_name'], 'Old Name')
        self.assertEqual(log.after['full_name'], 'L1')

    def test_request_metadata_enrichment(self):
        lead = Lead.objects.create(company=self.company, full_name='L1', phone_number='123456789', normalized_phone='123456789', source=self.source, current_stage=self.stage)
        
        request = self.factory.get('/leads/update/')
        import uuid
        request.correlation_id = uuid.uuid4()
        request.META['HTTP_USER_AGENT'] = 'Mozilla Test'
        request.META['REMOTE_ADDR'] = '192.168.1.1'
        
        _thread_locals.request = request
        try:
            log = AuditService.log(
                company=self.company,
                action='lead.updated',
                obj=lead
            )
            self.assertEqual(log.correlation_id, request.correlation_id)
            self.assertEqual(log.ip_address, '192.168.1.1')
            self.assertEqual(log.user_agent, 'Mozilla Test')
            self.assertEqual(log.request_path, '/leads/update/')
        finally:
            _thread_locals.request = None
