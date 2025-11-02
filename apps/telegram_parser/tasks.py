import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('telegram_parser')


@shared_task(bind=True, max_retries=3)
def process_message_task(self, message_data):
    """
    Celery task для обработки сообщений
    """
    try:
        # Ленивый импорт для избежания циклических зависимостей
        from .message_processor import message_processor
        
        logger.info(f"Processing message {message_data.get('message_id')} from chat {message_data.get('chat_id')}")
        
        # Обрабатываем сообщение
        success = message_processor.process_message(message_data)
        
        if success:
            logger.info(f"Successfully processed message {message_data.get('message_id')}")
            return f"Processed message {message_data.get('message_id')}"
        else:
            logger.error(f"Failed to process message {message_data.get('message_id')}")
            raise Exception("Message processing failed")
            
    except Exception as exc:
        logger.error(f"Error in process_message_task: {exc}")
        
        # Retry с exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            logger.info(f"Retrying message {message_data.get('message_id')} in {countdown} seconds")
            raise self.retry(exc=exc, countdown=countdown)
        else:
            logger.error(f"Max retries reached for message {message_data.get('message_id')}")
            raise exc


@shared_task
def start_telegram_parser():
    """
    Celery task для запуска Telegram парсера
    """
    try:
        # Ленивый импорт для избежания циклических зависимостей
        from .telegram_client import master_parser
        
        logger.info("Starting Telegram parser via Celery task")
        
        # Импортируем asyncio здесь, чтобы избежать проблем
        import asyncio
        
        # Запускаем парсер
        result = asyncio.run(master_parser.start_monitoring())
        
        if result:
            logger.info("Telegram parser started successfully")
            return "Telegram parser started"
        else:
            logger.error("Failed to start Telegram parser")
            return "Failed to start parser"
            
    except Exception as exc:
        logger.error(f"Error starting Telegram parser: {exc}")
        raise exc


@shared_task
def stop_telegram_parser():
    """
    Celery task для остановки Telegram парсера
    """
    try:
        # Ленивый импорт для избежания циклических зависимостей
        from .telegram_client import master_parser
        
        logger.info("Stopping Telegram parser via Celery task")
        
        import asyncio
        asyncio.run(master_parser.stop())
        
        logger.info("Telegram parser stopped successfully")
        return "Telegram parser stopped"
        
    except Exception as exc:
        logger.error(f"Error stopping Telegram parser: {exc}")
        raise exc


@shared_task
def reset_daily_message_counter():
    """
    Задача для сброса ежедневного счетчика сообщений (запускается в полночь)
    """
    try:
        from .models import BotStatus
        
        bot_status = BotStatus.objects.first()
        if bot_status:
            bot_status.messages_processed_today = 0
            bot_status.save(update_fields=['messages_processed_today'])
            
            logger.info("Daily message counter reset successfully")
            return "Daily counter reset"
        else:
            logger.warning("No bot status record found for daily reset")
            return "No bot status record"
            
    except Exception as exc:
        logger.error(f"Error resetting daily counter: {exc}")
        raise exc


@shared_task
def cleanup_old_messages():
    """
    Задача для очистки старых сообщений (запускается еженедельно)
    """
    try:
        from datetime import timedelta
        from .models import ProcessedMessage
        
        # Удаляем сообщения старше 30 дней
        cutoff_date = timezone.now() - timedelta(days=30)
        
        deleted_count, _ = ProcessedMessage.objects.filter(
            processed_at__lt=cutoff_date
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old messages")
        return f"Cleaned up {deleted_count} messages"
        
    except Exception as exc:
        logger.error(f"Error cleaning up old messages: {exc}")
        raise exc


@shared_task
def update_bot_statistics():
    """
    Задача для обновления статистики бота (запускается каждый час)
    """
    try:
        from .models import BotStatus, MonitoredChat
        from apps.users.models import User
        
        bot_status = BotStatus.objects.first()
        if not bot_status:
            logger.warning("No bot status record found")
            return "No bot status record"
        
        # Обновляем статистику
        total_chats = MonitoredChat.objects.filter(is_active=True).values('chat_id').distinct().count()
        total_users = User.objects.filter(is_active=True).count()
        
        bot_status.total_chats_monitored = total_chats
        bot_status.total_users = total_users
        bot_status.save(update_fields=['total_chats_monitored', 'total_users'])
        
        logger.info(f"Updated bot statistics: {total_chats} chats, {total_users} users")
        return f"Updated statistics: {total_chats} chats, {total_users} users"
        
    except Exception as exc:
        logger.error(f"Error updating bot statistics: {exc}")
        raise exc


@shared_task
def health_check():
    """
    Задача для проверки здоровья системы
    """
    try:
        from .models import BotStatus
        
        bot_status = BotStatus.objects.first()
        if not bot_status:
            return "No bot status record"
        
        if not bot_status.is_healthy:
            logger.warning("Bot health check failed - bot appears to be unhealthy")
            
            # Здесь можно добавить отправку уведомлений администратору
            # Или автоматический перезапуск бота
            
            return "Bot unhealthy"
        
        logger.info("Bot health check passed")
        return "Bot healthy"
        
    except Exception as exc:
        logger.error(f"Error in health check: {exc}")
        raise exc