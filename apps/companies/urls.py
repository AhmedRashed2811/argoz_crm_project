from django.urls import path
from . import views

app_name = 'companies'
urlpatterns = [
    path('', views.CompanyListView.as_view(), name='list'),
    path('create/', views.CompanyCreateView.as_view(), name='create'),
    path('<uuid:pk>/edit/', views.CompanyUpdateView.as_view(), name='edit'),
    path('branches/', views.BranchListView.as_view(), name='branches'),
    path('languages/', views.LanguageListView.as_view(), name='languages'),
    path('policies/', views.PolicyConsoleView.as_view(), name='policy_console'),
]
