from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.core.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', DashboardView.as_view(), name='dashboard'),
    path('accounts/', include('apps.accounts.urls')),
    path('companies/', include('apps.companies.urls')),
    path('permissions/', include('apps.permissions_engine.urls')),
    path('leads/', include('apps.leads.urls')),
    path('marketing/', include('apps.marketing.urls')),
    path('integrations/', include('apps.integrations.urls')),
    path('audit/', include('apps.audit.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reports/', include('apps.reports.urls')),
    path('sla/', include('apps.sla.urls')),
    path('distribution/', include('apps.distribution.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
