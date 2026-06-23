from django.urls import path
from . import views

app_name = 'marketing'
urlpatterns = [
    path('', views.CampaignListView.as_view(), name='campaign_list'),
    path('create/', views.CampaignCreateView.as_view(), name='campaign_create'),
    path('<uuid:pk>/', views.CampaignDetailView.as_view(), name='campaign_detail'),
    path('<uuid:pk>/edit/', views.CampaignUpdateView.as_view(), name='campaign_edit'),
    path('<uuid:pk>/duplicate/', views.CampaignDuplicateView.as_view(), name='campaign_duplicate'),
    path('<uuid:pk>/archive/', views.CampaignArchiveView.as_view(), name='campaign_archive'),
    path('approval-queue/', views.ApprovalQueueView.as_view(), name='approval_queue'),
    path('roi/', views.ROIReportView.as_view(), name='roi_report'),
    path('ajax/budget-preview/', views.ajax_budget_preview, name='ajax_budget_preview'),
]
