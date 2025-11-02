import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('telegram_parser_saas')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    'reset-daily-message-counter': {
        'task': 'apps.telegram_parser.tasks.reset_daily_message_counter',
        'schedule': crontab(hour=0, minute=0),  # Каждый день в полночь
    },
    'reset-monthly-user-counters': {
        'task': 'apps.users.tasks.reset_monthly_counters',
        'schedule': crontab(hour=0, minute=0, day_of_month=1),  # 1го числа каждого месяца
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
