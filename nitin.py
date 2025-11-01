import re
import os
import pandas as pd
from datetime import datetime
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util import ssl_ as ssl_util
from telethon import TelegramClient, events
import asyncio
import logging
import random
import json
import signal
import sys
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telethon.tl.types import Channel, Chat, PeerChannel, PeerChat
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import RPCError
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import fcntl
import sqlite3
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import aiosqlite
import hashlib
from openai import OpenAI
import html

def escape_html(text):
    """Экранирует HTML символы для безопасной отправки"""
    if not text:
        return text
    return html.escape(str(text))

def truncate_message(text, max_length=4000):
    """Обрезает сообщение до максимальной длины"""
    if not text:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

# Конфигурация API ключей и токенов
api_id = 23909433
api_hash = '128760f536df8072c1ed6551ad4599ef'
grok_api_key = 'xai-0HtySrKXBtkSSO7Tmv05DXNrDUDMLjUzc5qHmSSxpDSWBW1UiRlqNXFgjlC089kKSOowWuxIw7FMG0Wn'
grok_api_url = 'https://api.x.ai/v1'
bot_token = '7193620780:AAEM_QlyHeGMFbppRp2Uw7ObBrL73lEjkL0'

# ID Google таблицы
main_spreadsheet_id = '1i3w2FvV5IJQ2UxytWvN7Yj8DR4L_7vlJOFBqfsr9j9Q'  # Рабочий ID таблицы

# Настройка логирования с ротацией файлов
import logging.handlers

# Настройка ротации логов (логи в корне папки)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler = logging.handlers.RotatingFileHandler(
    'bot.log',  # Убираем папку logs/
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
log_handler.setFormatter(log_formatter)

# Также выводим в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# Настройка основного логгера
logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler, console_handler]
)

def test_grok_connection():
    try:
        logging.info(f"[GROK TEST] Attempting connection to {grok_api_url}")
        
        client = OpenAI(
            api_key=grok_api_key,
            base_url=grok_api_url
        )
        
        completion = client.chat.completions.create(
            model="grok-3",
            messages=[
                {"role": "user", "content": "Hello"}
            ]
        )
        
        logging.info(f"[GROK TEST] Connection successful")
        logging.info(f"[GROK TEST] Response: {completion.choices[0].message.content}")
        
        return True
        
    except Exception as e:
        logging.error(f"[GROK TEST] Error: {str(e)}")
        logging.error(f"[GROK TEST] Response: {getattr(e, 'response', 'No response')}")
        logging.warning("[GROK TEST] Тест подключения к X.AI API не пройден. Проверьте настройки и соединение.")
        return False

# Выполняем тест подключения сразу после определения функции
if not test_grok_connection():
    logging.warning("[GROK TEST] Тест подключения к Grok API не пройден. Проверьте настройки и соединение.")

enable_gsheets_logging = True
enable_keyword_forwarding = True

# Настройки дедупликации сообщений
DEDUPLICATION_ENABLED = True
DEDUPLICATION_TIME_HOURS = 24  # Время хранения хешей в часах
MAX_USER_MESSAGES_PER_HOUR = 3  # Максимум сообщений от одного пользователя в час

min_delay = 5
max_delay = 15
min_action_delay = 3
max_action_delay = 6

# Инициализация бота
bot = telebot.TeleBot(bot_token)

# Переменные для мониторинга здоровья бота
bot_health = {
    'last_activity': datetime.now(),
    'messages_processed': 0,
    'errors_count': 0,
    'start_time': datetime.now(),
    'is_healthy': True
}

def update_bot_health(activity_type="activity"):
    """Обновляет показатели здоровья бота"""
    global bot_health
    bot_health['last_activity'] = datetime.now()
    if activity_type == "message":
        bot_health['messages_processed'] += 1
    elif activity_type == "error":
        bot_health['errors_count'] += 1
    
    # Проверяем общее здоровье
    time_since_activity = datetime.now() - bot_health['last_activity']
    bot_health['is_healthy'] = time_since_activity.total_seconds() < 300  # 5 минут без активности

def get_bot_health_status():
    """Возвращает статус здоровья бота"""
    uptime = datetime.now() - bot_health['start_time']
    time_since_activity = datetime.now() - bot_health['last_activity']
    
    status = {
        'uptime': str(uptime).split('.')[0],
        'last_activity': time_since_activity.total_seconds(),
        'messages_processed': bot_health['messages_processed'],
        'errors_count': bot_health['errors_count'],
        'is_healthy': bot_health['is_healthy'],
        'error_rate': bot_health['errors_count'] / max(bot_health['messages_processed'], 1) * 100
    }
    
    return status

# Константы для чата ошибок
ERROR_CHAT_ID = -1002745278083  # Чат для отправки ошибок

# Глобальные переменные для мониторинга
last_heartbeat = datetime.now()
consecutive_errors = 0
max_consecutive_errors = 5

async def send_critical_alert(message, error_type="CRITICAL", additional_info=""):
    """Отправляет критическое уведомление администратору"""
    try:
        alert_message = (
            f"🆘 **КРИТИЧЕСКАЯ ОШИБКА БОТА**\n\n"
            f"🔥 Тип: {error_type}\n"
            f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📝 Описание: {message[:800]}...\n\n"
            f"ℹ️ Дополнительно: {additional_info}\n\n"
            f"⚠️ **ТРЕБУЕТСЯ НЕМЕДЛЕННОЕ ВМЕШАТЕЛЬСТВО!**"
        )
        
        # Отправляем несколько попыток для гарантии доставки
        for attempt in range(3):
            try:
                bot.send_message(ERROR_CHAT_ID, alert_message, parse_mode='Markdown')
                logging.critical(f"Критическое уведомление отправлено (попытка {attempt + 1})")
                break
            except Exception as send_error:
                if attempt == 2:  # Последняя попытка
                    logging.error(f"НЕ УДАЛОСЬ ОТПРАВИТЬ КРИТИЧЕСКОЕ УВЕДОМЛЕНИЕ: {send_error}")
                await asyncio.sleep(1)
                
    except Exception as e:
        logging.error(f"Ошибка при отправке критического уведомления: {e}")

async def heartbeat_monitor():
    """Мониторинг жизни бота - отправляет heartbeat каждые 5 минут"""
    global last_heartbeat, consecutive_errors
    
    while True:
        try:
            await asyncio.sleep(300)  # каждые 5 минут
            
            # Проверяем что бот еще жив
            try:
                bot_info = bot.get_me()
                update_bot_health("heartbeat")
                last_heartbeat = datetime.now()
                consecutive_errors = 0  # Сбрасываем счетчик ошибок
                
                logging.info(f"❤️ Heartbeat OK: Bot @{bot_info.username} alive")
                
                # Отправляем статус каждые 30 минут (каждые 6 heartbeat-ов)
                if datetime.now().minute % 30 == 0:
                    status = get_bot_health_status()
                    status_msg = (
                        f"✅ **СТАТУС БОТА**\n\n"
                        f"⏱️ Время работы: {status['uptime']}\n"
                        f"📨 Обработано сообщений: {status['messages_processed']}\n"
                        f"❌ Ошибок: {status['errors_count']}\n"
                        f"📊 Частота ошибок: {status['error_rate']:.1f}%\n"
                        f"🟢 Статус: {'Здоров' if status['is_healthy'] else '🔴 Проблемы'}"
                    )
                    try:
                        bot.send_message(ERROR_CHAT_ID, status_msg, parse_mode='Markdown')
                    except:
                        pass
                        
            except Exception as heartbeat_error:
                consecutive_errors += 1
                error_msg = f"💔 Heartbeat FAILED (ошибка #{consecutive_errors}): {heartbeat_error}"
                logging.error(error_msg)
                
                # Если 3 heartbeat подряд не прошли - критическая ошибка
                if consecutive_errors >= 3:
                    await send_critical_alert(
                        f"Бот не отвечает на heartbeat уже {consecutive_errors} раз подряд. Возможна остановка работы!",
                        "HEARTBEAT_FAILURE",
                        f"Последний успешный heartbeat: {last_heartbeat.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                # Если достигли максимального количества ошибок - перезапуск
                if consecutive_errors >= max_consecutive_errors:
                    await send_critical_alert(
                        f"Критическое количество ошибок heartbeat ({consecutive_errors}). Попытка перезапуска бота.",
                        "BOT_RESTART_REQUIRED",
                        "Автоматический перезапуск"
                    )
                    # Здесь можно добавить логику перезапуска
                    
        except Exception as monitor_error:
            logging.error(f"Ошибка в heartbeat_monitor: {monitor_error}")
            await send_critical_alert(
                f"Ошибка в системе мониторинга heartbeat: {monitor_error}",
                "MONITOR_ERROR",
                "Система мониторинга может быть нарушена"
            )

async def detect_silent_stop():
    """Детектор тихой остановки - проверяет активность бота"""
    last_activity_check = datetime.now()
    
    while True:
        try:
            await asyncio.sleep(600)  # проверяем каждые 10 минут
            
            current_time = datetime.now()
            time_since_last_activity = current_time - bot_health['last_activity']
            
            # Если нет активности более 15 минут - подозрение на тихую остановку
            if time_since_last_activity.total_seconds() > 900:  # 15 минут
                await send_critical_alert(
                    f"ПОДОЗРЕНИЕ НА ТИХУЮ ОСТАНОВКУ! Нет активности уже {time_since_last_activity}",
                    "SILENT_STOP_DETECTED",
                    f"Последняя активность: {bot_health['last_activity'].strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
            # Если нет активности более 30 минут - критическая тихая остановка
            if time_since_last_activity.total_seconds() > 1800:  # 30 минут
                await send_critical_alert(
                    f"КРИТИЧЕСКАЯ ТИХАЯ ОСТАНОВКА! Бот не активен {time_since_last_activity}",
                    "CRITICAL_SILENT_STOP",
                    "Требуется немедленная проверка и перезапуск бота!"
                )
                
        except Exception as e:
            logging.error(f"Ошибка в detect_silent_stop: {e}")

# Тестовый handler для проверки работы бота
@bot.message_handler(commands=['test'])
def test_handler(message):
    update_bot_health("message")
    logging.info(f"[ТЕСТ БОТА] Получена команда /test от пользователя {message.from_user.id}")
    bot.reply_to(message, "🤖 Бот работает! Обработчики активны.")

# Хендлер для проверки состояния здоровья бота
@bot.message_handler(commands=['health'])
def health_handler(message):
    update_bot_health("message")
    status = get_bot_health_status()
    
    health_emoji = "✅" if status['is_healthy'] else "❌"
    
    response = f"""
{health_emoji} **Статус бота**

🕒 **Время работы:** {status['uptime']}
⏰ **Последняя активность:** {status['last_activity']:.0f} сек назад
📊 **Обработано сообщений:** {status['messages_processed']}
⚠️ **Количество ошибок:** {status['errors_count']}
📈 **Процент ошибок:** {status['error_rate']:.2f}%
💚 **Состояние:** {"Здоров" if status['is_healthy'] else "Требует внимания"}
"""
    
    bot.reply_to(message, response, parse_mode='Markdown')

# Дополнительный тест - логируем все callback_query
@bot.callback_query_handler(func=lambda call: call.data.startswith('test:'))
def test_callback_handler(call):
    logging.info(f"[ТЕСТ CALLBACK] Получен тестовый callback: {call.data}")
    bot.answer_callback_query(call.id, text="Тест callback работает!")

def update_message_status_in_sheet(message_id, thread_id, status_type, is_active, spreadsheet_id=main_spreadsheet_id):
    try:
        spreadsheet = client_gspread.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet('messages')
        
        # Получаем все записи
        all_records = sheet.get_all_records()
        row_number = None
        
        # Ищем нужную строку
        for idx, record in enumerate(all_records, start=2):  # start=2 так как первая строка - заголовки
            if str(record['Message ID']) == str(message_id) and str(record.get('Thread ID', '')) == str(thread_id or ''):
                row_number = idx
                break
        
        if row_number:            # Определяем название колонки на основе типа статуса
            status_column_map = {
                'non_qualified': 'Неквал',
                'qualified': 'Квал',
                'spam': 'SPAM',
                'dialog_started': 'Начали диалог',
                'sale_made': 'Есть продажа'
            }
            
            header_row = sheet.row_values(1)

            # Обновляем основной статус
            column_name = status_column_map.get(status_type)
            if column_name:
                try:
                    col_idx = header_row.index(column_name) + 1
                    # Для qualified устанавливаем TRUE, для non_qualified - FALSE
                    if status_type in ['qualified', 'non_qualified']:
                        new_value = status_type == 'qualified'
                    else:
                        new_value = is_active
                    
                    sheet.update_cell(row_number, col_idx, new_value)
                    logging.info(f"Обновлен статус '{column_name}' для сообщения {message_id}: {new_value}")
                except ValueError:
                    logging.error(f"Колонка '{column_name}' не найдена в таблице")
            
            # Всегда обновляем статус "Обработан" при любом действии
            try:
                processed_col_idx = header_row.index('Обработан') + 1
                sheet.update_cell(row_number, processed_col_idx, True)
                logging.info(f"Обновлен статус 'Обработан' для сообщения {message_id}")
            except ValueError:
                logging.error("Колонка 'Обработан' не найдена в таблице")
            return True
        else:
            logging.error(f"Сообщение {message_id} (Thread ID: {thread_id}) не найдено в таблице")
            return False
            
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса в таблице: {e}")
        return False

@bot.callback_query_handler(func=lambda call: not call.data.startswith('test:'))
def handle_callback(call):
    update_bot_health("message")
    try:
        logging.info(f"[КНОПКИ] Получен callback: {call.data}")
        
        if not call.data:
            logging.warning("[КНОПКИ] Получен пустой callback_data")
            return

        parts = call.data.split(':')
        if len(parts) < 4:
            logging.error(f"[КНОПКИ] Некорректный формат callback_data: {call.data}")
            bot.answer_callback_query(call.id, text="Ошибка формата данных")
            return

        action_type = parts[1]
        message_id = parts[2]
        thread_id = parts[3] if parts[3] != '' else None

        logging.info(f"[КНОПКИ] Обработка callback: action={action_type}, message_id={message_id}, thread_id={thread_id}")
        
        try:
            logging.info(f"[КНОПКИ] Нажата кнопка: {action_type}")
            
            # Получаем текущее состояние кнопок из UI
            try:
                current_state = {
                    'qualified': '✅' in next((btn.text for btn in call.message.reply_markup.keyboard[0] if 'Квал' in btn.text), ''),
                    'non_qualified': '✅' in next((btn.text for btn in call.message.reply_markup.keyboard[0] if 'Неквал' in btn.text), ''),
                    'spam': '✅' in next((btn.text for btn in call.message.reply_markup.keyboard[0] if 'Спам' in btn.text), ''),
                    'dialog_started': '✅' in next((btn.text for btn in call.message.reply_markup.keyboard[1] if 'Начали диалог' in btn.text), ''),
                    'sale_made': '✅' in next((btn.text for btn in call.message.reply_markup.keyboard[2] if 'Есть продажа' in btn.text), '')
                }
                logging.info(f"[КНОПКИ] Текущее состояние кнопок: {current_state}")
            except Exception as e:
                logging.error(f"[КНОПКИ] Ошибка при получении состояния кнопок: {e}")
                current_state = {
                    'qualified': False,
                    'non_qualified': False,
                    'spam': False,
                    'dialog_started': False,
                    'sale_made': False
                }
            
            # Создаем новое состояние
            new_state = current_state.copy()
            
            # Обновляем состояние в зависимости от нажатой кнопки
            if action_type == 'spam':
                new_state['spam'] = not current_state['spam']
                if new_state['spam']:
                    new_state['qualified'] = False
                    new_state['non_qualified'] = False
            elif action_type == 'qualified':
                new_state['qualified'] = not current_state['qualified']
                if new_state['qualified']:
                    new_state['non_qualified'] = False
                    new_state['spam'] = False
            elif action_type == 'non_qualified':
                new_state['non_qualified'] = not current_state['non_qualified']
                if new_state['non_qualified']:
                    new_state['qualified'] = False
                    new_state['spam'] = False
            elif action_type == 'dialog_started':
                new_state['dialog_started'] = not current_state['dialog_started']
            elif action_type == 'sale_made':
                new_state['sale_made'] = not current_state['sale_made']
            
            logging.info(f"[КНОПКИ] Новое состояние кнопок: {new_state}")
            
            # Создаем новую клавиатуру
            try:
                new_keyboard = create_inline_keyboard(message_id, thread_id, new_state)
                logging.info(f"[КНОПКИ] Клавиатура создана успешно")
                
                # Обновляем кнопки в сообщении
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=new_keyboard
                )
                logging.info(f"[КНОПКИ] Кнопки обновлены в UI")
                
                # Отвечаем пользователю
                bot.answer_callback_query(call.id, text="✅ Кнопка обновлена", show_alert=False)
                logging.info(f"[КНОПКИ] Отправлен ответ пользователю")
            except Exception as ui_error:
                logging.error(f"[КНОПКИ] Ошибка при обновлении UI: {ui_error}")
                bot.answer_callback_query(call.id, text="Ошибка обновления UI", show_alert=True)

            # Запускаем обновление данных в фоне через executor
            try:
                logging.info(f"[КНОПКИ] Запускаем обновление БД для message_id={message_id}")
                executor.submit(
                    update_message_status_new_logic,
                    message_id,
                    thread_id,
                    action_type
                )
                logging.info(f"[КНОПКИ] Задача обновления БД поставлена в очередь")
            except Exception as executor_error:
                logging.error(f"[КНОПКИ] Ошибка при запуске executor: {executor_error}")

        except Exception as e:
            update_bot_health("error")
            logging.error(f"[КНОПКИ] Ошибка при обновлении UI: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка обновления", show_alert=True)

    except Exception as e:
        update_bot_health("error")
        logging.error(f"Ошибка при обработке callback: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, text="Произошла ошибка при обработке", show_alert=True)
        except:
            pass

async def process_callback_changes(chat_id, ui_message_id, target_message_id, thread_id, action_type, user_id):
    """Асинхронная обработка изменений после нажатия на кнопку"""
    try:
        tasks = []
        
        # Если это спам, добавляем пользователя в спам-лист
        if action_type == 'spam':
            message_info = get_message_info_sync(target_message_id, thread_id)
            if message_info and message_info['sender_id'] and message_info['keyword_group']:
                tasks.append(async_add_spam_user(
                    int(message_info['sender_id']),
                    str(message_info['keyword_group'])
                ))

        # Добавляем задачу обновления Google таблицы
        tasks.append(async_update_gsheets_row(
            target_message_id,
            thread_id,
            action_type
        ))

        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Проверяем результаты
        success = all(not isinstance(r, Exception) for r in results)

        if success:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="✅ База данных обновлена",
                    reply_to_message_id=ui_message_id
                )
            except Exception as e:
                logging.warning(f"Не удалось отправить уведомление об успешном обновлении: {e}")
        else:
            failed_tasks = [i for i, r in enumerate(results) if isinstance(r, Exception)]
            logging.error(f"Ошибки при выполнении задач: {failed_tasks}")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ Ошибка при обновлении базы данных",
                    reply_to_message_id=ui_message_id
                )
            except Exception as e:
                logging.warning(f"Не удалось отправить уведомление об ошибке: {e}")

    except Exception as e:
        logging.error(f"Ошибка при асинхронной обработке изменений: {e}", exc_info=True)

# Путь к файлу блокировки
lock_file_path = 'bot.lock'

# Проверка, что только один экземпляр бота запущен
def acquire_lock():
    lock_file = open(lock_file_path, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        logging.critical("Другой экземпляр бота уже запущен. Завершение работы.")
        sys.exit(1)

# На Windows fcntl не работает, используем альтернативу
if os.name == 'nt':
    def acquire_lock():
        lock_file = open(lock_file_path, 'w')
        try:
            os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            return lock_file
        except FileExistsError:
            logging.critical("Другой экземпляр бота уже запущен. Завершение работы.")
            sys.exit(1)
        except Exception as e:
            logging.critical(f"Ошибка при попытке получить блокировку: {e}")
            sys.exit(1)

# Список ID чатов и каналов для мониторинга с их ссылками для вступления
target_chats = {
    -1002243778623: {
        'name': 'Аномалия с Гребенюком | чат',
        'invite_link': 'https://t.me/anomalyagreb'  # Пример ссылки, замените на реальную
    },
    -1001343969698: {
        'name': 'Чат ТЯК "МОСКВА"',
        'invite_link': 'https://t.me/chattkmoskva'  # None означает, что ссылка не предоставлена
    }
}

# Список всех ID чатов для обработки (используется в коде, где нужен просто список ID)
target_chat_ids = list(target_chats.keys())

# Белый список ID пользователей (админы, боты, и т.д.)
whitelist_user_ids = [
    553147242,
]

# Чёрный список ключевых слов
blacklist_keywords = [
    '@guru883', 'ищудесятку', 'Вакансии', 'заработок', 'бесплатно', 'рассылка', '#готовпомочь', 'Подробнее в описании', 'СЕО оптимизация, реклама, кто разбирается в этом напишите мне в личные сообщения', 'сборка', 'сборкой', 'В онлайн-школу по ЕГЭ требуется:',
    # Добавь другие нежелательные слова
]

# Структура для ключевых слов и получателей
keyword_groups = [
    {
        'name': 'cdek 0',
        'keywords': [
            'sdgewgedsgeqweqxdsdsd'
        ],
        'recipients': [-1002658531864],
        'excluded_chats': [],  # Список ID чатов, которые нужно исключить из обработки (пример: [-1001234567890, -1001987654321])
        'use_neural_check': True,
        'check_user_info': False,  # Включаем проверку информации пользователя
        'neural_prompt': 'Ты помощник, который анализирует сообщения и определяет, является ли это коммерческим предложением товаров с упоминанием доставки/ТК или запросом помощи по доставке. Отвечай только "True" или "False".\n\nTrue — если сообщение содержит: коммерческое предложение товаров с ценами И упоминанием доставки/ТК (СДЭК/ПЭК/КИТ/Боксберри и др.), прайс-лист товаров с ценами И доставкой через ТК, предложение товаров оптом с указанием ТК, запросы помощи по доставке ("подскажите ТК", "посоветуйте доставку").\n\nFalse — если: продажа товаров БЕЗ упоминания доставки/ТК, предложения работы/вакансии, предложения услуг (не товаров), информационные сообщения без коммерческой составляющей, только цены товаров без доставки, общие рекламные сообщения без ТК, упоминание комбикорма, объем заказа свыше 100 кг (максимум 80–100 кг).\n\nКлючевое: True — товары + цены + конкретные способы доставки (ТК) или запросы о доставке, без комбикорма и с весом до 100 кг.\n\nПримеры False: "Ищем дизайнера" (вакансия), "Доставка из Китая" (услуга), "Продаем комбикорм" (комбикорм), "Продам 5 тонн картошки, доставка ПЭК" (свыше 100 кг), "Продам картошку, 50 рублей/кг" (без доставки).',
    }
]

# Настройка Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client_gspread = gspread.authorize(creds)

# ID Google Sheets документа
main_spreadsheet_id = '1i3w2FvV5IJQ2UxytWvN7Yj8DR4L_7vlJOFBqfsr9j9Q'

my_username = '@iNv1one'

# Заголовки для листа messages
messages_headers = [
    'Дата', 'Год', 'Месяц', 'Неделя', 'День',
    'Автор', 'Username', 'Канал', 'Текст сообщения', 'Ключевое слово', 'Ответ OpenAI',
    'Message ID', 'Thread ID', 'Группа ключевых слов', 'Ссылка на сообщение',
    'Обработан', 'Квал', 'Начали диалог', 'Есть продажа', 'SPAM', 'Комментарий'
]

last_processed_message_id = {}
state_file = 'state.json'

# Кэш для предотвращения дублирования обработки сообщений
processed_messages = set()
# Буфер для пакетной отправки сообщений
message_buffer = []
# Кэш состояний кнопок
button_states_cache = {}

update_queue = deque()
executor = ThreadPoolExecutor(max_workers=4)
db_pool = {}

# Улучшенные функции для работы с SQLite с защитой от блокировок
import time
import random

def safe_db_connect(db_path='spam_users.db', timeout=30.0, max_retries=5):
    """Безопасное подключение к SQLite с повторными попытками"""
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=timeout)
            conn.execute('PRAGMA journal_mode=WAL')  # Включаем WAL режим для лучшей concurrent работы
            conn.execute('PRAGMA synchronous=NORMAL')  # Баланс между безопасностью и скоростью
            conn.execute('PRAGMA temp_store=MEMORY')  # Временные таблицы в памяти
            conn.execute('PRAGMA cache_size=10000')  # Увеличиваем кэш
            return conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 0.1 + random.uniform(0, 0.1)  # Экспоненциальная задержка с jitter
                logging.warning(f"База данных заблокирована, попытка {attempt + 1}/{max_retries}, ждем {wait_time:.2f}s")
                time.sleep(wait_time)
                continue
            raise
    raise sqlite3.OperationalError(f"Не удалось подключиться к БД после {max_retries} попыток")

async def safe_async_db_connect(db_path='spam_users.db', timeout=30.0, max_retries=5):
    """Асинхронная версия безопасного подключения к SQLite"""
    for attempt in range(max_retries):
        try:
            conn = await aiosqlite.connect(db_path, timeout=timeout)
            await conn.execute('PRAGMA journal_mode=WAL')
            await conn.execute('PRAGMA synchronous=NORMAL')
            await conn.execute('PRAGMA temp_store=MEMORY')
            await conn.execute('PRAGMA cache_size=10000')
            return conn
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 0.1 + random.uniform(0, 0.1)
                logging.warning(f"База данных заблокирована (async), попытка {attempt + 1}/{max_retries}, ждем {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                continue
            raise
    raise aiosqlite.OperationalError(f"Не удалось подключиться к БД после {max_retries} попыток")

async def flush_buffer_to_gsheets():
    global message_buffer
    if not message_buffer:
        logging.info("Буфер сообщений пуст, нечего сохранять.")
        return
        
    logging.info(f"Начинаем сохранение буфера сообщений. Размер буфера: {len(message_buffer)}")
    
    if not enable_gsheets_logging:
        logging.warning("Сохранение в Google Sheets отключено (enable_gsheets_logging=False). Буфер будет очищен без сохранения.")
        message_buffer = []
        return

    max_retries = 3
    buffer_backup = message_buffer.copy()  # Создаем копию на случай ошибки
    
    for attempt in range(max_retries):
        try:
            logging.info(f"Попытка {attempt + 1}/{max_retries} сохранения в Google Sheets")
            await save_to_gsheets(message_buffer, 'messages', main_spreadsheet_id)
            message_buffer = []  # Очищаем буфер только при успешном сохранении
            logging.info("Буфер сообщений успешно сохранен и очищен.")
            return
            
        except Exception as e:
            error_msg = f"Ошибка при сохранении буфера сообщений (попытка {attempt + 1}): {e}"
            logging.error(error_msg)
            
            if attempt < max_retries - 1:
                # Ждем перед повторной попыткой
                wait_time = (attempt + 1) * 5
                logging.info(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                await asyncio.sleep(wait_time)
            else:
                # Последняя попытка не удалась
                final_error_msg = f"КРИТИЧЕСКАЯ ОШИБКА: не удалось сохранить буфер после {max_retries} попыток. Размер потерянных данных: {len(buffer_backup)} сообщений"
                logging.error(final_error_msg)
                await send_error_to_chat(final_error_msg, "CRITICAL_GSHEETS_ERROR", "Критическая ошибка сохранения буфера")
                
                # Сохраняем данные в локальный файл как резервную копию
                try:
                    backup_filename = f"backup_messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(backup_filename, 'w', encoding='utf-8') as f:
                        json.dump(buffer_backup, f, ensure_ascii=False, indent=2)
                    logging.info(f"Данные сохранены в резервный файл: {backup_filename}")
                    await send_error_to_chat(f"Данные сохранены в резервный файл: {backup_filename}", "BACKUP_CREATED", "Резервное копирование")
                except Exception as backup_error:
                    logging.error(f"Не удалось создать резервную копию: {backup_error}")
                
                # Очищаем буфер чтобы избежать накопления данных
                message_buffer = []

def save_state():
    try:
        with open(state_file, 'w') as f:
            json.dump(last_processed_message_id, f)
        logging.info(f"Состояние сохранено в {state_file}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении состояния: {e}")

def load_state():
    global last_processed_message_id
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                last_processed_message_id = json.load(f)
            last_processed_message_id = {str(k): v for k, v in last_processed_message_id.items()}
            logging.info(f"Состояние загружено из {state_file}")
        except Exception as e:
            logging.error(f"Ошибка при загрузке состояния: {e}")

def disable_webhook():
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")
        if response.status_code == 200 and response.json().get('ok'):
            logging.info("Webhook успешно отключён.")
        else:
            logging.error(f"Ошибка при отключении webhook: {response.text}")
    except Exception as e:
        logging.error(f"Ошибка при отключении webhook: {e}")

def exit_gracefully(signum, frame):
    save_state()
    loop.run_until_complete(flush_buffer_to_gsheets())
    bot.stop_polling()
    try:
        os.remove(lock_file_path)
    except Exception as e:
        logging.error(f"Ошибка при удалении файла блокировки: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

async def ensure_worksheet(spreadsheet, sheet_name, headers):
    """Создает или получает лист с повторными попытками"""
    max_retries = 5
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            logging.info(f"Попытка {attempt + 1}/{max_retries} работы с листом {sheet_name}")
            
            # Пытаемся получить существующий лист
            try:
                sheet = spreadsheet.worksheet(sheet_name)
                logging.info(f"Лист {sheet_name} найден успешно")
                
                # Проверяем заголовки
                try:
                    existing_headers = sheet.row_values(1) if sheet.row_count > 0 else []
                    if not existing_headers or len(existing_headers) != len(headers):
                        logging.warning(f"Заголовки листа {sheet_name} требуют обновления")
                        
                        # Расширяем лист если нужно
                        if len(headers) > sheet.col_count:
                            sheet.add_cols(len(headers) - sheet.col_count)
                            await asyncio.sleep(1)
                        
                        # Обновляем заголовки
                        sheet.update('A1', [headers])
                        await asyncio.sleep(1)
                        logging.info(f"Заголовки листа {sheet_name} обновлены")
                        
                except Exception as headers_error:
                    logging.warning(f"Проблема с заголовками листа {sheet_name}: {headers_error}")
                
                return sheet
                
            except gspread.exceptions.WorksheetNotFound:
                logging.info(f"Лист {sheet_name} не существует, создаем новый")
                
                try:
                    # Создаем новый лист
                    sheet = spreadsheet.add_worksheet(
                        title=sheet_name, 
                        rows=1000, 
                        cols=max(len(headers), 10)
                    )
                    await asyncio.sleep(2)  # Даем время на создание
                    
                    # Добавляем заголовки
                    sheet.update('A1', [headers])
                    await asyncio.sleep(1)
                    
                    logging.info(f"Новый лист {sheet_name} создан с заголовками")
                    return sheet
                    
                except Exception as create_error:
                    logging.error(f"Ошибка создания листа {sheet_name} (попытка {attempt + 1}): {create_error}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        raise Exception(f"Не удалось создать лист {sheet_name} после {max_retries} попыток: {create_error}")
                        
            except Exception as get_error:
                logging.error(f"Ошибка получения листа {sheet_name} (попытка {attempt + 1}): {get_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    raise Exception(f"Не удалось получить лист {sheet_name} после {max_retries} попыток: {get_error}")
                    
        except Exception as general_error:
            logging.error(f"Общая ошибка работы с листом {sheet_name} (попытка {attempt + 1}): {general_error}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            else:
                raise Exception(f"Критическая ошибка: не удалось получить или создать лист {sheet_name}: {general_error}")
    
    raise Exception(f"Превышено максимальное количество попыток для листа {sheet_name}")

def get_message_state_sync(message_id, thread_id, spreadsheet_id=main_spreadsheet_id, sheet_name='messages'):
    try:
        spreadsheet = client_gspread.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet(sheet_name)
        all_records = sheet.get_all_records()
        
        for record in all_records:
            if str(record['Message ID']) == str(message_id) and str(record.get('Thread ID', '')) == str(thread_id or ''):
                def convert_to_bool(value):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.upper() == 'TRUE'
                    return bool(value)

                state = {
                    'qualified': convert_to_bool(record.get('Квал')),
                    'non_qualified': convert_to_bool(record.get('Неквал')),
                    'dialog_started': convert_to_bool(record.get('Начали диалог')),
                    'sale_made': convert_to_bool(record.get('Есть продажа')),
                    'spam': convert_to_bool(record.get('SPAM'))
                }
                # Состояние найдено
                return state
                
        state = {'qualified': False, 'non_qualified': False, 'dialog_started': False, 'sale_made': False, 'spam': False}
        # Строка не найдена, возвращаем начальное состояние
        return state
    except Exception as e:
        logging.error(f"Ошибка при получении состояния сообщения {message_id}: {e}")
        state = {'qualified': False, 'non_qualified': False, 'dialog_started': False, 'sale_made': False, 'spam': False}
        # Ошибка, возвращаем начальное состояние
        return state

def update_gsheets_row_sync(message_id, thread_id, action, spreadsheet_id=main_spreadsheet_id, sheet_name='messages'):
    try:
        spreadsheet = client_gspread.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet(sheet_name)
        
        # Найдем строку по Message ID и Thread ID
        cell_list = sheet.findall(str(message_id))
        row_index = None
        
        for cell in cell_list:
            row = sheet.row_values(cell.row)
            thread_id_index = messages_headers.index('Thread ID')
            if str(row[thread_id_index]) == str(thread_id or ''):
                row_index = cell.row
                break

        if row_index is None:
            logging.error(f"Строка для сообщения {message_id} не найдена")
            return False        # Подготовим обновление только для нужного столбца
        updates = []
        
        # Обработан (P) - всегда TRUE
        updates.append((row_index, 16, 'TRUE'))
        
        # Обновляем только тот столбец, который соответствует нажатой кнопке
        if action == 'non_qualified':
            # При неквале ставим FALSE в столбец Квал (Q)
            updates.append((row_index, 17, 'FALSE'))
        elif action == 'qualified':
            # При квале ставим TRUE в столбец Квал (Q)
            updates.append((row_index, 17, 'TRUE'))
        elif action == 'dialog_started':
            # При начали диалог ставим TRUE в столбец Начали диалог (R)
            updates.append((row_index, 18, 'TRUE'))
        elif action == 'sale_made':
            # При есть продажа ставим TRUE в столбец Есть продажа (S)
            updates.append((row_index, 19, 'TRUE'))
        elif action == 'spam':
            # При спаме ставим TRUE в столбец SPAM (T)
            updates.append((row_index, 20, 'TRUE'))

        # Обновляем все изменения за один запрос
        cell_list = []
        for row, col, value in updates:
            cell = sheet.cell(row, col)
            cell.value = value
            cell_list.append(cell)
        
        sheet.update_cells(cell_list)
            
        logging.info(f"Обновлена строка {row_index} в Google Sheets для Message ID {message_id}, действие: {action}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении Google Sheets: {e}", exc_info=True)
        return False

def update_message_status_new_logic(message_id, thread_id, action_type):
    """
    Новая логика обновления статусов:
    1. Сначала обновляем в базе данных
    2. Потом проверяем, есть ли в Google Sheets и обновляем там
    3. Если нет ни в БД, ни в Sheets - отправляем ошибку
    """
    try:
        logging.info(f"[БД ОБНОВЛЕНИЕ] Начинаем обновление статуса для message_id={message_id}, action_type={action_type}")
        
        # Определяем значение в зависимости от типа действия
        if action_type in ['qualified', 'non_qualified']:
            value = action_type == 'qualified'
            logging.info(f"[БД ОБНОВЛЕНИЕ] Тип qualified/non_qualified, value={value}")
        else:
            # Для других действий получаем текущее состояние и инвертируем
            current_message = get_message_from_db_sync(message_id, thread_id)
            logging.info(f"[БД ОБНОВЛЕНИЕ] Получено текущее сообщение из БД: {current_message is not None}")
            if current_message:
                current_value = current_message.get(action_type, False)
                value = not current_value
                logging.info(f"[БД ОБНОВЛЕНИЕ] Инвертируем значение: {current_value} -> {value}")
            else:
                value = True
                logging.info(f"[БД ОБНОВЛЕНИЕ] Сообщение не найдено в БД, устанавливаем value=True")
        
        # 1. Пробуем обновить в базе данных
        try:
            logging.info(f"[БД ОБНОВЛЕНИЕ] Пытаемся обновить БД...")
            update_message_status_in_db_sync(message_id, thread_id, action_type, value)
            logging.info(f"[БД ОБНОВЛЕНИЕ] ✅ Статус '{action_type}' для сообщения {message_id} обновлен в БД: {value}")
            db_updated = True
        except Exception as e:
            logging.error(f"[БД ОБНОВЛЕНИЕ] ❌ Ошибка обновления в БД для сообщения {message_id}: {e}")
            db_updated = False
        
        # 2. Пробуем обновить в Google Sheets (если сообщение там есть)
        gsheets_updated = False
        try:
            logging.info(f"[БД ОБНОВЛЕНИЕ] Проверяем наличие сообщения в Google Sheets...")
            # Проверяем есть ли сообщение в Google Sheets
            message_info = get_message_info_sync(message_id, thread_id)
            if message_info:
                # Сообщение есть в Google Sheets, обновляем
                update_gsheets_row_sync(message_id, thread_id, action_type)
                logging.info(f"✅ Статус '{action_type}' для сообщения {message_id} обновлен в Google Sheets")
                gsheets_updated = True
            else:
                logging.info(f"ℹ️ Сообщение {message_id} не найдено в Google Sheets, пропускаем обновление")
        except Exception as e:
            logging.error(f"❌ Ошибка обновления в Google Sheets для сообщения {message_id}: {e}")
        
        # 3. Проверяем результат и отправляем уведомление/ошибку
        if not db_updated and not gsheets_updated:
            # Сообщение не найдено ни в БД, ни в Sheets
            error_msg = f"❌ КРИТИЧЕСКАЯ ОШИБКА: Сообщение {message_id} (Thread: {thread_id}) не найдено ни в базе данных, ни в Google Sheets!"
            logging.error(error_msg)
            # Отправляем ошибку в чат
            try:
                bot.send_message(
                    chat_id=ERROR_CHAT_ID,
                    text=error_msg,
                    parse_mode='HTML'
                )
            except Exception as notify_error:
                logging.error(f"Не удалось отправить уведомление об ошибке: {notify_error}")
        elif db_updated and not gsheets_updated:
            # Обновлено только в БД
            logging.info(f"✅ Сообщение {message_id} обновлено только в БД (не найдено в Google Sheets)")
        elif db_updated and gsheets_updated:
            # Обновлено в обеих системах
            logging.info(f"✅ Сообщение {message_id} успешно обновлено в БД и Google Sheets")
        else:
            # Обновлено только в Google Sheets (странная ситуация)
            logging.warning(f"⚠️ Сообщение {message_id} обновлено только в Google Sheets (не найдено в БД)")
            
    except Exception as e:
        error_msg = f"❌ Критическая ошибка при обновлении статуса сообщения {message_id}: {e}"
        logging.error(error_msg, exc_info=True)
        try:
            bot.send_message(
                chat_id=ERROR_CHAT_ID,
                text=error_msg,
                parse_mode='HTML'
            )
        except Exception as notify_error:
            logging.error(f"Не удалось отправить уведомление об ошибке: {notify_error}")

async def async_update_gsheets_row(message_id, thread_id, action, spreadsheet_id=main_spreadsheet_id, sheet_name='messages'):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            lambda: update_gsheets_row_sync(message_id, thread_id, action, spreadsheet_id, sheet_name)
        )
        return result
    except Exception as e:
        logging.error(f"Ошибка при асинхронном обновлении Google Sheets: {e}", exc_info=True)
        return False

def find_blacklist_keywords(text):
    matches = []
    for keyword in blacklist_keywords:
        if re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE):
            matches.append(keyword)
    return matches

def find_all_keyword_groups(text, username=None, profile_desc=None, check_user_info=True):
    matches = []
    for group_idx, group in enumerate(keyword_groups):
        # Skip user info check if check_user_info is False or explicitly disabled for this group
        should_check_user_info = check_user_info and group.get('check_user_info', True)
        
        for keyword in group['keywords']:
            keyword_pattern = r'\b' + re.escape(keyword) + r'\b'
            
            # Check main text
            if re.search(keyword_pattern, text, re.IGNORECASE):
                matches.append(('text', keyword, group, group_idx))
            
            # Check username and profile description if enabled for this group
            if should_check_user_info:
                if username and re.search(keyword_pattern, username, re.IGNORECASE):
                    matches.append(('username', keyword, group, group_idx))
                if profile_desc and re.search(keyword_pattern, profile_desc, re.IGNORECASE):
                    matches.append(('profile', keyword, group, group_idx))
    
    return matches

async def check_openai(message_text, prompt):
    try:
        client = OpenAI(
            api_key=grok_api_key,
            base_url=grok_api_url
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f'Сообщение: "{message_text}"'}
        ]

        logging.info(f"[GROK API] Отправляем запрос:")
        logging.info(f"[GROK API] System prompt: {prompt}")
        logging.info(f"[GROK API] User message: {message_text}")

        completion = client.chat.completions.create(
            model="grok-3",
            messages=messages,
            max_tokens=20,  # Увеличено с 5 до 10 для более стабильных ответов
            temperature=0
        )

        result = completion.choices[0].message.content.strip().lower()
        logging.info(f"[GROK API] Получен ответ: {result}")

        # Более гибкая проверка ответа ИИ
        is_valid = (
            result.startswith("true") or 
            result.startswith("да") or 
            result.startswith("yes") or
            "true" in result.split() or
            result == "1"
        )
        logging.info(f"[GROK API] Результат проверки: {'принято' if is_valid else 'отклонено'} (исходный ответ: '{result}')")

        return is_valid

    except Exception as e:
        logging.error(f"Ошибка при вызове Grok API: {str(e)}")
        return False

def init_database():
    try:
        conn = safe_db_connect()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS spam_users (
                user_id INTEGER,
                keyword_group TEXT,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, keyword_group)
            )
        ''')
        
        # Таблица для хранения сообщений с найденными ключевыми словами (для дедупликации)
        c.execute('''
            CREATE TABLE IF NOT EXISTS keyword_messages (
                message_hash TEXT PRIMARY KEY,
                user_id INTEGER,
                message_text TEXT,
                keywords TEXT,
                keyword_group TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                occurrence_count INTEGER DEFAULT 1
            )
        ''')
        
        # Создаем индексы для быстрого поиска
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_keyword_messages_user_id 
            ON keyword_messages(user_id)
        ''')
        
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_keyword_messages_group 
            ON keyword_messages(keyword_group)
        ''')
        
        # Таблица для хранения всех сообщений с их статусами (для работы кнопок)
        c.execute('''
            CREATE TABLE IF NOT EXISTS message_statuses (
                message_id TEXT,
                thread_id TEXT,
                sender_id INTEGER,
                sender_name TEXT,
                sender_username TEXT,
                channel_title TEXT,
                message_text TEXT,
                keyword_group TEXT,
                keywords TEXT,
                openai_result TEXT,
                message_link TEXT,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                qualified BOOLEAN DEFAULT FALSE,
                non_qualified BOOLEAN DEFAULT FALSE,
                spam BOOLEAN DEFAULT FALSE,
                dialog_started BOOLEAN DEFAULT FALSE,
                sale_made BOOLEAN DEFAULT FALSE,
                processed BOOLEAN DEFAULT FALSE,
                comment TEXT DEFAULT '',
                in_gsheets BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (message_id, thread_id)
            )
        ''')
        
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_message_statuses_message_id 
            ON message_statuses(message_id)
        ''')
        
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_message_statuses_sender 
            ON message_statuses(sender_id)
        ''')
        
        conn.commit()
        conn.close()
        logging.info("База данных успешно инициализирована")
    except Exception as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")
        if 'conn' in locals():
            conn.close()
        raise

def is_user_spam(user_id, keyword_group):
    try:
        conn = safe_db_connect()
        c = conn.cursor()
        c.execute('SELECT 1 FROM spam_users WHERE user_id = ? AND keyword_group = ?', 
                  (user_id, keyword_group))
        result = c.fetchone() is not None
        conn.close()
        return result
    except Exception as e:
        logging.error(f"Ошибка при проверке спам-пользователя: {e}")
        return False

async def async_add_spam_user(user_id, keyword_group):
    try:
        db = await safe_async_db_connect()
        await db.execute(
            'INSERT OR REPLACE INTO spam_users (user_id, keyword_group) VALUES (?, ?)',
            (user_id, keyword_group)
        )
        await db.commit()
        await db.close()
        logging.info(f"Асинхронно добавлен спам-пользователь {user_id} для группы {keyword_group}")
    except Exception as e:
        logging.error(f"Ошибка при асинхронном добавлении спам-пользователя: {e}")
        if 'db' in locals():
            await db.close()

# Функции для работы с таблицей message_statuses

async def save_message_to_db(message_id, thread_id, sender_id, sender_name, sender_username, 
                           channel_title, message_text, keyword_group, keywords, openai_result, 
                           message_link, in_gsheets=False):
    """Сохраняет сообщение в базу данных"""
    try:
        db = await safe_async_db_connect()
        await db.execute('''
            INSERT OR REPLACE INTO message_statuses 
            (message_id, thread_id, sender_id, sender_name, sender_username, 
             channel_title, message_text, keyword_group, keywords, openai_result, 
             message_link, in_gsheets)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (str(message_id), str(thread_id or ''), sender_id, sender_name, sender_username,
              channel_title, message_text, keyword_group, keywords, openai_result,
              message_link, in_gsheets))
        await db.commit()
        await db.close()
    except Exception as e:
        logging.error(f"Ошибка при сохранении сообщения в БД: {e}")
        if 'db' in locals():
            await db.close()

async def update_message_status_in_db(message_id, thread_id, status_type, value):
    """Обновляет статус сообщения в базе данных"""
    try:
        db = await safe_async_db_connect()
        # Определяем какое поле обновлять
        field_map = {
            'qualified': 'qualified',
            'non_qualified': 'non_qualified', 
            'spam': 'spam',
            'dialog_started': 'dialog_started',
            'sale_made': 'sale_made',
            'processed': 'processed'
        }
        
        field = field_map.get(status_type)
        if not field:
            logging.error(f"Неизвестный тип статуса: {status_type}")
            await db.close()
            return False
            
        # Обновляем поле
        await db.execute(f'''
            UPDATE message_statuses 
            SET {field} = ? 
            WHERE message_id = ? AND thread_id = ?
        ''', (value, str(message_id), str(thread_id or '')))
        
        await db.commit()
        await db.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса сообщения в БД: {e}")
        if 'db' in locals():
            await db.close()
        return False
        
        field = field_map.get(status_type)
        if not field:
            raise ValueError(f"Неизвестный тип статуса: {status_type}")
        
        query = f'UPDATE message_statuses SET {field} = ?, processed = TRUE WHERE message_id = ? AND thread_id = ?'
        await db.execute(query, (value, str(message_id), str(thread_id or '')))
        await db.commit()

async def get_message_from_db(message_id, thread_id):
    """Получает сообщение из базы данных"""
    try:
        db = await safe_async_db_connect()
        async with db.execute('''
            SELECT * FROM message_statuses 
            WHERE message_id = ? AND thread_id = ?
        ''', (str(message_id), str(thread_id or ''))) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                result = dict(zip(columns, row))
                await db.close()
                return result
            await db.close()
            return None
    except Exception as e:
        logging.error(f"Ошибка при получении сообщения из БД: {e}")
        if 'db' in locals():
            await db.close()
        return None

def update_message_status_in_db_sync(message_id, thread_id, status_type, value):
    """Синхронная версия обновления статуса в БД"""
    try:
        conn = safe_db_connect()
        c = conn.cursor()
        
        field_map = {
            'qualified': 'qualified',
            'non_qualified': 'non_qualified',
            'spam': 'spam', 
            'dialog_started': 'dialog_started',
            'sale_made': 'sale_made',
            'processed': 'processed'
        }
        
        field = field_map.get(status_type)
        if not field:
            conn.close()
            raise ValueError(f"Неизвестный тип статуса: {status_type}")
        
        query = f'UPDATE message_statuses SET {field} = ?, processed = 1 WHERE message_id = ? AND thread_id = ?'
        c.execute(query, (value, str(message_id), str(thread_id or '')))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка при синхронном обновлении статуса сообщения: {e}")
        if 'conn' in locals():
            conn.close()
        raise
    c.execute(query, (value, str(message_id), str(thread_id or '')))
    conn.commit()
    conn.close()

def get_message_from_db_sync(message_id, thread_id):
    """Синхронная версия получения сообщения из БД"""
    conn = sqlite3.connect('spam_users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM message_statuses 
        WHERE message_id = ? AND thread_id = ?
    ''', (str(message_id), str(thread_id or '')))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def create_message_hash(user_id, message_text):
    """Создает хеш от комбинации user_id + текст сообщения"""
    # Нормализуем текст: убираем лишние пробелы, переводим в нижний регистр
    normalized_text = ' '.join(message_text.lower().split())
    # Создаем хеш от user_id + нормализованный текст
    hash_input = f"{user_id}:{normalized_text}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()

async def is_message_duplicate(user_id, message_text):
    """Проверяет, является ли сообщение дубликатом сообщения с ключевыми словами из БД"""
    if not DEDUPLICATION_ENABLED:
        return False
    
    message_hash = create_message_hash(user_id, message_text)
    
    try:
        db = await safe_async_db_connect()
        # Проверяем есть ли такой хеш среди сообщений с ключевыми словами за последние N часов
        cursor = await db.execute('''
            SELECT occurrence_count, first_seen 
            FROM keyword_messages 
            WHERE message_hash = ? 
            AND datetime(last_seen) > datetime('now', '-{} hours')
        '''.format(DEDUPLICATION_TIME_HOURS), (message_hash,))
        
        result = await cursor.fetchone()
        await db.close()
        return result is not None
    except Exception as e:
        logging.error(f"Ошибка при проверке дубликата сообщения: {e}")
        if 'db' in locals():
            await db.close()
        return False

async def check_user_rate_limit(user_id):
    """Проверяет не превышает ли пользователь лимит сообщений в час (проверяем только по сообщениям с ключевыми словами)"""
    if not DEDUPLICATION_ENABLED:
        return False
    
    try:
        db = await safe_async_db_connect()
        cursor = await db.execute('''
            SELECT COUNT(*) 
            FROM keyword_messages 
            WHERE user_id = ? 
            AND datetime(last_seen) > datetime('now', '-1 hour')
        ''', (user_id,))
        
        result = await cursor.fetchone()
        count = result[0] if result else 0
        await db.close()
        
        return count >= MAX_USER_MESSAGES_PER_HOUR
    except Exception as e:
        logging.error(f"Ошибка при проверке лимита пользователя: {e}")
        if 'db' in locals():
            await db.close()
        return False

async def add_keyword_message(user_id, message_text, keywords, keyword_group):
    """Добавляет сообщение с ключевыми словами в базу или обновляет счетчик"""
    if not DEDUPLICATION_ENABLED:
        return
    
    message_hash = create_message_hash(user_id, message_text)
    
    try:
        db = await safe_async_db_connect()
        # Проверяем есть ли уже такой хеш
        cursor = await db.execute(
            'SELECT occurrence_count FROM keyword_messages WHERE message_hash = ?',
            (message_hash,)
        )
        result = await cursor.fetchone()
        
        if result:
            # Обновляем существующую запись
            await db.execute('''
                UPDATE keyword_messages 
                SET last_seen = CURRENT_TIMESTAMP, 
                    occurrence_count = occurrence_count + 1
                WHERE message_hash = ?
            ''', (message_hash,))
        else:
            # Добавляем новую запись
            await db.execute('''
                INSERT INTO keyword_messages (message_hash, user_id, message_text, keywords, keyword_group) 
                VALUES (?, ?, ?, ?, ?)
            ''', (message_hash, user_id, message_text, keywords, keyword_group))
        
        await db.commit()
        await db.close()
    except Exception as e:
        logging.error(f"Ошибка при добавлении ключевого сообщения: {e}")
        if 'db' in locals():
            await db.close()

async def add_processed_message(user_id, message_text):
    """Добавляет сообщение в базу обработанных или обновляет счетчик"""
    if not DEDUPLICATION_ENABLED:
        return
    
    message_hash = create_message_hash(user_id, message_text)
    
    try:
        db = await safe_async_db_connect()
        # Проверяем есть ли уже такой хеш
        cursor = await db.execute(
            'SELECT occurrence_count FROM processed_messages WHERE message_hash = ?',
            (message_hash,)
        )
        result = await cursor.fetchone()
        
        if result:
            # Обновляем существующую запись
            await db.execute('''
                UPDATE processed_messages 
                SET last_seen = CURRENT_TIMESTAMP, 
                    occurrence_count = occurrence_count + 1
                WHERE message_hash = ?
            ''', (message_hash,))
        else:
            # Добавляем новую запись
            await db.execute('''
                INSERT INTO processed_messages (message_hash, user_id) 
                VALUES (?, ?)
            ''', (message_hash, user_id))
        
        await db.commit()
        await db.close()
    except Exception as e:
        logging.error(f"Ошибка при добавлении обработанного сообщения: {e}")
        if 'db' in locals():
            await db.close()

async def cleanup_old_messages():
    """Удаляет старые записи из таблицы keyword_messages"""
    if not DEDUPLICATION_ENABLED:
        return
    
    async with aiosqlite.connect('spam_users.db') as db:
        # Удаляем записи старше чем DEDUPLICATION_TIME_HOURS * 2 (с запасом)
        await db.execute('''
            DELETE FROM keyword_messages 
            WHERE datetime(last_seen) < datetime('now', '-{} hours')
        '''.format(DEDUPLICATION_TIME_HOURS * 2))
        
        await db.commit()
        
        # Логируем количество удаленных записей
        cursor = await db.execute('SELECT changes()')
        deleted_count = await cursor.fetchone()
        if deleted_count and deleted_count[0] > 0:
            logging.info(f"Удалено {deleted_count[0]} старых записей из таблицы дедупликации keyword_messages")

def save_error_to_gsheets(error_message, error_type="ERROR", context=""):
    """
    Сохраняет сообщение об ошибке в Google Sheets
    """
    try:
        if not enable_gsheets_logging:
            logging.warning("Сохранение ошибок в Google Sheets отключено (enable_gsheets_logging=False)")
            return
        
        spreadsheet = client_gspread.open_by_key(main_spreadsheet_id)
        sheet = spreadsheet.worksheet('errors')
        
        current_time = datetime.now()
        year = current_time.year
        month = current_time.month
        week = current_time.isocalendar().week
        day = current_time.day
        
        error_info = {
            'Дата': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Год': year,
            'Месяц': month,
            'Неделя': week,
            'День': day,
            'Тип ошибки': error_type,
            'Сообщение': error_message,
            'Контекст': context
        }
        
        # Добавляем новую запись
        sheet.append_row(list(error_info.values()))
        logging.info(f"Сообщение об ошибке успешно сохранено в Google Sheets: {error_info}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении сообщения об ошибке в Google Sheets: {e}")

async def send_error_to_chat(error_message, error_type="ERROR", context=""):
    """
    Отправляет сообщение об ошибке в специальный чат для мониторинга ошибок
    """
    try:
        formatted_message = f"🚨 {error_type}\n\n"
        if context:
            formatted_message += f"Контекст: {context}\n\n"
        formatted_message += f"Ошибка: {error_message}\n\n"
        formatted_message += f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Ограничиваем длину сообщения до 4096 символов (лимит Telegram)
        if len(formatted_message) > 4096:
            formatted_message = formatted_message[:4093] + "..."
        
        bot.send_message(ERROR_CHAT_ID, formatted_message)
        logging.info(f"Сообщение об ошибке отправлено в чат {ERROR_CHAT_ID}")
    except Exception as e:
        logging.error(f"Не удалось отправить ошибку в чат {ERROR_CHAT_ID}: {e}")

async def log_error_and_send(error_message, context="", send_to_chat=True):
    """
    Логирует ошибку и отправляет её в специальный чат
    """
    logging.error(error_message)
    if send_to_chat:
        await send_error_to_chat(error_message, "ERROR", context)

async def check_channel_write_permissions():
    """
    Проверяет права доступа на запись сообщений в каналы из keyword_groups
    """
    permission_errors = []
    
    for group in keyword_groups:
        group_name = group['name']
        recipients = group['recipients']
        
        for chat_id in recipients:
            try:
                # Получаем информацию о чате
                chat_info = bot.get_chat(chat_id)
                
                # Получаем информацию о себе в этом чате
                try:
                    member = bot.get_chat_member(chat_id, bot.get_me().id)
                    
                    # Проверяем, есть ли права на отправку сообщений
                    if member.status in ['left', 'kicked']:
                        error_msg = f"Бот исключен из чата {chat_info.title} (ID: {chat_id}) для группы '{group_name}'"
                        permission_errors.append(error_msg)
                        logging.error(error_msg)
                    elif member.status == 'restricted' and not member.can_send_messages:
                        error_msg = f"У бота нет прав на отправку сообщений в чате {chat_info.title} (ID: {chat_id}) для группы '{group_name}'"
                        permission_errors.append(error_msg)
                        logging.error(error_msg)
                    else:
                        logging.info(f"Права доступа к чату {chat_info.title} (ID: {chat_id}) для группы '{group_name}' - OK")
                        
                except Exception as member_error:
                    error_msg = f"Не удалось получить информацию о правах в чате {chat_id} для группы '{group_name}': {member_error}"
                    permission_errors.append(error_msg)
                    logging.error(error_msg)
                    
            except Exception as chat_error:
                error_msg = f"Не удалось получить информацию о чате {chat_id} для группы '{group_name}': {chat_error}"
                permission_errors.append(error_msg)
                logging.error(error_msg)
    
    # Если есть ошибки доступа, отправляем их в чат ошибок
    if permission_errors:
        error_summary = f"Обнаружены проблемы с правами доступа к {len(permission_errors)} чатам:\n\n"
        for i, error in enumerate(permission_errors, 1):
            error_summary += f"{i}. {error}\n"
        
        await send_error_to_chat(error_summary, "PERMISSION_ERROR", "Проверка прав доступа при запуске")
    else:
        logging.info("Проверка прав доступа завершена успешно - все чаты доступны")
    
    return permission_errors

def create_inline_keyboard(message_id, thread_id, state=None):
    keyboard = InlineKeyboardMarkup()
    non_qualified_text = "Неквал ✅" if state and state.get('non_qualified', False) else "Неквал"
    qualified_text = "Квал ✅" if state and state.get('qualified', False) else "Квал"
    spam_text = "Спам ✅" if state and state.get('spam', False) else "Спам"
    dialog_text = "Начали диалог ✅" if state and state.get('dialog_started', False) else "Начали диалог"
    sale_text = "Есть продажа ✅" if state and state.get('sale_made', False) else "Есть продажа"

    # Создаем клавиатуру для управления состояниями

    keyboard.row(
        InlineKeyboardButton(non_qualified_text, callback_data=f"action:non_qualified:{message_id}:{thread_id or ''}"),
        InlineKeyboardButton(qualified_text, callback_data=f"action:qualified:{message_id}:{thread_id or ''}"),
        InlineKeyboardButton(spam_text, callback_data=f"action:spam:{message_id}:{thread_id or ''}")
    )
    keyboard.row(
        InlineKeyboardButton(dialog_text, callback_data=f"action:dialog_started:{message_id}:{thread_id or ''}")
    )
    keyboard.row(
        InlineKeyboardButton(sale_text, callback_data=f"action:sale_made:{message_id}:{thread_id or ''}")
    )
    return keyboard

def get_message_info_sync(message_id, thread_id, spreadsheet_id=main_spreadsheet_id, sheet_name='messages'):
    try:
        spreadsheet = client_gspread.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet(sheet_name)
        all_records = sheet.get_all_records()
        for record in all_records:
            if str(record['Message ID']) == str(message_id) and str(record.get('Thread ID', '')) == str(thread_id or ''):
                return {
                    'sender_id': record.get('Автор').split('ID ')[-1] if 'ID ' in record.get('Автор', '') else None,
                    'keyword_group': record.get('Группа ключевых слов')
                }
        return None
    except Exception as e:
        logging.error(f"Ошибка при получении информации о сообщении {message_id}: {e}")
        return None

async def collect_message_data(client, message, channel_title, thread_id=None):
    global message_buffer
    try:
        if message is None:
            logging.warning("Сообщение отсутствует.")
            return

        if not message.message and not message.media:
            logging.info("Сообщение не содержит текст или медиа. Пропуск.")
            return

        if "Ваше сообщение попало под фильтр спам-слов" in (message.message or ""):
            logging.info("Сообщение удалено спам-фильтром. Пропуск.")
            return

        message_key = f"{message.chat_id}_{message.id}"
        if message_key in processed_messages:
            logging.info(f"Сообщение ID {message.id} уже обработано. Пропуск.")
            return
        processed_messages.add(message_key)

        sender = message.sender_id
        if sender in whitelist_user_ids:
            logging.info(f"Сообщение ID {message.id} от пользователя {sender} в белом списке. Пропуск.")
            return

        message_text = message.message or "[Медиа]"

        sender_name = "Неизвестный отправитель"
        sender_username = "Нет username"

        if sender:
            try:
                sender_entity = await client.get_entity(sender)
                if hasattr(sender_entity, 'first_name') and sender_entity.first_name:
                    sender_name = sender_entity.first_name or ""
                    if sender_entity.last_name:
                        sender_name += f" {sender_entity.last_name}"
                elif hasattr(sender_entity, 'title') and sender_entity.title:
                    sender_name = sender_entity.title
                sender_username = sender_entity.username or "Нет username"
                if sender_username != "Нет username":
                    sender_username = f"@{sender_username}"
            except Exception as e:
                logging.warning(f"Не удалось получить информацию о пользователе с ID {sender} через get_entity: {e}")
                try:
                    await asyncio.sleep(0.1)
                    full_user = await client(GetFullUserRequest(id=sender))
                    user = full_user.users[0]
                    sender_name = (f"{user.first_name} {user.last_name or ''}".strip() if user.first_name else
                                   f"Пользователь ID {sender}")
                    sender_username = f"@{user.username}" if user.username else "Нет username"
                    logging.info(f"Успешно получены данные пользователя {sender} через GetFullUserRequest")
                except Exception as e2:
                    logging.warning(f"Не удалось получить данные пользователя {sender} через GetFullUserRequest: {e2}")
                    sender_name = f"Пользователь ID {sender}"
                    sender_username = "Неизвестно"

        chat_id = (message.to_id.channel_id if hasattr(message.to_id, 'channel_id') else
                   message.to_id.chat_id if hasattr(message.to_id, 'chat_id') else None)
        message_link = f"https://t.me/c/{chat_id}/{message.id}" if chat_id else ""

        current_time = datetime.now()
        year = current_time.year
        month = current_time.month
        week = current_time.isocalendar().week
        day = current_time.day

        blacklist_matches = find_blacklist_keywords(message_text)
        if blacklist_matches:
            message_info = {
                'Дата': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Год': year,
                'Месяц': month,
                'Неделя': week,
                'День': day,
                'Автор': sender_name or "",
                'Username': sender_username or "",
                'Канал': channel_title or "",
                'Текст сообщения': message_text or "",
                'Ключевое слово': f"Blacklist: {', '.join(blacklist_matches)}",
                'Ответ OpenAI': "",
                'Message ID': message.id,
                'Thread ID': thread_id if thread_id else "",
                'Группа ключевых слов': "Чёрный список",
                'Ссылка на сообщение': message_link,
                'Обработан': False,
                'Квал': False,
                'Начали диалог': False,
                'Есть продажа': False,
                'Комментарий': ""
            }
            # Добавляем в Google Sheets
            message_buffer.append(message_info)
            logging.info(f"Сообщение ID {message.id} из чёрного списка добавлено в буфер Google Sheets.")
            
            # Также сохраняем в базу данных
            try:
                await save_message_to_db(
                    message_id=message.id,
                    thread_id=thread_id,
                    sender_id=sender if sender else None,
                    sender_name=sender_name,
                    sender_username=sender_username,
                    channel_title=channel_title,
                    message_text=message_text,
                    keyword_group="Чёрный список",
                    keywords=f"Blacklist: {', '.join(blacklist_matches)}",
                    openai_result="",
                    message_link=message_link,
                    in_gsheets=True  # Отмечаем что добавлено в Google Sheets
                )
                logging.info(f"Сообщение ID {message.id} из чёрного списка сохранено в БД.")
            except Exception as e:
                logging.error(f"Ошибка при сохранении сообщения чёрного списка {message.id} в БД: {e}")
                
            if len(message_buffer) >= 10:
                await flush_buffer_to_gsheets()
            return

        keyword_groups_matched = find_all_keyword_groups(message_text)

        groups_keywords = {}
        for source, keyword, group, group_idx in keyword_groups_matched:
            group_name = group['name']
            if group_name not in groups_keywords:
                groups_keywords[group_name] = {'keywords': [], 'group': group, 'idx': group_idx, 'sources': []}
            groups_keywords[group_name]['keywords'].append(keyword)
            groups_keywords[group_name]['sources'].append(source)

            # Проверяем ключевые слова в тексте сообщения, имени пользователя и описании профиля
            try:
                # Получаем информацию о пользователе для проверки имени и описания
                profile_desc = None
                if sender:
                    try:
                        sender_entity = await client.get_entity(sender)
                        if hasattr(sender_entity, 'about'):
                            profile_desc = sender_entity.about
                    except Exception as e:
                        logging.warning(f"Не удалось получить описание профиля пользователя {sender}: {e}")

                # Ищем ключевые слова во всех источниках
                all_matches = find_all_keyword_groups(message_text, username=sender_name, profile_desc=profile_desc)
                if not all_matches:
                    # Сообщения без ключевых слов НЕ добавляем в Google Sheets, только в БД для статистики
                    try:
                        await save_message_to_db(
                            message_id=message.id,
                            thread_id=thread_id,
                            sender_id=sender if sender else None,
                            sender_name=sender_name,
                            sender_username=sender_username,
                            channel_title=channel_title,
                            message_text=message_text,
                            keyword_group="",
                            keywords="",
                            openai_result="",
                            message_link=message_link,
                            in_gsheets=False  # НЕ добавляем в Google Sheets
                        )
                        logging.info(f"Сообщение ID {message.id} без ключевых слов сохранено только в БД (не добавлено в Google Sheets).")
                    except Exception as e:
                        logging.error(f"Ошибка при сохранении сообщения {message.id} в БД: {e}")
                    return

                # Группируем совпадения по группам ключевых слов
                matches_by_group = {}
                for source, keyword, group, group_idx in all_matches:
                    group_name = group['name']
                    if group_name not in matches_by_group:
                        matches_by_group[group_name] = {
                            'group': group,
                            'idx': group_idx,
                            'keywords': [],
                            'matches': []
                        }
                    matches_by_group[group_name]['keywords'].append(keyword)
                    matches_by_group[group_name]['matches'].append((source, keyword))
                    
                if not matches_by_group:  # Если нет совпадений
                    try:
                        await save_message_to_db(
                            message_id=message.id,
                            thread_id=thread_id,
                            sender_id=sender if sender else None,
                            sender_name=sender_name,
                            sender_username=sender_username,
                            channel_title=channel_title,
                            message_text=message_text,
                            keyword_group="",
                            keywords="",
                            openai_result="",
                            message_link=message_link,
                            in_gsheets=False
                        )
                        logging.info(f"Сообщение ID {message.id} без ключевых слов сохранено только в БД (не добавлено в Google Sheets).")
                    except Exception as e:
                        logging.error(f"Ошибка при сохранении сообщения {message.id} в БД: {e}")
                    return

            except Exception as e:
                logging.error(f"Ошибка при проверке ключевых слов: {e}")
                matches_by_group = {}
                
            for group_name, match_data in matches_by_group.items():
                keywords = match_data['keywords']
                group = match_data['group']
                group_idx = match_data['idx']
                matches = match_data['matches']
                openai_result = ""

            # Проверка исключенных чатов для данной группы
            excluded_chats = group.get('excluded_chats', [])
            if excluded_chats and message.chat_id in excluded_chats:
                logging.info(f"[ИСКЛЮЧЕНИЕ ЧАТОВ] Чат {message.chat_id} исключен из обработки для группы {group_name}. Пропуск.")
                continue

            # Проверка дедупликации для сообщений с ключевыми словами
            if sender and DEDUPLICATION_ENABLED:
                # Проверяем на дублирование с другими сообщениями с ключевыми словами
                is_duplicate = await is_message_duplicate(sender, message_text)
                if is_duplicate:
                    logging.info(f"[ДЕДУПЛИКАЦИЯ] Сообщение ID {message.id} от пользователя {sender} для группы {group_name} является дублем. Пропуск.")
                    continue
                
                # Проверяем лимит сообщений от пользователя
                rate_limited = await check_user_rate_limit(sender)
                if rate_limited:
                    logging.info(f"[ДЕДУПЛИКАЦИЯ] Пользователь {sender} превысил лимит {MAX_USER_MESSAGES_PER_HOUR} сообщений в час. Пропуск группы {group_name}.")
                    continue

            # Проверяем, нужна ли проверка через нейросеть
            should_process = True
            if group.get('use_neural_check', False):
                try:
                    prompt = group.get('neural_prompt', '')
                    is_valid = await check_openai(message_text, prompt)
                    openai_result = str(is_valid)
                    should_process = is_valid
                    logging.info(f"OpenAI проверка для сообщения ID {message.id}: {openai_result}")
                except Exception as e:
                    logging.error(f"Ошибка при проверке OpenAI: {e}")
                    should_process = False
                    openai_result = "Error"

            # Создаем запись для сообщения с ключевыми словами
            message_info = {
                'Дата': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Год': year,
                'Месяц': month,
                'Неделя': week,
                'День': day,
                'Автор': sender_name or "",
                'Username': sender_username or "",
                'Канал': channel_title or "",
                'Текст сообщения': message_text or "",
                'Ключевое слово': ', '.join(keywords),
                'Ответ OpenAI': openai_result,
                'Message ID': message.id,
                'Thread ID': thread_id if thread_id else "",
                'Группа ключевых слов': group_idx,
                'Ссылка на сообщение': message_link,
                'Обработан': False,
                'Квал': False,
                'Начали диалог': False,
                'Есть продажа': False,
                'SPAM': False,
                'Комментарий': ""
            }
            
            # Добавляем в Google Sheets (только сообщения с ключевыми словами)
            message_buffer.append(message_info)
            logging.info(f"Сообщение ID {message.id} для группы {group_name} добавлено в буфер Google Sheets.")
            
            # Также сохраняем в базу данных
            try:
                await save_message_to_db(
                    message_id=message.id,
                    thread_id=thread_id,
                    sender_id=sender if sender else None,
                    sender_name=sender_name,
                    sender_username=sender_username,
                    channel_title=channel_title,
                    message_text=message_text,
                    keyword_group=group_name,
                    keywords=', '.join(keywords),
                    openai_result=openai_result,
                    message_link=message_link,
                    in_gsheets=True  # Отмечаем что добавлено в Google Sheets
                )
                logging.info(f"Сообщение ID {message.id} для группы {group_name} сохранено в БД.")
            except Exception as e:
                logging.error(f"Ошибка при сохранении сообщения {message.id} в БД: {e}")

            # Добавляем в базу дедупликации только сообщения с ключевыми словами
            if sender and DEDUPLICATION_ENABLED:
                await add_keyword_message(sender, message_text, ', '.join(keywords), group_name)
                # Сообщение добавлено в базу дедупликации

            # Отправляем в канал если:
            # 1. use_neural_check = False (пропускаем всё)
            # 2. use_neural_check = True и should_process = True (прошло проверку ИИ)
            if enable_keyword_forwarding and (not group.get('use_neural_check', False) or should_process):
                try:
                    for recipient_id in group.get('recipients', []):
                        try:
                            keyboard = create_inline_keyboard(message.id, thread_id)
                            
                            # Получаем информацию о канале для правильной ссылки
                            chat_id = message.chat.id
                            # Преобразуем ID в формат с -100, если нужно
                            if str(chat_id).startswith('-100'):
                                target_chat_id = chat_id
                            else:
                                target_chat_id = int(f"-100{abs(chat_id)}")
                            
                            channel_info = target_chats.get(target_chat_id)
                            # Отправляем сообщение в канал
                            if channel_info and channel_info.get('invite_link'):
                                channel_link_html = f"<a href='{channel_info['invite_link']}'>{channel_title}</a>"
                            else:
                                channel_link_html = f"{channel_title} (закрытый канал)"
                            
                            # Формируем информацию о найденных ключевых словах
                            keywords_info = []
                            for source, keyword in matches:  # используем matches из текущей группы
                                location = {
                                    'text': 'в сообщении',
                                    'username': 'в имени пользователя',
                                    'profile': 'в описании профиля'
                                }.get(source, 'в сообщении')
                                keywords_info.append(f"{escape_html(keyword)} ({location})")
                            
                            # Безопасно форматируем сообщение с экранированием HTML
                            safe_sender_name = escape_html(sender_name)
                            safe_sender_username = escape_html(sender_username)
                            safe_message_text = escape_html(message_text)
                            safe_keywords = escape_html(', '.join([kw.split(' (')[0] for kw in keywords_info]))
                            
                            formatted_message = (
                                f"🎯 Новый потенциальный клиент!\n\n"
                                f"👤 Имя: {safe_sender_name}\n"
                                f"🔍 Юзернейм: {safe_sender_username}\n"
                                f"📢 Канал: {channel_link_html}\n"
                                f"🔗 Ссылка на сообщение: {message_link}\n"
                                f"🎯 Ключевые слова: {', '.join(keywords_info)}\n\n"
                                f"💬 Сообщение:\n{safe_message_text}"
                            )
                            
                            # Обрезаем сообщение если оно слишком длинное
                            formatted_message = truncate_message(formatted_message)
                            
                            try:
                                bot.send_message(
                                    chat_id=recipient_id,
                                    text=formatted_message,
                                    reply_markup=keyboard,
                                    parse_mode='HTML',
                                    disable_web_page_preview=True
                                )
                                logging.info(f"Сообщение {message.id} успешно отправлено в канал {recipient_id}")
                            except Exception as send_error:
                                error_code = getattr(send_error, 'error_code', None)
                                if error_code == 400:
                                    if "can't parse entities" in str(send_error) or "Unsupported start tag" in str(send_error):
                                        # Отправляем без HTML форматирования
                                        try:
                                            plain_message = (
                                                f"🎯 Новый потенциальный клиент!\n\n"
                                                f"👤 Имя: {sender_name}\n"
                                                f"🔍 Юзернейм: {sender_username}\n"
                                                f"📢 Канал: {channel_title}\n"
                                                f"🔗 Ссылка: {message_link}\n"
                                                f"🎯 Ключевые слова: {safe_keywords}\n\n"
                                                f"💬 Сообщение:\n{message_text}"
                                            )
                                            bot.send_message(
                                                chat_id=recipient_id,
                                                text=truncate_message(plain_message),
                                                reply_markup=keyboard,
                                                disable_web_page_preview=True
                                            )
                                            logging.info(f"Сообщение {message.id} отправлено в канал {recipient_id} без HTML форматирования")
                                        except Exception as e2:
                                            logging.error(f"Не удалось отправить сообщение {message.id} даже без форматирования: {e2}")
                                            await send_error_to_chat(f"Критическая ошибка отправки: {str(e2)}", "CRITICAL_SEND_ERROR", f"Сообщение {message.id}")
                                    elif "message is too long" in str(send_error):
                                        # Отправляем укороченное сообщение
                                        try:
                                            short_message = (
                                                f"🎯 Новый потенциальный клиент!\n\n"
                                                f"👤 Имя: {safe_sender_name}\n"
                                                f"🔍 Юзернейм: {safe_sender_username}\n"
                                                f"📢 Канал: {channel_link_html}\n"
                                                f"🔗 Ссылка: {message_link}\n"
                                                f"🎯 Ключевые слова: {', '.join(keywords_info)}\n\n"
                                                f"💬 Сообщение слишком длинное, смотрите по ссылке"
                                            )
                                            bot.send_message(
                                                chat_id=recipient_id,
                                                text=short_message,
                                                reply_markup=keyboard,
                                                parse_mode='HTML',
                                                disable_web_page_preview=True
                                            )
                                            logging.info(f"Сообщение {message.id} отправлено в канал {recipient_id} в сокращенном виде")
                                        except Exception as e2:
                                            logging.error(f"Не удалось отправить сокращенное сообщение {message.id}: {e2}")
                                            await send_error_to_chat(f"Ошибка отправки сокращенного сообщения: {str(e2)}", "SEND_ERROR", f"Сообщение {message.id}")
                                    else:
                                        error_msg = f"Ошибка при отправке сообщения {message.id} в канал {recipient_id}: [{error_code}] {str(send_error)}"
                                        logging.error(error_msg)
                                        await send_error_to_chat(error_msg, "SEND_ERROR", f"Отправка сообщения {message.id}")
                                else:
                                    error_msg = f"Ошибка при отправке сообщения {message.id} в канал {recipient_id}: [{error_code}] {str(send_error)}"
                                    logging.error(error_msg)
                                    await send_error_to_chat(error_msg, "SEND_ERROR", f"Отправка сообщения {message.id}")
                        except Exception as e:
                            # Логируем общие ошибки отправки
                            error_msg = f"Общая ошибка при отправке в канал {recipient_id}: {str(e)}"
                            logging.error(error_msg)
                            await send_error_to_chat(error_msg, "GENERAL_SEND_ERROR", f"Отправка в канал {recipient_id}")
                except Exception as e:
                    error_msg = f"Ошибка при обработке пересылки сообщения {message.id}: {str(e)}"
                    logging.error(error_msg)
                    await send_error_to_chat(error_msg, "PROCESSING_ERROR", f"Обработка сообщения {message.id}")

            if len(message_buffer) >= 1:
                await flush_buffer_to_gsheets()

        await asyncio.sleep(10)
        processed_messages.discard(message_key)

    except Exception as e:
        error_msg = f"Ошибка при обработке сообщения: {e}"
        logging.error(error_msg)
        await send_error_to_chat(error_msg, "MESSAGE_PROCESSING_ERROR", "Обработка входящего сообщения")

async def periodic_flush():
    cleanup_counter = 0
    memory_cleanup_counter = 0
    while True:
        await asyncio.sleep(30)
        await flush_buffer_to_gsheets()
        
        # Очищаем старые записи дедупликации каждые 20 итераций (каждые 10 минут)
        cleanup_counter += 1
        if cleanup_counter >= 20:
            await cleanup_old_messages()
            cleanup_counter = 0
            
        # Очищаем processed_messages каждые 120 итераций (каждый час)
        memory_cleanup_counter += 1
        if memory_cleanup_counter >= 120:
            try:
                # Очищаем старые записи из processed_messages (старше 2 часов)
                current_time = time.time()
                initial_size = len(processed_messages)
                
                # Создаем новый set только с недавними сообщениями
                # В этой реализации просто очищаем весь set каждый час для предотвращения memory leak
                processed_messages.clear()
                
                logging.info(f"🧹 Memory cleanup: очищено {initial_size} записей из processed_messages")
                memory_cleanup_counter = 0
                
                # Отправляем уведомление о очистке памяти
                cleanup_msg = (
                    f"🧹 **ОЧИСТКА ПАМЯТИ**\n\n"
                    f"Очищено записей: {initial_size}\n"
                    f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Статус: Успешно"
                )
                try:
                    bot.send_message(ERROR_CHAT_ID, cleanup_msg, parse_mode='Markdown')
                except:
                    pass
                    
            except Exception as e:
                error_msg = f"Ошибка при очистке памяти: {e}"
                logging.error(error_msg)
                await send_critical_alert(error_msg, "MEMORY_CLEANUP_ERROR", "Проблема с очисткой памяти")

async def save_to_gsheets(data, sheet_name, spreadsheet_id):
    logging.info(f"Начинаем сохранение данных в таблицу. enable_gsheets_logging={enable_gsheets_logging}")
    if not enable_gsheets_logging:
        logging.warning("Сохранение в Google Sheets отключено (enable_gsheets_logging=False)")
        return
    retries = 3
    for attempt in range(retries):
        try:
            if data:
                logging.info(f"Подготовка {len(data)} записей для сохранения")
                new_df = pd.DataFrame(data)
                headers = messages_headers
                for col in headers:
                    if col not in new_df.columns:
                        new_df[col] = ""
                    new_df[col] = new_df[col].fillna("").apply(lambda x: "" if x is None or pd.isna(x) else x)
                spreadsheet = client_gspread.open_by_key(spreadsheet_id)
                sheet = await ensure_worksheet(spreadsheet, sheet_name, headers)
                if sheet is None:
                    raise Exception(f"Не удалось получить или создать лист {sheet_name}")
                values = new_df[headers].values.tolist()
                sheet.append_rows(values)
                logging.info(f"Успешно добавлено {len(data)} записей в лист {sheet_name} документа {spreadsheet_id}")
                await asyncio.sleep(2)
            else:
                logging.info(f"Нет новых данных для сохранения в лист {sheet_name} документа {spreadsheet_id}.")
            break
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt * 10
                logging.warning(f"Лимит запросов превышен, повторная попытка через {wait_time} секунд")
                await asyncio.sleep(wait_time)
                if attempt == retries - 1:
                    error_msg = f"Не удалось сохранить данные после {retries} попыток: {e}"
                    logging.error(error_msg)
                    await send_error_to_chat(error_msg, "GSHEETS_API_ERROR", f"Сохранение в {sheet_name}")
            else:
                error_msg = f"Ошибка при сохранении в лист {sheet_name} документа {spreadsheet_id}: {e}"
                logging.error(error_msg)
                await send_error_to_chat(error_msg, "GSHEETS_API_ERROR", f"Сохранение в {sheet_name}")
                break
        except Exception as e:
            error_msg = f"Ошибка при сохранении в лист {sheet_name} документа {spreadsheet_id}: {e}"
            logging.error(error_msg)
            await send_error_to_chat(error_msg, "GSHEETS_ERROR", f"Сохранение в {sheet_name}")
            break

async def monitor_new_messages(client, target_chats):
    @client.on(events.NewMessage(chats=target_chats))
    async def handler(event):
        try:
            update_bot_health("message")
            message = event.message
            channel_title = event.chat.title if event.chat else "Личное сообщение"
            thread_id = message.reply_to_msg_id if message.reply_to_msg_id else None
            
            if getattr(event.chat, 'broadcast', False):
                if not message.post:
                    return
            
            logging.info(f"Новое сообщение в {channel_title} (Thread ID: {thread_id or 'Нет'}): {message.message}")
            await collect_message_data(client, message, channel_title, thread_id)
            
        except Exception as e:
            update_bot_health("error")
            error_msg = f"Ошибка при обработке нового сообщения: {e}"
            logging.error(error_msg, exc_info=True)
            
            # Отправляем критические ошибки в чат
            try:
                await send_error_to_chat(error_msg, "MESSAGE_PROCESSING_ERROR", "Обработка нового сообщения")
            except:
                pass

async def main():
    global loop
    loop = asyncio.get_event_loop()
    
    try:
        # Инициализируем базу данных
        init_database()
        logging.info("База данных инициализирована.")
        
        # Отключаем webhook перед запуском polling
        disable_webhook()
        
        # Создаем клиент Telethon с улучшенной обработкой ошибок
        client = TelegramClient(
            'session_name',
            api_id,
            api_hash,
            device_model='Samsung Galaxy S21',
            system_version='Android 11',
            app_version='8.4.1',
            connection_retries=5,
            retry_delay=5
        )
        
        # Подключаемся с повторными попытками
        max_connection_attempts = 3
        for attempt in range(max_connection_attempts):
            try:
                await client.start()
                logging.info("Успешно авторизованы в Telegram.")
                break
            except Exception as e:
                logging.error(f"Ошибка подключения к Telegram (попытка {attempt + 1}/{max_connection_attempts}): {e}")
                if attempt == max_connection_attempts - 1:
                    raise e
                await asyncio.sleep(10)
        
        load_state()

        def start_bot():
            retry_count = 0
            max_retries = 10  # Увеличиваем количество попыток
            base_delay = 5    # Начальная задержка
            max_delay = 300   # Максимальная задержка (5 минут)
            
            while retry_count < max_retries:
                try:
                    logging.info(f"Запуск polling бота (попытка {retry_count + 1}/{max_retries})")
                    
                    # Проверяем состояние бота перед запуском
                    try:
                        bot_info = bot.get_me()
                        logging.info(f"Бот активен: @{bot_info.username} ({bot_info.id})")
                    except Exception as health_error:
                        logging.error(f"Ошибка проверки состояния бота: {health_error}")
                        raise health_error
                    
                    # Запускаем polling с обработкой ошибок
                    bot.polling(
                        none_stop=True, 
                        interval=2,      # Увеличиваем интервал
                        timeout=60,      # Увеличиваем timeout
                        long_polling_timeout=60  # Долгий polling
                    )
                    
                    # Если дошли до сюда, значит polling завершился нормально
                    logging.info("Polling завершился нормально")
                    break
                    
                except Exception as e:
                    retry_count += 1
                    update_bot_health("error")
                    error_str = str(e).lower()
                    
                    # Классифицируем ошибки
                    is_connection_error = any(phrase in error_str for phrase in [
                        'connection aborted', 'remote end closed', 'connection reset',
                        'timeout', 'network', 'connection error', 'connection refused',
                        'temporary failure', 'name resolution', 'ssl', 'certificate'
                    ])
                    
                    is_telegram_error = any(phrase in error_str for phrase in [
                        'flood control', 'too many requests', 'bad request',
                        'unauthorized', 'forbidden', 'conflict'
                    ])
                    
                    is_critical_error = any(phrase in error_str for phrase in [
                        'module', 'import', 'syntax', 'indentation'
                    ])
                    
                    # Формируем сообщение об ошибке
                    error_type = "🔌 CONNECTION" if is_connection_error else \
                               "📡 TELEGRAM API" if is_telegram_error else \
                               "💥 CRITICAL" if is_critical_error else \
                               "⚠️ UNKNOWN"
                    
                    error_msg = f"Ошибка в polling бота (попытка {retry_count}/{max_retries}): {e}"
                    logging.error(error_msg, exc_info=True)
                    
                    # Отправляем ошибку в чат с улучшенной информацией
                    try:
                        if retry_count >= max_retries:
                            critical_msg = (
                                f"🆘 **КРИТИЧЕСКАЯ ОШИБКА POLLING**\n\n"
                                f"❌ Превышено максимальное количество попыток перезапуска ({max_retries})\n\n"
                                f"🔍 Тип ошибки: {error_type}\n"
                                f"📝 Описание: {str(e)[:400]}...\n\n"
                                f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"🔄 Попытка: {retry_count}/{max_retries}\n\n"
                                f"🚨 **БОТ БУДЕТ ОСТАНОВЛЕН!**\n"
                                f"🔧 **ТРЕБУЕТСЯ РУЧНОЕ ВМЕШАТЕЛЬСТВО**"
                            )
                        else:
                            wait_time = min(base_delay * (2 ** retry_count), max_delay)
                            critical_msg = (
                                f"⚠️ **ОШИБКА POLLING**\n\n"
                                f"🔍 Тип: {error_type}\n"
                                f"📝 Описание: {str(e)[:400]}...\n\n"
                                f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"🔄 Попытка: {retry_count}/{max_retries}\n"
                                f"⏳ Перезапуск через: {wait_time} сек\n\n"
                                f"🔄 Автоматический перезапуск..."
                            )
                        
                        bot.send_message(ERROR_CHAT_ID, critical_msg, parse_mode='Markdown')
                        logging.info("Детальное сообщение об ошибке polling отправлено в чат")
                        
                    except Exception as send_error:
                        logging.error(f"Не удалось отправить ошибку polling в чат: {send_error}")
                        # Попытка отправить упрощенное сообщение
                        try:
                            simple_msg = f"🆘 POLLING ERROR {retry_count}/{max_retries}: {str(e)[:200]}"
                            bot.send_message(ERROR_CHAT_ID, simple_msg)
                        except:
                            pass
                    
                    # Если критическая ошибка или превышено количество попыток
                    if is_critical_error or retry_count >= max_retries:
                        error_msg = f"Критическая ошибка или превышено количество попыток: {e}"
                        logging.critical(error_msg)
                        raise Exception(error_msg)
                    
                    # Экспоненциальная задержка с джиттером
                    wait_time = min(base_delay * (2 ** retry_count), max_delay)
                    jitter = random.uniform(0.8, 1.2)  # Добавляем случайность
                    final_wait = wait_time * jitter
                    
                    logging.info(f"Ожидание {final_wait:.1f} секунд перед повторной попыткой...")
                    # ИСПРАВЛЕНО: используем asyncio.sleep вместо time.sleep для неблокирующего ожидания
                    import asyncio
                    asyncio.run(asyncio.sleep(final_wait))
                    
                    # Очищаем состояние бота перед перезапуском
                    try:
                        bot.stop_polling()
                        logging.info("Предыдущий polling остановлен")
                    except:
                        pass

        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()

        # Проверяем права доступа к каналам из keyword_groups
        logging.info("Проверка прав доступа к каналам из keyword_groups...")
        try:
            permission_errors = await check_channel_write_permissions()
            if permission_errors:
                logging.warning(f"Обнаружены проблемы с правами доступа к {len(permission_errors)} каналам")
            else:
                logging.info("Все каналы из keyword_groups доступны для записи")
        except Exception as e:
            error_msg = f"Ошибка при проверке прав доступа: {e}"
            logging.error(error_msg)
            await send_error_to_chat(error_msg, "PERMISSION_CHECK_ERROR", "Проверка прав доступа при запуске")

        target_chats = []
        failed_chats = []
        print("Проверяемые чаты и каналы:")
        
        for i, chat_id in enumerate(target_chat_ids):
            try:
                # Добавляем паузу каждые 10 чатов чтобы не превысить лимиты API
                if i > 0 and i % 10 == 0:
                    print(f"Пауза после {i} чатов...")
                    await asyncio.sleep(2)
                
                if str(chat_id).startswith('-100'):
                    entity = await client.get_entity(PeerChannel(chat_id))
                else:
                    entity = await client.get_entity(PeerChat(chat_id))
                chat_type = 'Канал' if getattr(entity, 'broadcast', False) else 'Супергруппа' if getattr(entity, 'megagroup', False) else 'Группа'
                forum = '[Форум]' if getattr(entity, 'forum', False) else ''
                title = entity.title if hasattr(entity, 'title') else f"Чат ID {chat_id}"
                print(f"✅ {title} [{chat_type} {forum}] (ID: {chat_id})")
                logging.info(f"Добавлен чат для мониторинга: {title} (ID: {chat_id})")
                target_chats.append(entity)
                
                # Небольшая пауза между запросами
                await asyncio.sleep(0.1)
                
            except Exception as e:
                error_msg = f"Не удалось загрузить чат с ID {chat_id}: {e}"
                logging.warning(error_msg)  # Изменили на warning вместо error
                print(f"❌ Чат {chat_id}: {str(e)[:100]}...")
                failed_chats.append(chat_id)
                
                # Пауза после ошибки
                await asyncio.sleep(0.5)

        # Отправляем сводку по недоступным чатам
        if failed_chats:
            summary_msg = (f"⚠️ НЕДОСТУПНЫЕ ЧАТЫ\n\n"
                          f"Не удалось подключиться к {len(failed_chats)} чатам из {len(target_chat_ids)}\n"
                          f"Успешно подключено: {len(target_chats)}\n\n"
                          f"Бот будет работать с доступными чатами.")
            
            try:
                await send_error_to_chat(summary_msg, "CHAT_ACCESS_WARNING", "Инициализация чатов")
            except:
                pass

        if not target_chats:
            error_msg = "Ни один чат не доступен для мониторинга."
            print("❌ Не удалось загрузить ни один чат для мониторинга.")
            logging.error(error_msg)
            try:
                await send_error_to_chat(error_msg, "CRITICAL_ERROR", "Инициализация чатов")
            except:
                pass
            return
        
        print(f"\n✅ Успешно подключено к {len(target_chats)} чатам из {len(target_chat_ids)}")

        # Отправляем расширенное уведомление об успешном запуске
        try:
            startup_msg = (
                f"🟢 **БОТ УСПЕШНО ЗАПУЩЕН**\n\n"
                f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📊 Мониторинг чатов: {len(target_chats)}\n"
                f"🐍 Версия Python: {sys.version.split()[0]}\n"
                f"💾 База данных: Подключена\n"
                f"📋 Google Sheets: {'Включены' if enable_gsheets_logging else 'Отключены'}\n"
                f"🔄 Пересылка сообщений: {'Включена' if enable_keyword_forwarding else 'Отключена'}\n\n"
                f"🔧 **СИСТЕМЫ МОНИТОРИНГА:**\n"
                f"❤️ Heartbeat Monitor: Активен\n"
                f"🔍 Silent Stop Detector: Активен\n"
                f"🧹 Memory Cleaner: Активен\n"
                f"📨 Periodic Flush: Активен\n\n"
                f"✅ **Статус: Готов к работе**\n"
                f"🛡️ **Полная защита от сбоев активирована**"
            )
            
            bot.send_message(ERROR_CHAT_ID, startup_msg, parse_mode='Markdown')
            logging.info("Расширенное уведомление о запуске отправлено")
        except Exception as e:
            logging.warning(f"Не удалось отправить уведомление о запуске: {e}")
            # Попытка отправить упрощенное уведомление
            try:
                simple_msg = f"🟢 БОТ ЗАПУЩЕН\n\nЧатов: {len(target_chats)}\nВремя: {datetime.now().strftime('%H:%M:%S')}\nСтатус: Готов"
                bot.send_message(ERROR_CHAT_ID, simple_msg)
            except:
                pass

        # Запускаем все асинхронные задачи
        asyncio.create_task(periodic_flush())
        asyncio.create_task(monitor_new_messages(client, target_chats))
        asyncio.create_task(heartbeat_monitor())  # Мониторинг жизни бота
        asyncio.create_task(detect_silent_stop())  # Детектор тихой остановки
        
        logging.info("🚀 Все системы мониторинга запущены")
        await client.run_until_disconnected()
        
    except Exception as e:
        update_bot_health("error")
        error_msg = f"Критическая ошибка в функции main: {e}"
        logging.critical(error_msg, exc_info=True)
        
        # Отправляем критическую ошибку с подробностями
        try:
            critical_msg = (
                f"🆘 **КРИТИЧЕСКАЯ ОШИБКА MAIN**\n\n"
                f"❌ Ошибка: {str(e)[:500]}...\n\n"
                f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"🔄 Функция main завершена с ошибкой!\n"
                f"🔧 **ТРЕБУЕТСЯ ПЕРЕЗАПУСК БОТА**"
            )
            bot.send_message(ERROR_CHAT_ID, critical_msg, parse_mode='Markdown')
            logging.critical("Критическое уведомление о ошибке main отправлено")
        except Exception as send_err:
            logging.error(f"Не удалось отправить критическое уведомление: {send_err}")
        
        raise e

if __name__ == '__main__':
    try:
        if api_id == 'YOUR_API_ID' or api_hash == 'YOUR_API_HASH':
            logging.critical("Укажите свой api_id и api_hash.")
            sys.exit(1)
        if bot_token == 'YOUR_BOT_TOKEN':
            logging.critical("Укажите токен бота.")
            sys.exit(1)
        lock_file = acquire_lock()
        asyncio.run(main())
    except Exception as e:
        error_msg = f"Критическая ошибка при выполнении: {e}"
        logging.critical(error_msg, exc_info=True)
        
        # Отправляем критическую ошибку в чат с максимальными подробностями
        try:
            critical_alert = (
                f"🆘 **КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА БОТА**\n\n"
                f"💥 Ошибка: {str(e)[:700]}...\n\n"
                f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📍 Место: Главная функция запуска\n"
                f"🔧 **БОТ ОСТАНОВЛЕН! ТРЕБУЕТСЯ РУЧНОЙ ПЕРЕЗАПУСК**\n\n"
                f"🚨 **ВНИМАНИЕ: Автоматическая работа прервана!**"
            )
            
            # Пытаемся отправить уведомление несколько раз
            for attempt in range(5):
                try:
                    bot.send_message(ERROR_CHAT_ID, critical_alert, parse_mode='Markdown')
                    logging.critical(f"Критическое уведомление о остановке отправлено (попытка {attempt + 1})")
                    break
                except Exception as send_error:
                    if attempt == 4:  # Последняя попытка
                        logging.error(f"НЕ УДАЛОСЬ ОТПРАВИТЬ КРИТИЧЕСКОЕ УВЕДОМЛЕНИЕ ПОСЛЕ 5 ПОПЫТОК: {send_error}")
                    time.sleep(1)
                    
        except Exception as notify_error:
            logging.error(f"Критическая ошибка при отправке уведомления: {notify_error}")
            print(f"КРИТИЧЕСКАЯ ОШИБКА: {error_msg}")  # Выводим в консоль как последнее средство
    finally:
        try:
            os.remove(lock_file_path)
        except Exception as e:
            logging.error(f"Ошибка при удалении файла блокировки: {e}")