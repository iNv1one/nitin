# -*- coding: utf-8 -*-
"""
Скрипт для исправления JSON и импорта чатов
"""
import json
import os
import re
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.telegram_parser.models import GlobalChat

def fix_and_import():
    # Читаем файл
    with open('chats.json', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправляем проблемные символы
    lines = content.split('\n')
    fixed_lines = []
    
    for line in lines:
        if '"name":' in line or '"invite_link":' in line:
            # Находим содержимое строки
            if '"name"' in line:
                match = re.search(r'"name":\s*"(.+?)"(?=,|\s*})', line)
                if match:
                    name_content = match.group(1)
                    # Экранируем все кавычки внутри
                    name_fixed = name_content.replace('"', '\\"').replace('\\', '\\\\')
                    # Убираем двойное экранирование если оно уже было
                    name_fixed = name_fixed.replace('\\\\\\\\', '\\\\')
                    line = line.replace(f'"{name_content}"', f'"{name_fixed}"', 1)
        fixed_lines.append(line)
    
    content_fixed = '\n'.join(fixed_lines)
    
    # Пытаемся распарсить
    try:
        target_chats = json.loads(content_fixed)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка JSON: {e}")
        # Сохраняем исправленный файл для проверки
        with open('chats_fixed.json', 'w', encoding='utf-8') as f:
            f.write(content_fixed)
        print("💾 Исправленный файл сохранен как chats_fixed.json")
        print("Попробуем прочитать построчно...")
        
        # Альтернативный способ - читаем как Python словарь
        try:
            with open('chats.json', 'r', encoding='utf-8') as f:
                exec_globals = {}
                exec(f"data = {f.read()}", exec_globals)
                target_chats = exec_globals['data']
                print(f"✅ Успешно прочитано через exec: {len(target_chats)} чатов")
        except Exception as e2:
            print(f"❌ И это не сработало: {e2}")
            return
    
    print(f"📂 Загружено {len(target_chats)} чатов")
    
    created_count = 0
    updated_count = 0
    created_chats = []

    for chat_id_str, chat_data in target_chats.items():
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
    print('\n' + '='*50)
    
    if created_chats:
        print('\n✅ Создано чатов:')
        for chat_name in created_chats[:10]:
            print(f'   ✅ {chat_name}')
        
        if len(created_chats) > 10:
            print(f'   ... и еще {len(created_chats) - 10} чатов')

    print('\n' + '='*50)
    print(f'\n✅ Импорт завершен!')
    print(f'   Создано: {created_count}')
    print(f'   Обновлено: {updated_count}')
    print(f'   Всего: {created_count + updated_count}\n')

if __name__ == '__main__':
    fix_and_import()
