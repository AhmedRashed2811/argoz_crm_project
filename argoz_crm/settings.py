from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-this-key-in-production')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'apps.core',
    'apps.companies',
    'apps.accounts',
    'apps.permissions_engine.apps.PermissionsEngineConfig',
    'apps.audit',
    'apps.notifications',
    'apps.leads',
    'apps.distribution',
    'apps.sla',
    'apps.marketing',
    'apps.integrations',
    'apps.reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.CurrentRequestMiddleware',
]

ROOT_URLCONF = 'argoz_crm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.crm_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'argoz_crm.wsgi.application'
ASGI_APPLICATION = 'argoz_crm.asgi.application'

# Keep the existing MySQL/MariaDB configuration by default.
# For local backend tests/CI, set DJANGO_DB_ENGINE=sqlite without changing code.
if os.environ.get('DJANGO_DB_ENGINE', '').lower() == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('SQLITE_NAME', str(BASE_DIR / 'db.sqlite3')),
        }
    }
elif os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(os.environ['DATABASE_URL'])}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('MYSQL_DATABASE', 'argoz_crm'),
            'USER': os.environ.get('MYSQL_USER', 'root'),
            'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
            'HOST': os.environ.get('MYSQL_HOST', '127.0.0.1'),
            'PORT': os.environ.get('MYSQL_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'Africa/Cairo')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/1')
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TRACK_STARTED = True
CELERY_BEAT_SCHEDULE = {
    'check_sla_expiry': {
        'task': 'apps.sla.tasks.check_sla_expiry',
        'schedule': 120.0,
    },
    'send_due_reminders': {
        'task': 'apps.notifications.tasks.send_due_reminders',
        'schedule': 300.0,
    },
    'send_email_outbox': {
        'task': 'apps.notifications.tasks.send_email_outbox',
        'schedule': 60.0,
    },
    'recalculate_campaign_metrics': {
        'task': 'apps.marketing.tasks.recalculate_campaign_metrics',
        'schedule': 3600.0,
    },
    'update-campaign-lifecycles-every-hour': {
        'task': 'apps.marketing.tasks.update_campaign_lifecycles_task',
        'schedule': 3600.0,
    },
    'retry_failed_webhooks': {
        'task': 'apps.integrations.tasks.retry_failed_webhooks',
        'schedule': 600.0,
    },
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/2')]},
    }
}

EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Argoz CRM <no-reply@argoz-crm.local>')

CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o]
