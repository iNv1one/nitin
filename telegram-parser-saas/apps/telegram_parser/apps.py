from django.apps import AppConfig


class TelegramParserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.telegram_parser'
    verbose_name = 'Telegram Parser'
    
    def ready(self):
        """Import tasks when app is ready"""
        import apps.telegram_parser.tasks