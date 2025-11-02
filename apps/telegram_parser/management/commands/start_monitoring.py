"""
Management команда для запуска Telegram мониторинга
"""
import asyncio
import logging
from django.core.management.base import BaseCommand
from apps.telegram_parser.telegram_client import master_parser

logger = logging.getLogger('telegram_parser')


class Command(BaseCommand):
    help = 'Запускает постоянный мониторинг Telegram чатов'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Запуск Telegram мониторинга...'))
        
        try:
            # Запускаем мониторинг
            asyncio.run(master_parser.start_monitoring())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n⚠️  Получен сигнал остановки'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Ошибка: {e}'))
            logger.error(f'Ошибка в мониторинге: {e}')
            raise
        finally:
            self.stdout.write(self.style.SUCCESS('✅ Мониторинг остановлен'))
