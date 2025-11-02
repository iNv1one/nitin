"""
Обработчики для Telegram ботов пользователей
"""
import logging
from django.conf import settings
from .models import ProcessedMessage
from apps.users.models import User

logger = logging.getLogger('telegram_parser')


def handle_status_callback(call, bot, user):
    """Обработка нажатия на кнопку статуса"""
    try:
        # Парсим callback_data: status_{message_id}_{action}
        parts = call.data.split('_')
        if len(parts) != 3 or parts[0] != 'status':
            return
        
        message_id = int(parts[1])
        action = parts[2]
        
        # Получаем сообщение
        try:
            processed_msg = ProcessedMessage.objects.get(
                id=message_id,
                user=user
            )
        except ProcessedMessage.DoesNotExist:
            bot.answer_callback_query(call.id, "Сообщение не найдено")
            return
        
        # Обновляем статус
        updated = False
        
        if action in ['unqualified', 'qualified', 'spam']:
            # Эти статусы взаимоисключающие
            if processed_msg.quality_status == action:
                # Если уже выбрано - снимаем
                processed_msg.quality_status = 'none'
            else:
                processed_msg.quality_status = action
            updated = True
            
        elif action == 'dialog':
            # Переключаем флаг
            processed_msg.dialog_started = not processed_msg.dialog_started
            updated = True
            
        elif action == 'sale':
            # Переключаем флаг
            processed_msg.sale_made = not processed_msg.sale_made
            updated = True
        
        if updated:
            processed_msg.save()
            
            # Обновляем кнопки
            from .message_processor import message_processor
            new_keyboard = message_processor._create_status_keyboard(processed_msg)
            
            try:
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=new_keyboard
                )
                bot.answer_callback_query(call.id, "✅ Статус обновлен")
            except Exception as e:
                logger.error(f"Error updating keyboard: {e}")
                bot.answer_callback_query(call.id, "Статус обновлен")
        
    except Exception as e:
        logger.error(f"Error handling status callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обновления")


def setup_bot_handlers(bot, user):
    """Настройка обработчиков для бота пользователя"""
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('status_'))
    def callback_handler(call):
        handle_status_callback(call, bot, user)
    
    logger.info(f"Bot handlers set up for user {user.id}")
