from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Расширенная модель пользователя"""
    
    SUBSCRIPTION_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    
    # Telegram settings
    telegram_user_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="Telegram User ID",
        help_text="ID пользователя в Telegram"
    )
    telegram_bot_token = models.TextField(
        blank=True,
        verbose_name="Bot Token",
        help_text="Токен бота для отправки уведомлений"
    )
    notification_chat_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="Chat ID для уведомлений",
        help_text="ID чата куда отправлять уведомления"
    )
    
    # Sender account (для отправки сообщений лидам)
    sender_api_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Sender API ID",
        help_text="API ID для аккаунта-отправителя"
    )
    sender_api_hash = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Sender API Hash",
        help_text="API Hash для аккаунта-отправителя"
    )
    sender_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Sender Phone",
        help_text="Номер телефона аккаунта-отправителя"
    )
    sender_session_string = models.TextField(
        blank=True,
        verbose_name="Sender Session",
        help_text="Строка сессии для аккаунта-отправителя"
    )
    sender_phone_code_hash = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Phone Code Hash",
        help_text="Хеш кода для авторизации (временное поле)"
    )
    
    # Message templates
    default_message_template = models.TextField(
        blank=True,
        verbose_name="Шаблон сообщения по умолчанию",
        help_text="Шаблон для автоматической отправки. Используйте {name} для имени получателя"
    )
    
    # Subscription
    subscription_plan = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_CHOICES,
        default='free',
        verbose_name="План подписки"
    )
    
    # Usage tracking
    messages_this_month = models.IntegerField(
        default=0,
        verbose_name="Сообщений в этом месяце",
        help_text="Счетчик обработанных сообщений за текущий месяц"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    
    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.username} ({self.get_subscription_plan_display()})"
    
    @property
    def has_telegram_bot(self):
        """Проверяет, есть ли у пользователя настроенный бот"""
        return bool(self.telegram_bot_token and self.notification_chat_id)
    
    @property
    def has_sender_account(self):
        """Проверяет, настроен ли аккаунт для отправки сообщений"""
        return bool(
            self.sender_api_id and 
            self.sender_api_hash and 
            self.sender_phone and 
            self.sender_session_string
        )
    
    @property
    def subscription_limits(self):
        """Возвращает лимиты для текущего плана подписки"""
        limits = {
            'free': {
                'chats': 2,
                'keyword_groups': 3,
                'messages_per_month': 100,
            },
            'pro': {
                'chats': 10,
                'keyword_groups': 15,
                'messages_per_month': 5000,
            },
            'enterprise': {
                'chats': 50,
                'keyword_groups': 100,
                'messages_per_month': 50000,
            }
        }
        return limits.get(self.subscription_plan, limits['free'])
    
    def get_message_limit(self):
        """Возвращает лимит сообщений для текущего плана"""
        return self.subscription_limits['messages_per_month']
    
    def get_keyword_groups_limit(self):
        """Возвращает лимит групп ключевых слов для текущего плана"""
        return self.subscription_limits['keyword_groups']
    
    def get_chats_limit(self):
        """Возвращает лимит чатов для текущего плана"""
        return self.subscription_limits['chats']
    
    def increment_message_count(self):
        """Увеличивает счетчик сообщений"""
        self.messages_this_month += 1
        self.save(update_fields=['messages_this_month'])
    
    def reset_monthly_counter(self):
        """Сбрасывает месячный счетчик сообщений"""
        self.messages_this_month = 0
        self.save(update_fields=['messages_this_month'])