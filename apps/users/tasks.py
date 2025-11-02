import logging
from celery import shared_task
from .models import User

logger = logging.getLogger('users')


@shared_task
def reset_monthly_counters():
    """
    Сбрасывает месячные счетчики сообщений для всех пользователей
    Запускается 1го числа каждого месяца
    """
    try:
        users_count = User.objects.filter(is_active=True).count()
        User.objects.filter(is_active=True).update(messages_this_month=0)
        
        logger.info(f"Monthly counters reset for {users_count} users")
        return f"Reset monthly counters for {users_count} users"
        
    except Exception as exc:
        logger.error(f"Error resetting monthly counters: {exc}")
        raise exc
