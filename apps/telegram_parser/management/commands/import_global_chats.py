# -*- coding: utf-8 -*-
import json
import os
from django.core.management.base import BaseCommand
from apps.telegram_parser.models import GlobalChat


class Command(BaseCommand):
    help = 'Импорт глобальных чатов из JSON файла в базу данных'

    def handle(self, *args, **options):
        # Путь к JSON файлу в корне проекта
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        json_file_path = os.path.join(base_dir, 'chats.json')
        
        # Проверяем существование файла
        if not os.path.exists(json_file_path):
            self.stdout.write(
                self.style.ERROR(f'❌ Файл {json_file_path} не найден!')
            )
            return
        
        # Загружаем данные - пробуем разные способы
        target_chats = None
        
        # Способ 1: Как JSON
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                target_chats = json.load(f)
            self.stdout.write(self.style.SUCCESS('✅ Прочитано как JSON'))
        except json.JSONDecodeError:
            pass
        
        # Способ 2: Как Python код (с eval)
        if target_chats is None:
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Если начинается с {, добавляем префикс
                    if content.strip().startswith('{'):
                        content = 'target_chats = ' + content
                    # Выполняем код
                    exec_globals = {}
                    exec(content, exec_globals)
                    target_chats = exec_globals.get('target_chats') or exec_globals.get('data')
                self.stdout.write(self.style.SUCCESS('✅ Прочитано как Python код'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Ошибка при чтении как Python: {e}'))
        
        if not target_chats:
            self.stdout.write(
                self.style.ERROR('❌ Не удалось прочитать файл ни одним способом!')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'📂 Загружено {len(target_chats)} чатов из JSON файла')
        )
        
        created_count = 0
        updated_count = 0
        created_chats = []

        for chat_id_str, chat_data in target_chats.items():
            # Конвертируем строковый ключ в int
            chat_id = int(chat_id_str)
            name = chat_data.get('name', f'Chat {chat_id}')
            invite_link = chat_data.get('invite_link')

            # Создаем или обновляем чат
            chat, created = GlobalChat.objects.update_or_create(
                chat_id=chat_id,
                defaults={
                    'name': name,
                    'invite_link': invite_link,
                    'is_active': True
                }
            )

            if created:
                created_count += 1
                created_chats.append(name)
            else:
                updated_count += 1

        # Выводим результаты
        self.stdout.write('\n' + '='*50)
        
        if created_chats:
            self.stdout.write(
                self.style.SUCCESS('\n✅ Создано чатов:')
            )
            for chat_name in created_chats[:10]:  # Показываем первые 10
                self.stdout.write(f'   ✅ {chat_name}')
            
            if len(created_chats) > 10:
                self.stdout.write(f'   ... и еще {len(created_chats) - 10} чатов')

        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Импорт завершен!')
        )
        self.stdout.write(f'   Создано: {created_count}')
        self.stdout.write(f'   Обновлено: {updated_count}')
        self.stdout.write(f'   Всего: {created_count + updated_count}\n')
