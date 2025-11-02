import os
from celery import Celery
from celery.signals import worker_ready

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('telegram_parser_saas')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@worker_ready.connect
def at_start(sender, **kwargs):
    """
    Запускаем polling для ботов пользователей при старте Celery worker
    """
    with sender.app.connection() as conn:
        from apps.telegram_parser.tasks import start_user_bots_polling
        start_user_bots_polling.apply_async(connection=conn)