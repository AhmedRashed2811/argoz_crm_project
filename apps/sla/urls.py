from django.urls import path
from . import views

app_name = 'sla'
urlpatterns = [
    path('', views.SLADashboardView.as_view(), name='dashboard'),
    path('definitions/', views.SLADefinitionListView.as_view(), name='definitions'),
]
