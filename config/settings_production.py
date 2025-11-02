"""
Production settings для Telegram Parser SaaS
"""
from .settings import *

# Security
DEBUG = False
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS').split(',')

# HTTPS/Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Database - PostgreSQL для production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# Static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# Media files
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

# Celery - Redis для production
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')

# Email settings (опционально)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# Logging - более детальное логирование для production
LOGGING['handlers']['file']['filename'] = '/var/log/telegram-parser/django.log'
LOGGING['root']['level'] = 'WARNING'
LOGGING['loggers']['django']['level'] = 'WARNING'
LOGGING['loggers']['telegram_parser']['level'] = 'INFO'

# Celery Beat Schedule - периодические задачи
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Обновление статистики каждый час
    'update-bot-statistics': {
        'task': 'apps.telegram_parser.tasks.update_bot_statistics',
        'schedule': crontab(minute=0),  # Каждый час
    },
    # Проверка здоровья системы каждые 5 минут
    'health-check': {
        'task': 'apps.telegram_parser.tasks.health_check',
        'schedule': 300.0,  # 5 минут в секундах
    },
    # Очистка старых сообщений каждый день в 3:00
    'cleanup-old-messages': {
        'task': 'apps.telegram_parser.tasks.cleanup_old_messages',
        'schedule': crontab(hour=3, minute=0),
    },
    # Сброс дневного счетчика в полночь
    'reset-daily-counter': {
        'task': 'apps.telegram_parser.tasks.reset_daily_message_counter',
        'schedule': crontab(hour=0, minute=0),
    },
}

# Настройки Celery
CELERY_TIMEZONE = 'Europe/Moscow'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 минут максимум на задачу
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

