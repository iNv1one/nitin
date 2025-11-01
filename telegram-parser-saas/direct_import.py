# -*- coding: utf-8 -*-
"""
Прямой импорт из Python словаря
"""
import os
import django

# Настройка Django  
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.telegram_parser.models import GlobalChat

# Вставьте сюда ваш словарь target_chats напрямую из вашего сообщения
# Скопируйте всё содержимое из вашего последнего сообщения

print("Скрипт готов. Пожалуйста, вставьте словарь target_chats в этот файл и запустите снова.")
print("После строки 14 добавьте: target_chats = { ... ваш словарь ... }")
