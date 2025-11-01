"""
Скрипт для проверки всех доступных диалогов в Telegram
"""
import asyncio
import os
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from telethon import TelegramClient

# Читаем напрямую из .env файла
env_path = os.path.join(os.path.dirname(__file__), '.env')
api_id = None
api_hash = None

if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('TELEGRAM_API_ID='):
                api_id = int(line.split('=')[1].strip())
            elif line.startswith('TELEGRAM_API_HASH='):
                api_hash = line.split('=')[1].strip()

if not api_id or not api_hash:
    print("❌ Не найдены TELEGRAM_API_ID или TELEGRAM_API_HASH в .env файле")
    exit(1)

async def main():
    client = TelegramClient('master_session', api_id, api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ Клиент не авторизован!")
        return
    
    print("✅ Получаем список всех диалогов...")
    print("=" * 80)
    
    dialogs = await client.get_dialogs()
    
    channels_and_groups = []
    
    for dialog in dialogs:
        entity = dialog.entity
        # Фильтруем только группы и каналы
        if hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup'):
            chat_id = entity.id
            # Преобразуем в формат, который использует Telethon для каналов/групп
            if hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup'):
                # Для каналов и супергрупп добавляем префикс -100
                formatted_id = -1000000000000 - entity.id if entity.id > 0 else entity.id
            else:
                formatted_id = -entity.id if entity.id > 0 else entity.id
            
            title = getattr(entity, 'title', 'Unknown')
            is_channel = getattr(entity, 'broadcast', False)
            is_megagroup = getattr(entity, 'megagroup', False)
            
            chat_type = "Канал" if is_channel else "Супергруппа" if is_megagroup else "Группа"
            
            channels_and_groups.append({
                'id': formatted_id,
                'title': title,
                'type': chat_type
            })
            
            print(f"{chat_type}: {title}")
            print(f"  ID: {formatted_id}")
            print("-" * 80)
    
    print(f"\n📊 Всего найдено {len(channels_and_groups)} каналов/групп")
    print("\n🔍 Сверяем с вашими мониторимыми чатами:")
    
    monitored_chats = [
        -1001335987893, -1001278646951, -1001176945179, -1002385254556,
        -1001413864936, -1001360390648, -1001408855384, -1002215188959,
        -1002360093760, -1002243778623, -1001499924694, -1001728102627,
        -1001292776869, -1001211707984, -1001177606993, -1001326461925,
        -1001142696105, -1001416337054, -1001343969698, -1002213805855
    ]
    
    available_ids = [c['id'] for c in channels_and_groups]
    
    print("\n✅ Доступные мониторимые чаты:")
    for chat_id in monitored_chats:
        if chat_id in available_ids:
            chat_info = next(c for c in channels_and_groups if c['id'] == chat_id)
            print(f"  ✓ {chat_id}: {chat_info['title']}")
    
    print("\n❌ НЕ доступные мониторимые чаты (вы не состоите в них):")
    for chat_id in monitored_chats:
        if chat_id not in available_ids:
            print(f"  ✗ {chat_id}")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
