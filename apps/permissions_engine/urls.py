from django.urls import path
from . import views

app_name = 'permissions_engine'
urlpatterns = [
    path('matrix/', views.PermissionMatrixView.as_view(), name='matrix'),
    path('overrides/', views.UserOverrideListView.as_view(), name='overrides'),
]
