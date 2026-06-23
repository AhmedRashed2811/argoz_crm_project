from django.urls import path
from . import views
app_name = 'notifications'
urlpatterns = [
    path('', views.NotificationListView.as_view(), name='list'),
    path('preferences/', views.NotificationPreferenceView.as_view(), name='preferences'),
    path('ajax/mark-read/', views.ajax_mark_read, name='ajax_mark_read'),
    path('ajax/dismiss-reminder/<uuid:pk>/', views.ajax_dismiss_reminder, name='ajax_dismiss_reminder'),
]
