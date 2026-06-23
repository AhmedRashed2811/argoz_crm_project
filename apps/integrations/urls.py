from django.urls import path
from . import views

app_name = 'integrations'
urlpatterns = [
    path('', views.IntegrationListView.as_view(), name='list'),
    path('meta/setup/', views.MetaSetupView.as_view(), name='meta_setup'),
    path('webhook-logs/', views.WebhookLogListView.as_view(), name='webhook_logs'),
    path('webhooks/<uuid:endpoint_uuid>/', views.TenantWebhookView.as_view(), name='tenant_webhook'),
    path('webhooks/reprocess/<uuid:pk>/', views.WebhookReprocessView.as_view(), name='webhook_reprocess'),
    path('webhooks/rotate-secret/<uuid:pk>/', views.WebhookSecretRotateView.as_view(), name='webhook_secret_rotate'),
]
