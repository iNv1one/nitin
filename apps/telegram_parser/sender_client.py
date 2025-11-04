"""
Telethon клиент для отправки сообщений от имени пользовательского аккаунта
"""
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from django.conf import settings

logger = logging.getLogger(__name__)


class SenderClient:
    """Класс для работы с sender-аккаунтом"""
    
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        """
        Инициализация клиента для отправки сообщений
        
        Args:
            api_id: API ID аккаунта
            api_hash: API Hash аккаунта
            session_string: Строка сессии
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.client = None
    
    async def connect(self):
        """Подключение к Telegram"""
        try:
            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash
            )
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error("Sender account is not authorized")
                return False
            
            logger.info("Sender client connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting sender client: {e}")
            return False
    
    async def disconnect(self):
        """Отключение от Telegram"""
        if self.client:
            await self.client.disconnect()
            logger.info("Sender client disconnected")
    
    async def send_message(self, user_id: int, message_text: str) -> bool:
        """
        Отправка сообщения пользователю
        
        Args:
            user_id: ID пользователя в Telegram
            message_text: Текст сообщения
            
        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            if not self.client:
                logger.error("Client not connected")
                return False
            
            # Пробуем разные способы получить entity
            try:
                # Способ 1: Получаем entity напрямую по ID
                from telethon.tl.types import PeerUser
                entity = PeerUser(user_id)
                
                # Отправляем сообщение
                await self.client.send_message(entity, message_text)
                logger.info(f"Message sent successfully to user {user_id}")
                return True
                
            except Exception as e1:
                logger.warning(f"Failed to send via PeerUser, trying get_entity: {e1}")
                
                # Способ 2: Пытаемся получить через get_entity
                try:
                    entity = await self.client.get_entity(user_id)
                    await self.client.send_message(entity, message_text)
                    logger.info(f"Message sent successfully to user {user_id} via get_entity")
                    return True
                except Exception as e2:
                    logger.error(f"Failed to get entity for {user_id}: {e2}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending message to {user_id}: {e}")
            return False
    
    async def send_message_by_username(self, username: str, message_text: str) -> bool:
        """
        Отправка сообщения пользователю по username
        
        Args:
            username: Username пользователя (с @ или без)
            message_text: Текст сообщения
            
        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            if not self.client:
                logger.error("Client not connected")
                return False
            
            # Убираем @ если есть
            username = username.lstrip('@')
            
            # Отправляем сообщение
            await self.client.send_message(username, message_text)
            
            logger.info(f"Message sent successfully to @{username}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to @{username}: {e}")
            return False
    
    async def get_me(self):
        """Получение информации о текущем аккаунте"""
        try:
            if not self.client:
                return None
            return await self.client.get_me()
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None


async def create_session_string(api_id: int, api_hash: str, phone: str) -> str:
    """
    Создание строки сессии для нового аккаунта
    
    Args:
        api_id: API ID
        api_hash: API Hash
        phone: Номер телефона
        
    Returns:
        str: Строка сессии
    """
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            # Пользователь должен будет ввести код
            # Это нужно делать через отдельный интерфейс
        
        session_string = client.session.save()
        return session_string
        
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return ""
    finally:
        await client.disconnect()
