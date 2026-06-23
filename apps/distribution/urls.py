from django.urls import path
from . import views

app_name = 'distribution'

urlpatterns = [
    path('manual/', views.ManualDistributionListView.as_view(), name='list'),
    path('manual/<uuid:pk>/', views.ManualDistributionDetailView.as_view(), name='detail'),
    path('manual/<uuid:pk>/assign/', views.ManualDistributionAssignView.as_view(), name='assign'),
    path('manual/<uuid:pk>/ignore/', views.ManualDistributionIgnoreView.as_view(), name='ignore'),
]
