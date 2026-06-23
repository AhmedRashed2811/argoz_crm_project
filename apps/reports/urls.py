from django.urls import path
from . import views

app_name = 'reports'
urlpatterns = [
    path('executive/', views.ExecutiveReportView.as_view(), name='executive'),
    path('sales/', views.SalesReportView.as_view(), name='sales'),
    path('marketing/', views.MarketingReportView.as_view(), name='marketing'),
    path('finance/', views.FinanceReportView.as_view(), name='finance'),
]
