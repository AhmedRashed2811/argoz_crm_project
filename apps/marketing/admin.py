from django.contrib import admin
from django.apps import apps

app_config = apps.get_app_config(__name__.split('.')[-2])
for model in app_config.get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
