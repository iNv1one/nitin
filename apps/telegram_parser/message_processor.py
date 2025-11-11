import logging
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import GlobalChat, UserChatSettings, KeywordGroup, ProcessedMessage
import telebot
import re

logger = logging.getLogger('telegram_parser')


class MessageProcessor:
    """Процессор сообщений для всех пользователей"""
    
    def __init__(self):
        self.user_bots = {}  # Кэш пользовательских ботов
    
    def process_message(self, message_data: Dict[str, Any]) -> bool:
        """Главная функция обработки сообщения"""
        try:
            chat_id = message_data['chat_id']
            message_text = message_data.get('text', '')
            
            if not message_text.strip():
                logger.debug(f"Skipping empty message {message_data.get('message_id')}")
                return True
            
            # Находим всех пользователей, которые мониторят этот чат
            interested_users = self._find_interested_users(chat_id)
            
            if not interested_users:
                logger.debug(f"No users monitoring chat {chat_id}")
                return True
            
            logger.info(f"Processing message {message_data.get('message_id')} for {len(interested_users)} users")
            
            # Обрабатываем для каждого пользователя
            for user_data in interested_users:
                self._process_for_user(user_data, message_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing message {message_data.get('message_id')}: {e}")
            return False
    
    def _find_interested_users(self, chat_id: int) -> List[Dict]:
        """Находим пользователей, которые мониторят данный чат через UserChatSettings"""
        try:
            # Находим глобальный чат
            try:
                global_chat = GlobalChat.objects.get(chat_id=chat_id, is_active=True)
            except GlobalChat.DoesNotExist:
                logger.debug(f"Chat {chat_id} not found in GlobalChat")
                return []
            
            # Находим пользователей с включенным мониторингом этого чата
            user_settings = UserChatSettings.objects.filter(
                global_chat=global_chat,
                is_enabled=True,
                user__is_active=True
            ).select_related('user', 'global_chat').values(
                'user__id',
                'user__username',
                'user__telegram_bot_token',
                'user__notification_chat_id',
                'global_chat__id',
                'global_chat__name'
            )
            
            return list(user_settings)
            
        except Exception as e:
            logger.error(f"Error finding interested users for chat {chat_id}: {e}")
            return []
    
    def _process_for_user(self, user_data: Dict, message_data: Dict[str, Any]):
        """Обрабатываем сообщение для конкретного пользователя"""
        try:
            user_id = user_data['user__id']
            message_text = message_data.get('text', '')
            
            # Получаем активные группы ключевых слов пользователя
            keyword_groups = KeywordGroup.objects.filter(
                user_id=user_id,
                is_active=True
            )
            
            for group in keyword_groups:
                matched_keywords = self._check_keywords(message_text, group.keywords)
                
                if matched_keywords:
                    logger.info(f"Found keywords {matched_keywords} for user {user_id} in group {group.name}")
                    
                    # Проверяем AI фильтр если включен
                    ai_approved = True
                    ai_result = ""
                    
                    if group.use_ai_filter and group.ai_prompt:
                        logger.info(f"🤖 AI проверка включена для группы '{group.name}' (user {user_id})")
                        ai_approved, ai_result = self._check_ai_filter(message_text, group.ai_prompt)
                        logger.info(f"🤖 AI ответ: '{ai_result}' | Одобрено: {ai_approved}")
                        
                        if not ai_approved:
                            logger.info(f"❌ Сообщение отклонено AI фильтром для user {user_id}")
                    
                    if ai_approved:
                        logger.info(f"✅ Сообщение прошло все проверки для user {user_id}")
                        # Сохраняем в БД
                        processed_msg = self._save_processed_message(
                            user_data, group, message_data, matched_keywords, ai_result
                        )
                        
                        # Отправляем уведомление
                        if processed_msg:
                            logger.info(f"📨 Отправка уведомления в Telegram для user {user_id}")
                            self._send_notification(user_data, processed_msg)
                            logger.info(f"✅ Уведомление отправлено для сообщения {processed_msg.id}")
                
        except Exception as e:
            logger.error(f"Error processing message for user {user_data.get('user__id')}: {e}")
    
    def _check_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """Проверяем наличие ключевых слов в тексте"""
        if not text or not keywords:
            return []
        
        text_lower = text.lower()
        matched = []
        
        for keyword in keywords:
            if not keyword:
                continue
                
            keyword_lower = keyword.lower().strip()
            
            # Простая проверка на вхождение
            if keyword_lower in text_lower:
                matched.append(keyword)
            
            # Можно добавить более сложную логику:
            # - регулярные выражения
            # - проверка по словам (word boundaries)
            # - морфологический анализ
        
        return matched
    
    def _check_ai_filter(self, text: str, prompt: str) -> tuple[bool, str]:
        """Проверяем сообщение через AI (Grok)"""
        try:
            from openai import OpenAI
            from django.conf import settings
            
            logger.info(f"🤖 AI проверка сообщения: '{text[:100]}...'")
            
            # Создаем клиент для Grok API
            client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL
            )
            
            # Формируем системный промт
            system_prompt = f"""
{prompt}

ВАЖНО: Ты должен ответить ТОЛЬКО словом "YES" или "NO".
- YES - если сообщение соответствует критериям
- NO - если сообщение НЕ соответствует критериям

Не добавляй никаких пояснений, только YES или NO.
"""
            
            logger.info(f"🤖 AI промт: '{prompt[:100]}...'")
            
            # Отправляем запрос к Grok
            response = client.chat.completions.create(
                model="grok-3-mini",  # Grok модель
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Проверь это сообщение:\n\n{text}"}
                ],
                max_tokens=10,
                temperature=0.3
            )
            
            # Получаем результат
            result = response.choices[0].message.content.strip().upper()
            logger.info(f"🤖 AI ответил: '{result}'")
            
            # Проверяем ответ
            is_approved = result in ['YES', 'Y', '1', 'TRUE', 'ДА']
            
            logger.info(f"🤖 Решение: {'ОДОБРЕНО ✅' if is_approved else 'ОТКЛОНЕНО ❌'}")
            
            return is_approved, result
            
        except Exception as e:
            logger.error(f"❌ AI filter error: {e}")
            # При ошибке AI пропускаем сообщение (не блокируем)
            return True, f"AI filter error: {str(e)}"
    
    def _save_processed_message(
        self, 
        user_data: Dict, 
        keyword_group: KeywordGroup, 
        message_data: Dict[str, Any], 
        matched_keywords: List[str],
        ai_result: str
    ) -> Optional[ProcessedMessage]:
        """Сохраняем обработанное сообщение в БД"""
        try:
            with transaction.atomic():
                # Получаем GlobalChat
                global_chat = GlobalChat.objects.get(id=user_data['global_chat__id'])
                
                # Формируем ссылку на сообщение
                message_link = ""
                chat_id = message_data['chat_id']
                message_id = message_data['message_id']
                
                if str(chat_id).startswith('-100'):
                    # Публичный канал или супергруппа
                    chat_id_clean = str(chat_id)[4:]  # Убираем -100
                    message_link = f"https://t.me/c/{chat_id_clean}/{message_id}"
                
                # Используем get_or_create чтобы избежать дубликатов
                # unique_together = ['user', 'message_id', 'chat_id']
                processed_msg, created = ProcessedMessage.objects.get_or_create(
                    user_id=user_data['user__id'],
                    message_id=message_id,
                    chat_id=chat_id,
                    defaults={
                        'keyword_group': keyword_group,
                        'global_chat': global_chat,
                        'monitored_chat_id': None,  # Устаревшее поле, оставляем None
                        'sender_id': message_data.get('sender_id'),
                        'sender_name': self._format_sender_name(message_data),
                        'sender_username': message_data.get('sender_username', ''),
                        'message_text': message_data.get('text', ''),
                        'message_link': message_link,
                        'matched_keywords': matched_keywords,
                        'ai_result': ai_result,
                        'notification_sent': False
                    }
                )
                
                # Если запись уже существовала, обновляем matched_keywords
                if not created:
                    # Добавляем новые ключевые слова к существующим
                    existing_keywords = set(processed_msg.matched_keywords or [])
                    new_keywords = set(matched_keywords)
                    all_keywords = list(existing_keywords | new_keywords)
                    
                    if all_keywords != processed_msg.matched_keywords:
                        processed_msg.matched_keywords = all_keywords
                        processed_msg.save(update_fields=['matched_keywords'])
                        logger.info(f"Updated keywords for existing message {message_id}")
                
                logger.info(f"{'Created' if created else 'Found existing'} processed message {message_id} for user {user_data['user__id']}")
                return processed_msg
                
        except Exception as e:
            logger.error(f"Error saving processed message: {e}")
            return None
    
    def _format_sender_name(self, message_data: Dict[str, Any]) -> str:
        """Форматируем имя отправителя"""
        first_name = message_data.get('sender_name', '')
        last_name = message_data.get('sender_last_name', '')
        
        if first_name and last_name:
            return f"{first_name} {last_name}".strip()
        elif first_name:
            return first_name
        else:
            return f"User {message_data.get('sender_id', 'Unknown')}"
    
    def _send_notification(self, user_data: Dict, processed_msg: ProcessedMessage):
        """Отправляем уведомление пользователю"""
        try:
            bot_token = user_data.get('user__telegram_bot_token')
            chat_id = user_data.get('user__notification_chat_id')
            
            if not bot_token or not chat_id:
                logger.warning(f"No bot token or chat ID for user {user_data['user__id']}")
                return False
            
            # Получаем или создаем бот для пользователя
            bot = self._get_user_bot(user_data['user__id'], bot_token)
            
            if not bot:
                logger.error(f"Failed to create bot for user {user_data['user__id']}")
                return False
            
            # Форматируем сообщение
            notification_text = self._format_notification(processed_msg, user_data)
            
            # Создаем inline клавиатуру с кнопками статусов
            keyboard = self._create_status_keyboard(processed_msg)
            
            # Отправляем уведомление
            try:
                sent_message = bot.send_message(
                    chat_id=chat_id,
                    text=notification_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=keyboard
                )
                
                # Сохраняем ID сообщения для последующего редактирования кнопок
                processed_msg.notification_sent = True
                processed_msg.telegram_message_id = sent_message.message_id
                processed_msg.save(update_fields=['notification_sent', 'telegram_message_id'])
                
                logger.info(f"Notification sent to user {user_data['user__id']} for message {processed_msg.message_id}")
                return True
                
            except Exception as send_error:
                logger.error(f"Failed to send notification to user {user_data['user__id']}: {send_error}")
                return False
                
        except Exception as e:
            logger.error(f"Error in send_notification: {e}")
            return False
    
    def _create_status_keyboard(self, processed_msg: ProcessedMessage):
        """Создаем inline клавиатуру со статусами"""
        from telebot import types
        
        markup = types.InlineKeyboardMarkup(row_width=3)
        
        # Первая строка: Неквал, Квал, Спам
        buttons_row1 = []
        
        # Неквал
        unq_text = "✅ Неквал" if processed_msg.quality_status == 'unqualified' else "Неквал"
        buttons_row1.append(types.InlineKeyboardButton(
            unq_text, 
            callback_data=f"status_{processed_msg.id}_unqualified"
        ))
        
        # Квал
        qual_text = "✅ Квал" if processed_msg.quality_status == 'qualified' else "Квал"
        buttons_row1.append(types.InlineKeyboardButton(
            qual_text,
            callback_data=f"status_{processed_msg.id}_qualified"
        ))
        
        # Спам
        spam_text = "✅ Спам" if processed_msg.quality_status == 'spam' else "Спам"
        buttons_row1.append(types.InlineKeyboardButton(
            spam_text,
            callback_data=f"status_{processed_msg.id}_spam"
        ))
        
        markup.row(*buttons_row1)
        
        # Вторая строка: Начали диалог, Есть продажа
        buttons_row2 = []
        
        # Начали диалог
        dialog_text = "✅ Начали диалог" if processed_msg.dialog_started else "Начали диалог"
        buttons_row2.append(types.InlineKeyboardButton(
            dialog_text,
            callback_data=f"status_{processed_msg.id}_dialog"
        ))
        
        # Есть продажа
        sale_text = "✅ Есть продажа" if processed_msg.sale_made else "Есть продажа"
        buttons_row2.append(types.InlineKeyboardButton(
            sale_text,
            callback_data=f"status_{processed_msg.id}_sale"
        ))
        
        markup.row(*buttons_row2)
        
        return markup
    
    def _get_user_bot(self, user_id: int, bot_token: str):
        """Получаем бот для пользователя (с кэшированием)"""
        try:
            if user_id not in self.user_bots:
                self.user_bots[user_id] = telebot.TeleBot(bot_token)
            
            return self.user_bots[user_id]
            
        except Exception as e:
            logger.error(f"Error creating bot for user {user_id}: {e}")
            return None
    
    def _format_notification(self, processed_msg: ProcessedMessage, user_data: Dict) -> str:
        """Форматируем текст уведомления"""
        try:
            # Безопасное экранирование HTML
            def escape_html(text):
                if not text:
                    return ""
                return (str(text)
                       .replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace('"', "&quot;")
                       .replace("'", "&#x27;"))
            
            sender_name = escape_html(processed_msg.sender_name)
            sender_username = escape_html(processed_msg.sender_username)
            message_text = escape_html(processed_msg.message_text)
            keywords = escape_html(", ".join(processed_msg.matched_keywords))
            
            # Получаем название чата из GlobalChat
            if processed_msg.global_chat:
                chat_name = escape_html(processed_msg.global_chat.name)
                chat_link = processed_msg.global_chat.invite_link
                
                # Форматируем канал с учетом ссылки
                if chat_link:
                    channel_info = f'<a href="{chat_link}">{chat_name}</a>'
                else:
                    channel_info = f'{chat_name} (Приватный)'
            else:
                channel_info = 'Unknown Chat'
            
            # Ограничиваем длину текста сообщения
            if len(message_text) > 300:
                message_text = message_text[:300] + "..."
            
            notification = f"""🎯 <b>Новый потенциальный клиент!</b>

👤 <b>Отправитель:</b> {sender_name}"""
            
            if sender_username:
                notification += f"\n🔍 <b>Username:</b> @{sender_username}"
            
            notification += f"""
📢 <b>Канал:</b> {channel_info}
🔗 <b>Ссылка на сообщение:</b> {processed_msg.message_link or 'Недоступна'}
🎯 <b>Ключевые слова:</b> {keywords}

💬 <b>Сообщение:</b>
{message_text}"""
            
            # Добавляем информацию об AI проверке если была
            if processed_msg.ai_result:
                notification += f"\n\n🤖 <b>AI проверка:</b> {escape_html(processed_msg.ai_result)}"
            
            return notification
            
        except Exception as e:
            logger.error(f"Error formatting notification: {e}")
            return f"Новое сообщение от {processed_msg.sender_name}: {processed_msg.message_text[:100]}..."


# Глобальный экземпляр процессора
message_processor = MessageProcessor()