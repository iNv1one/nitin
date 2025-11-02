"""
Management команда для импорта всех доступных Telegram чатов в базу данных
"""
import asyncio
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from telethon import TelegramClient
from apps.telegram_parser.models import GlobalChat, UserChatSettings
from asgiref.sync import sync_to_async

User = get_user_model()


class Command(BaseCommand):
    help = 'Импортирует все доступные Telegram чаты в базу данных'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID пользователя для создания настроек (по умолчанию первый суперпользователь)'
        )

    def handle(self, *args, **options):
        asyncio.run(self.async_handle(options))

    async def async_handle(self, options):
        # Получаем пользователя
        user_id = options.get('user_id')
        if user_id:
            user = await sync_to_async(User.objects.get)(id=user_id)
        else:
            user = await sync_to_async(User.objects.filter(is_superuser=True).first)()
            if not user:
                self.stdout.write(self.style.ERROR('❌ Суперпользователь не найден. Создайте суперпользователя или укажите --user-id'))
                return

        self.stdout.write(f'👤 Используем пользователя: {user.email}')

        # Читаем credentials из настроек Django
        from django.conf import settings
        api_id = settings.TELEGRAM_API_ID
        api_hash = settings.TELEGRAM_API_HASH

        # Подключаемся к Telegram
        client = TelegramClient('master_session', api_id, api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            self.stdout.write(self.style.ERROR('❌ Telegram клиент не авторизован!'))
            return

        self.stdout.write(self.style.SUCCESS('✅ Получаем список диалогов...'))

        dialogs = await client.get_dialogs()

        created_count = 0
        updated_count = 0
        settings_created = 0

        for dialog in dialogs:
            entity = dialog.entity

            # Только группы и каналы
            if not (hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup')):
                continue

            # Формируем ID в правильном формате
            chat_id = entity.id
            if hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup'):
                formatted_id = -1000000000000 - entity.id if entity.id > 0 else entity.id
            else:
                formatted_id = -entity.id if entity.id > 0 else entity.id

            title = getattr(entity, 'title', 'Unknown')
            username = getattr(entity, 'username', None)

            # Создаем или обновляем GlobalChat
            global_chat, created = await sync_to_async(GlobalChat.objects.update_or_create)(
                chat_id=formatted_id,
                defaults={
                    'name': title,
                    'invite_link': f'https://t.me/{username}' if username else None,
                    'is_active': True
                }
            )

            if created:
                created_count += 1
                self.stdout.write(f'  ✓ Создан: {title} (ID: {formatted_id})')
            else:
                updated_count += 1
                self.stdout.write(f'  ↻ Обновлен: {title} (ID: {formatted_id})')

            # Создаем настройки для пользователя (по умолчанию включены)
            user_setting, setting_created = await sync_to_async(UserChatSettings.objects.get_or_create)(
                user=user,
                global_chat=global_chat,
                defaults={'is_enabled': True}
            )

            if setting_created:
                settings_created += 1

        await client.disconnect()

        self.stdout.write(self.style.SUCCESS(f'\n📊 Статистика:'))
        self.stdout.write(f'  Создано чатов: {created_count}')
        self.stdout.write(f'  Обновлено чатов: {updated_count}')
        self.stdout.write(f'  Создано настроек: {settings_created}')
        self.stdout.write(self.style.SUCCESS(f'\n✅ Импорт завершен!'))
