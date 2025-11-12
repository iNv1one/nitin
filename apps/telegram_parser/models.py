from django.db import models
from django.conf import settings
from django.core.validators import MinLengthValidator
from django.utils import timezone
import json


class GlobalChat(models.Model):
    """Глобальные чаты, доступные всем пользователям"""
    chat_id = models.BigIntegerField(unique=True, verbose_name="ID чата Telegram")
    name = models.CharField(max_length=500, verbose_name="Название чата")
    invite_link = models.URLField(max_length=500, blank=True, null=True, verbose_name="Ссылка на чат")
    is_active = models.BooleanField(default=True, verbose_name="Чат активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Добавлен")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    
    class Meta:
        verbose_name = "Глобальный чат"
        verbose_name_plural = "Глобальные чаты"
        ordering = ['name']
        indexes = [
            models.Index(fields=['chat_id']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.chat_id})"
    
    def get_enabled_users_count(self):
        """Количество пользователей с включенным чатом"""
        return self.user_settings.filter(is_enabled=True).count()


class UserChatSettings(models.Model):
    """Настройки пользователя для глобальных чатов"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_settings',
        verbose_name="Пользователь"
    )
    global_chat = models.ForeignKey(
        GlobalChat,
        on_delete=models.CASCADE,
        related_name='user_settings',
        verbose_name="Глобальный чат"
    )
    is_enabled = models.BooleanField(default=True, verbose_name="Включен для пользователя")
    enabled_at = models.DateTimeField(auto_now_add=True, verbose_name="Включен")
    disabled_at = models.DateTimeField(null=True, blank=True, verbose_name="Выключен")
    
    class Meta:
        verbose_name = "Настройка чата пользователя"
        verbose_name_plural = "Настройки чатов пользователей"
        unique_together = [['user', 'global_chat']]
        indexes = [
            models.Index(fields=['user', 'is_enabled']),
        ]
    
    def __str__(self):
        status = "✅" if self.is_enabled else "❌"
        return f"{status} {self.user.username} - {self.global_chat.name}"
    
    def toggle(self):
        """Переключить статус включения"""
        self.is_enabled = not self.is_enabled
        if not self.is_enabled:
            self.disabled_at = timezone.now()
        self.save()


class ChatRequest(models.Model):
    """Заявки пользователей на добавление новых чатов"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает обработки'),
        ('approved', 'Одобрена'),
        ('rejected', 'Отклонена'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_requests',
        verbose_name="Пользователь"
    )
    chat_link = models.CharField(
        max_length=500,
        verbose_name="Ссылка на чат",
        help_text="Ссылка приглашения или @username чата"
    )
    chat_description = models.TextField(
        blank=True,
        verbose_name="Описание чата",
        help_text="Дополнительная информация о чате"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Статус заявки"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Обработана")
    admin_comment = models.TextField(blank=True, verbose_name="Комментарий администратора")
    global_chat = models.ForeignKey(
        GlobalChat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Созданный глобальный чат"
    )
    
    class Meta:
        verbose_name = "Заявка на добавление чата"
        verbose_name_plural = "Заявки на добавление чатов"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.chat_link} ({self.get_status_display()})"


class KeywordGroup(models.Model):
    """Группы ключевых слов пользователя"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="keyword_groups"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название группы",
        validators=[MinLengthValidator(2)]
    )
    keywords = models.JSONField(
        default=list,
        verbose_name="Ключевые слова",
        help_text="Список ключевых слов для поиска"
    )
    
    # Notification settings
    notification_chat_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Chat ID для уведомлений",
        help_text="ID чата Telegram, куда отправлять уведомления по этой группе ключевых слов"
    )
    
    # AI settings
    use_ai_filter = models.BooleanField(
        default=False,
        verbose_name="Использовать AI фильтр",
        help_text="Дополнительная проверка сообщений через ИИ"
    )
    ai_prompt = models.TextField(
        blank=True,
        verbose_name="Промт для AI",
        help_text="Инструкция для ИИ по фильтрации сообщений"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
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
        verbose_name = "Группа ключевых слов"
        verbose_name_plural = "Группы ключевых слов"
        ordering = ['-created_at']
        unique_together = ['user', 'name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    @property
    def keywords_count(self):
        """Количество ключевых слов"""
        return len(self.keywords) if self.keywords else 0
    
    def get_keywords_display(self):
        """Строковое представление ключевых слов"""
        if not self.keywords:
            return "Нет ключевых слов"
        return ", ".join(self.keywords[:5]) + ("..." if len(self.keywords) > 5 else "")


class MonitoredChat(models.Model):
    """Чаты для мониторинга"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="monitored_chats"
    )
    chat_id = models.BigIntegerField(
        verbose_name="ID чата",
        help_text="Telegram ID чата для мониторинга"
    )
    chat_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название чата"
    )
    chat_username = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Username чата",
        help_text="@username чата (если есть)"
    )
    invite_link = models.URLField(
        blank=True,
        verbose_name="Ссылка на чат"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления"
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последнее сообщение"
    )
    
    class Meta:
        verbose_name = "Мониторимый чат"
        verbose_name_plural = "Мониторимые чаты"
        ordering = ['-added_at']
        unique_together = ['user', 'chat_id']
    
    def __str__(self):
        return f"{self.user.username} - {self.chat_name or self.chat_id}"


class ProcessedMessage(models.Model):
    """Обработанные сообщения"""
    
    # Relations
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="processed_messages"
    )
    keyword_group = models.ForeignKey(
        KeywordGroup,
        on_delete=models.CASCADE,
        verbose_name="Группа ключевых слов",
        related_name="processed_messages"
    )
    global_chat = models.ForeignKey(
        GlobalChat,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Глобальный чат",
        related_name="processed_messages"
    )
    monitored_chat = models.ForeignKey(
        MonitoredChat,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Мониторимый чат (устарело)",
        related_name="processed_messages"
    )
    
    # Message data
    message_id = models.BigIntegerField(
        verbose_name="ID сообщения"
    )
    chat_id = models.BigIntegerField(
        verbose_name="ID чата"
    )
    sender_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID отправителя"
    )
    sender_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Имя отправителя"
    )
    sender_username = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Username отправителя"
    )
    message_text = models.TextField(
        verbose_name="Текст сообщения"
    )
    message_link = models.URLField(
        blank=True,
        verbose_name="Ссылка на сообщение"
    )
    
    # Matching data
    matched_keywords = models.JSONField(
        default=list,
        verbose_name="Найденные ключевые слова"
    )
    ai_result = models.TextField(
        blank=True,
        verbose_name="Результат AI проверки"
    )
    ai_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name="AI Score",
        help_text="Оценка релевантности от 0 до 1"
    )
    ai_approved = models.BooleanField(
        default=True,
        verbose_name="Одобрено AI",
        help_text="True если AI одобрил сообщение или AI не использовался"
    )
    
    # Status flags
    notification_sent = models.BooleanField(
        default=False,
        verbose_name="Уведомление отправлено"
    )
    telegram_message_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="ID сообщения в Telegram",
        help_text="ID уведомления в Telegram для редактирования кнопок"
    )
    
    # Lead quality statuses (взаимоисключающие)
    QUALITY_STATUS_CHOICES = [
        ('none', 'Не оценено'),
        ('unqualified', 'Неквал'),
        ('qualified', 'Квал'),
        ('spam', 'Спам'),
    ]
    
    quality_status = models.CharField(
        max_length=20,
        choices=QUALITY_STATUS_CHOICES,
        default='none',
        verbose_name="Качество лида"
    )
    
    # Progress statuses (дополнительные флаги)
    dialog_started = models.BooleanField(
        default=False,
        verbose_name="Диалог начат"
    )
    sale_made = models.BooleanField(
        default=False,
        verbose_name="Продажа совершена"
    )
    
    # Outreach tracking (отправка сообщений)
    message_sent = models.BooleanField(
        default=False,
        verbose_name="Сообщение отправлено",
        help_text="Было ли отправлено сообщение через sender-аккаунт"
    )
    message_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отправки сообщения"
    )
    sent_message_text = models.TextField(
        blank=True,
        verbose_name="Отправленный текст",
        help_text="Текст сообщения, которое было отправлено"
    )
    
    # Additional info
    notes = models.TextField(
        blank=True,
        verbose_name="Заметки",
        help_text="Дополнительные заметки пользователя"
    )
    
    # Timestamps
    processed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата обработки"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    
    class Meta:
        verbose_name = "Обработанное сообщение"
        verbose_name_plural = "Обработанные сообщения"
        ordering = ['-processed_at']
        unique_together = ['user', 'message_id', 'chat_id']
        indexes = [
            models.Index(fields=['user', 'processed_at']),
            models.Index(fields=['quality_status']),
            models.Index(fields=['notification_sent']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - Message {self.message_id}"
    
    @property
    def matched_keywords_display(self):
        """Строковое представление найденных ключевых слов"""
        if not self.matched_keywords:
            return "Нет"
        return ", ".join(self.matched_keywords)
    
    @property
    def short_message_text(self):
        """Сокращенный текст сообщения"""
        if len(self.message_text) <= 100:
            return self.message_text
        return self.message_text[:100] + "..."


class BotStatus(models.Model):
    """Статус главного парсер-бота"""
    
    # Bot info
    bot_username = models.CharField(
        max_length=255,
        default="master_parser",
        verbose_name="Username бота"
    )
    
    # Status
    is_running = models.BooleanField(
        default=False,
        verbose_name="Запущен"
    )
    last_heartbeat = models.DateTimeField(
        auto_now=True,
        verbose_name="Последний heartbeat"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время запуска"
    )
    
    # Statistics
    total_chats_monitored = models.IntegerField(
        default=0,
        verbose_name="Всего чатов мониторится"
    )
    total_users = models.IntegerField(
        default=0,
        verbose_name="Всего пользователей"
    )
    messages_processed_today = models.IntegerField(
        default=0,
        verbose_name="Сообщений обработано сегодня"
    )
    messages_processed_total = models.IntegerField(
        default=0,
        verbose_name="Всего сообщений обработано"
    )
    errors_count = models.IntegerField(
        default=0,
        verbose_name="Количество ошибок"
    )
    last_error = models.TextField(
        blank=True,
        verbose_name="Последняя ошибка"
    )
    last_error_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время последней ошибки"
    )
    
    class Meta:
        verbose_name = "Статус бота"
        verbose_name_plural = "Статус бота"
    
    def __str__(self):
        status = "🟢 Работает" if self.is_running else "🔴 Остановлен"
        return f"Master Parser - {status}"
    
    @property
    def uptime(self):
        """Время работы бота"""
        if not self.started_at:
            return "Не запущен"
        
        if not self.is_running:
            return "Остановлен"
        
        uptime = timezone.now() - self.started_at
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"
    
    @property
    def is_healthy(self):
        """Проверка здоровья бота (heartbeat не старше 5 минут)"""
        if not self.is_running:
            return False
        
        time_diff = timezone.now() - self.last_heartbeat
        return time_diff.total_seconds() < 300  # 5 минут


class RejectedMessage(models.Model):
    """Сообщения, отклоненные AI фильтром"""
    
    # Relations
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="rejected_messages"
    )
    keyword_group = models.ForeignKey(
        KeywordGroup,
        on_delete=models.CASCADE,
        verbose_name="Группа ключевых слов",
        related_name="rejected_messages"
    )
    global_chat = models.ForeignKey(
        GlobalChat,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Глобальный чат",
        related_name="rejected_messages"
    )
    
    # Message data
    message_id = models.BigIntegerField(verbose_name="ID сообщения")
    chat_id = models.BigIntegerField(verbose_name="ID чата")
    sender_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID отправителя")
    sender_name = models.CharField(max_length=255, blank=True, verbose_name="Имя отправителя")
    sender_username = models.CharField(max_length=255, blank=True, verbose_name="Username отправителя")
    message_text = models.TextField(verbose_name="Текст сообщения")
    
    # Rejection data
    matched_keywords = models.JSONField(default=list, verbose_name="Найденные ключевые слова")
    ai_rejection_reason = models.TextField(blank=True, verbose_name="Причина отклонения AI")
    
    # Timestamps
    rejected_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата отклонения")
    
    class Meta:
        verbose_name = "Отклоненное сообщение"
        verbose_name_plural = "Отклоненные сообщения"
        ordering = ['-rejected_at']
        unique_together = ['user', 'message_id', 'chat_id', 'keyword_group']
        indexes = [
            models.Index(fields=['user', 'rejected_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - Rejected {self.message_id}"


class RawMessage(models.Model):
    """Все сырые сообщения, полученные парсером (для отладки)"""
    
    # Message metadata
    message_id = models.BigIntegerField(verbose_name="ID сообщения")
    chat_id = models.BigIntegerField(verbose_name="ID чата")
    chat_name = models.CharField(max_length=500, blank=True, verbose_name="Название чата")
    
    # Sender info
    sender_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID отправителя")
    sender_name = models.CharField(max_length=255, blank=True, default='', verbose_name="Имя отправителя")
    sender_username = models.CharField(max_length=255, blank=True, default='', verbose_name="Username отправителя")
    
    # Message content
    message_text = models.TextField(verbose_name="Текст сообщения")
    message_date = models.DateTimeField(verbose_name="Дата сообщения")
    is_channel_post = models.BooleanField(default=False, verbose_name="Пост канала")
    
    # Processing
    received_at = models.DateTimeField(auto_now_add=True, verbose_name="Получено парсером")
    
    class Meta:
        verbose_name = "Сырое сообщение"
        verbose_name_plural = "Сырые сообщения"
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['-received_at']),
            models.Index(fields=['chat_id']),
        ]
    
    def __str__(self):
        return f"Message {self.message_id} from {self.chat_name} at {self.received_at}"


class MessageTemplate(models.Model):
    """Шаблоны сообщений для отправки лидам"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="message_templates"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название шаблона",
        help_text="Название для удобства (например, 'Первое касание', 'Повторное предложение')"
    )
    subject = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Тема/заголовок",
        help_text="Краткое описание шаблона"
    )
    template_text = models.TextField(
        verbose_name="Текст шаблона",
        help_text="Используйте переменные: {name}, {username}, {chat_name}"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Использовать по умолчанию"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлен"
    )
    
    class Meta:
        verbose_name = "Шаблон сообщения"
        verbose_name_plural = "Шаблоны сообщений"
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"
    
    def save(self, *args, **kwargs):
        # Если этот шаблон становится дефолтным, убираем флаг у остальных
        if self.is_default:
            MessageTemplate.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
    
    def render(self, context: dict) -> str:
        """
        Рендерит шаблон с подстановкой переменных
        
        Args:
            context: Словарь с переменными (name, username, chat_name и т.д.)
            
        Returns:
            str: Отрендеренный текст
        """
        text = self.template_text
        for key, value in context.items():
            text = text.replace(f'{{{key}}}', str(value or ''))
        return text


class SentMessageHistory(models.Model):
    """
    История отправленных сообщений через sender-аккаунт.
    Отслеживает статус прочтения и ответы.
    """
    
    # Связи
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        verbose_name="Пользователь"
    )
    processed_message = models.ForeignKey(
        'ProcessedMessage',
        on_delete=models.CASCADE,
        related_name='sent_history',
        verbose_name="Исходное сообщение-лид",
        null=True,
        blank=True
    )
    
    # Данные получателя
    recipient_username = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Username получателя"
    )
    recipient_user_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Telegram ID получателя"
    )
    recipient_name = models.CharField(
        max_length=500,
        verbose_name="Имя получателя"
    )
    
    # Данные отправки
    sent_message_text = models.TextField(
        verbose_name="Текст отправленного сообщения"
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время отправки"
    )
    sent_from_account = models.CharField(
        max_length=255,
        verbose_name="Sender-аккаунт",
        help_text="Username sender-аккаунта с которого отправили"
    )
    sent_from_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Телефон sender-аккаунта",
        help_text="Номер телефона sender-аккаунта для точной идентификации"
    )
    
    # Статусы отслеживания
    is_delivered = models.BooleanField(
        default=True,
        verbose_name="Доставлено"
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано"
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время прочтения"
    )
    is_replied = models.BooleanField(
        default=False,
        verbose_name="Получен ответ"
    )
    replied_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время ответа"
    )
    reply_text = models.TextField(
        blank=True,
        verbose_name="Текст ответа"
    )
    
    # Метаданные Telegram
    telegram_message_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID сообщения в Telegram"
    )
    chat_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID диалога в Telegram"
    )
    
    # Дополнительная информация
    template_used = models.ForeignKey(
        'MessageTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Использованный шаблон"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Заметки"
    )
    
    class Meta:
        verbose_name = "Отправленное сообщение"
        verbose_name_plural = "Отправленные сообщения"
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['user', '-sent_at']),
            models.Index(fields=['sent_from_account', '-sent_at']),
            models.Index(fields=['recipient_username']),
            models.Index(fields=['is_read', 'is_replied']),
            models.Index(fields=['-sent_at']),
        ]
    
    def __str__(self):
        return f"Сообщение для {self.recipient_name} от {self.sent_at.strftime('%d.%m.%Y %H:%M')}"
    
    def get_status_display(self):
        """Возвращает текстовое описание статуса"""
        if self.is_replied:
            return "Ответил"
        elif self.is_read:
            return "Прочитано"
        elif self.is_delivered:
            return "Доставлено"
        else:
            return "Отправлено"
    
    def get_response_time(self):
        """Время от отправки до ответа"""
        if self.replied_at and self.sent_at:
            delta = self.replied_at - self.sent_at
            hours = delta.total_seconds() / 3600
            if hours < 1:
                minutes = delta.total_seconds() / 60
                return f"{int(minutes)} мин"
            elif hours < 24:
                return f"{int(hours)} ч"
            else:
                days = delta.days
                return f"{days} дн"
        return None
    
    def get_read_time(self):
        """Время от отправки до прочтения"""
        if self.read_at and self.sent_at:
            delta = self.read_at - self.sent_at
            hours = delta.total_seconds() / 3600
            if hours < 1:
                minutes = delta.total_seconds() / 60
                return f"{int(minutes)} мин"
            elif hours < 24:
                return f"{int(hours)} ч"
            else:
                days = delta.days
                return f"{days} дн"
        return None


class SenderAccount(models.Model):
    """Аккаунты для отправки сообщений лидам"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sender_accounts',
        verbose_name="Пользователь"
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Название аккаунта",
        help_text="Например: Рабочий аккаунт, Резервный и т.д."
    )
    phone = models.CharField(
        max_length=20,
        verbose_name="Номер телефона",
        help_text="Номер в международном формате"
    )
    api_id = models.IntegerField(
        verbose_name="API ID",
        help_text="API ID от my.telegram.org"
    )
    api_hash = models.CharField(
        max_length=255,
        verbose_name="API Hash",
        help_text="API Hash от my.telegram.org"
    )
    session_string = models.TextField(
        blank=True,
        verbose_name="Session String",
        help_text="Строка сессии Telegram"
    )
    phone_code_hash = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Phone Code Hash",
        help_text="Временный хеш для авторизации"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="Использовать этот аккаунт для отправки"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    
    class Meta:
        verbose_name = "Sender-аккаунт"
        verbose_name_plural = "Sender-аккаунты"
        ordering = ['-created_at']
        unique_together = [['user', 'phone']]
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        status = "✅" if self.is_active else "❌"
        return f"{status} {self.name} ({self.phone})"
    
    @property
    def is_connected(self):
        """Проверяет, подключен ли аккаунт (есть ли session_string)"""
        return bool(self.session_string)
    
    def toggle_active(self):
        """Переключить статус активности"""
        self.is_active = not self.is_active
        self.save()
