from django.urls import path
from . import views
from .import_export import LeadImportView, LeadExportView

app_name = 'leads'
urlpatterns = [
    path('', views.LeadListView.as_view(), name='list'),
    path('create/', views.LeadCreateView.as_view(), name='create'),
    path('import/', LeadImportView.as_view(), name='import'),
    path('export/', LeadExportView.as_view(), name='export'),
    path('<uuid:pk>/', views.LeadDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', views.LeadUpdateView.as_view(), name='edit'),
    path('ajax/source-rules/', views.ajax_source_rules, name='ajax_source_rules'),
    path('ajax/campaign-children/', views.ajax_campaign_children, name='ajax_campaign_children'),
    path('ajax/eligible-sales/', views.ajax_eligible_sales, name='ajax_eligible_sales'),
]

