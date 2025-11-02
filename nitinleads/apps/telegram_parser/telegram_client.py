import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import MonitoredChat, BotStatus
from .tasks import process_message_task

logger = logging.getLogger('telegram_parser')


class MasterTelegramParser:
    """Главный парсер сообщений из всех чатов"""
    
    def __init__(self):
        self.client = TelegramClient(
            'master_session',
            settings.TELEGRAM_API_ID,
            settings.TELEGRAM_API_HASH
        )
        self.is_running = False
        self.bot_status = None
        
    async def initialize(self):
        """Инициализация клиента и статуса"""
        try:
            await self.client.start()
            logger.info("✅ Telegram client started successfully")
            
            # Получаем или создаем статус бота
            self.bot_status, created = await self._get_or_create_bot_status()
            if created:
                logger.info("📊 Bot status record created")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram client: {e}")
            return False
    
    async def _get_or_create_bot_status(self):
        """Получить или создать запись статуса бота"""
        from django.db import connection
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def get_or_create_status():
            bot_status, created = BotStatus.objects.get_or_create(
                bot_username='master_parser',
                defaults={
                    'is_running': False,
                    'total_chats_monitored': 0,
                    'messages_processed_today': 0,
                    'messages_processed_total': 0,
                    'errors_count': 0,
                }
            )
            return bot_status, created
        
        return await get_or_create_status()
    
    async def start_monitoring(self):
        """Запуск мониторинга всех чатов"""
        if not await self.initialize():
            return False
        
        try:
            # Получаем все уникальные чаты для мониторинга
            self.monitored_chats = await self._get_all_monitored_chats()
            
            if not self.monitored_chats:
                logger.warning("⚠️ No chats to monitor")
                return False
            
            logger.info(f"📺 Starting monitoring for {len(self.monitored_chats)} chats")
            logger.info(f"📋 Monitored chat IDs: {self.monitored_chats}")
            
            # Получаем подробную информацию о каждом чате
            for chat_id in self.monitored_chats[:5]:  # Логируем первые 5 для примера
                try:
                    chat = await self.client.get_entity(chat_id)
                    chat_title = getattr(chat, 'title', 'Unknown')
                    logger.info(f"  ✓ Chat ID {chat_id}: {chat_title}")
                except Exception as e:
                    logger.warning(f"  ✗ Chat ID {chat_id}: Failed to get info - {e}")
            
            # Обновляем статус
            await self._update_bot_status(
                is_running=True,
                started_at=timezone.now(),
                total_chats_monitored=len(self.monitored_chats),
                total_users=await self._get_total_users_count()
            )
            
            # Настраиваем обработчик новых сообщений для ВСЕХ чатов
            @self.client.on(events.NewMessage())
            async def message_handler(event):
                logger.info(f"📨 Raw message received from chat {event.chat_id}")
                await self._handle_new_message(event)
            
            logger.info("🚀 Master parser started and listening for messages...")
            logger.info(f"🔊 Listening to chat IDs: {self.monitored_chats}")
            logger.info(f"✅ Message handler registered successfully")
            self.is_running = True
            
            # Запускаем heartbeat
            asyncio.create_task(self._heartbeat_loop())
            
            # Запускаем основной loop
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
            await self._update_bot_status(
                is_running=False,
                errors_count=self.bot_status.errors_count + 1,
                last_error=str(e),
                last_error_at=timezone.now()
            )
            return False
        finally:
            self.is_running = False
            await self._update_bot_status(is_running=False)
    
    async def _get_all_monitored_chats(self):
        """Получить все уникальные чаты для мониторинга из GlobalChat"""
        from asgiref.sync import sync_to_async
        from .models import GlobalChat
        
        @sync_to_async
        def get_chats():
            # Получаем все активные глобальные чаты
            # Будем мониторить все, а фильтрацию по пользователям делаем при обработке
            return list(
                GlobalChat.objects.filter(is_active=True)
                .values_list('chat_id', flat=True)
                .distinct()
            )
        
        return await get_chats()
    
    async def _get_total_users_count(self):
        """Получить общее количество активных пользователей"""
        from asgiref.sync import sync_to_async
        from apps.users.models import User
        
        @sync_to_async
        def get_count():
            return User.objects.filter(is_active=True).count()
        
        return await get_count()
    
    async def _handle_new_message(self, event):
        """Обработка нового сообщения"""
        try:
            # Проверяем, что сообщение из мониторимого чата
            if not hasattr(self, 'monitored_chats') or event.chat_id not in self.monitored_chats:
                logger.debug(f"⏩ Message from non-monitored chat {event.chat_id}, skipping")
                return
            
            message = event.message
            
            logger.info(f"🔔 NEW MESSAGE received! Chat ID: {event.chat_id}, Message ID: {message.id}")
            
            # Базовая информация о сообщении
            message_data = {
                'message_id': message.id,
                'chat_id': event.chat_id,
                'sender_id': message.sender_id,
                'text': message.text or '',
                'date': message.date.isoformat() if message.date else None,
                'is_channel_post': getattr(event.chat, 'broadcast', False),
            }
            
            # Получаем информацию об отправителе
            try:
                sender = await message.get_sender()
                if sender:
                    message_data.update({
                        'sender_name': getattr(sender, 'first_name', '') or getattr(sender, 'title', ''),
                        'sender_last_name': getattr(sender, 'last_name', ''),
                        'sender_username': getattr(sender, 'username', ''),
                    })
                    logger.info(f"  👤 Sender: {message_data.get('sender_name')} (@{message_data.get('sender_username')})")
            except Exception as e:
                logger.warning(f"Failed to get sender info for message {message.id}: {e}")
            
            # Информация о чате
            try:
                chat = await event.get_chat()
                if chat:
                    message_data.update({
                        'chat_title': getattr(chat, 'title', ''),
                        'chat_username': getattr(chat, 'username', ''),
                    })
                    logger.info(f"  💬 Chat: {message_data.get('chat_title')} (ID: {event.chat_id})")
            except Exception as e:
                logger.warning(f"Failed to get chat info for message {message.id}: {e}")
            
            logger.info(f"  📝 Text preview: {(message.text or '')[:100]}")
            
            # Сохраняем сырое сообщение в БД для отладки
            await self._save_raw_message(message_data)
            
            # Отправляем в Celery для обработки
            process_message_task.delay(message_data)
            
            # Обновляем статистику
            await self._increment_message_counter()
            
            logger.info(f"✅ Message {message.id} from chat {event.chat_id} processed and saved")
            
        except Exception as e:
            logger.error(f"❌ Error handling message {getattr(event.message, 'id', 'unknown')}: {e}")
            await self._increment_error_counter(str(e))
    
    async def _save_raw_message(self, message_data):
        """Сохранить сырое сообщение в БД"""
        try:
            from asgiref.sync import sync_to_async
            from .models import RawMessage
            from datetime import datetime
            
            @sync_to_async
            def save_message():
                # Парсим дату
                if message_data.get('date'):
                    try:
                        message_date = datetime.fromisoformat(message_data['date'].replace('Z', '+00:00'))
                    except:
                        message_date = timezone.now()
                else:
                    message_date = timezone.now()
                
                RawMessage.objects.create(
                    message_id=message_data['message_id'],
                    chat_id=message_data['chat_id'],
                    chat_name=message_data.get('chat_title', ''),
                    sender_id=message_data.get('sender_id'),
                    sender_name=message_data.get('sender_name', ''),
                    sender_username=message_data.get('sender_username', ''),
                    message_text=message_data.get('text', ''),
                    message_date=message_date,
                    is_channel_post=message_data.get('is_channel_post', False),
                )
            
            await save_message()
            logger.debug(f"Saved raw message {message_data['message_id']}")
        except Exception as e:
            logger.error(f"Failed to save raw message: {e}")
    
    async def _update_bot_status(self, **fields):
        """Обновить статус бота"""
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def update_status():
            if self.bot_status:
                for field, value in fields.items():
                    setattr(self.bot_status, field, value)
                self.bot_status.save()
        
        await update_status()
    
    async def _increment_message_counter(self):
        """Увеличить счетчик обработанных сообщений"""
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def increment():
            if self.bot_status:
                self.bot_status.messages_processed_today += 1
                self.bot_status.messages_processed_total += 1
                self.bot_status.save(update_fields=['messages_processed_today', 'messages_processed_total'])
        
        await increment()
    
    async def _increment_error_counter(self, error_text):
        """Увеличить счетчик ошибок"""
        await self._update_bot_status(
            errors_count=self.bot_status.errors_count + 1,
            last_error=error_text[:1000],  # Ограничиваем длину
            last_error_at=timezone.now()
        )
    
    async def _heartbeat_loop(self):
        """Цикл heartbeat для обновления статуса"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                await self._update_bot_status(last_heartbeat=timezone.now())
                logger.debug("💓 Heartbeat updated")
            except Exception as e:
                logger.error(f"❌ Heartbeat error: {e}")
    
    async def stop(self):
        """Остановка парсера"""
        logger.info("🛑 Stopping master parser...")
        self.is_running = False
        
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        
        await self._update_bot_status(is_running=False)
        logger.info("✅ Master parser stopped")


# Глобальный экземпляр парсера
master_parser = MasterTelegramParser()