from django.urls import path
from . import views

app_name = 'accounts'
urlpatterns = [
    path('login/', views.CRMLoginView.as_view(), name='login'),
    path('logout/', views.CRMLogoutView.as_view(), name='logout'),
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<uuid:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<uuid:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    path('teams/', views.TeamListView.as_view(), name='team_list'),
    path('teams/create/', views.TeamCreateView.as_view(), name='team_create'),
    path('ajax/group-permissions/', views.ajax_group_permissions, name='ajax_group_permissions'),
]
