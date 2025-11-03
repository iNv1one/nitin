from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from .models import (
    KeywordGroup, MonitoredChat, ProcessedMessage, BotStatus,
    GlobalChat, UserChatSettings, ChatRequest, MessageTemplate
)


@admin.register(KeywordGroup)
class KeywordGroupAdmin(admin.ModelAdmin):
    """Админка для групп ключевых слов"""
    
    list_display = [
        'name', 'user', 'keywords_count', 'use_ai_filter', 
        'messages_count', 'is_active', 'created_at'
    ]
    list_filter = ['use_ai_filter', 'is_active', 'created_at', 'user__subscription_plan']
    search_fields = ['name', 'user__username', 'keywords']
    list_select_related = ['user']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'name', 'keywords', 'is_active')
        }),
        ('AI настройки', {
            'fields': ('use_ai_filter', 'ai_prompt'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def keywords_count(self, obj):
        return obj.keywords_count
    keywords_count.short_description = 'Ключевые слова'
    
    def messages_count(self, obj):
        """Количество обработанных сообщений"""
        count = obj.processed_messages.count()
        if count > 0:
            url = reverse('admin:telegram_parser_processedmessage_changelist')
            return format_html(
                '<a href="{}?keyword_group__id__exact={}">{}</a>',
                url, obj.id, count
            )
        return count
    messages_count.short_description = 'Сообщений'
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            messages_count=Count('processed_messages')
        )


@admin.register(MonitoredChat)
class MonitoredChatAdmin(admin.ModelAdmin):
    """Админка для мониторимых чатов"""
    
    list_display = [
        'chat_name_display', 'user', 'chat_id', 'messages_count',
        'is_active', 'last_message_at', 'added_at'
    ]
    list_filter = ['is_active', 'added_at', 'last_message_at', 'user__subscription_plan']
    search_fields = ['chat_name', 'chat_username', 'user__username', 'chat_id']
    list_select_related = ['user']
    
    fieldsets = (
        ('Информация о чате', {
            'fields': ('user', 'chat_id', 'chat_name', 'chat_username', 'invite_link')
        }),
        ('Статус', {
            'fields': ('is_active', 'last_message_at')
        }),
        ('Метаданные', {
            'fields': ('added_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['added_at', 'last_message_at']
    
    def chat_name_display(self, obj):
        """Отображение названия чата с иконкой"""
        icon = "🟢" if obj.is_active else "🔴"
        name = obj.chat_name or f"Chat {obj.chat_id}"
        if obj.chat_username:
            return format_html('{} {} (@{})', icon, name, obj.chat_username)
        return format_html('{} {}', icon, name)
    chat_name_display.short_description = 'Чат'
    
    def messages_count(self, obj):
        """Количество сообщений из чата"""
        count = obj.processed_messages.count()
        if count > 0:
            url = reverse('admin:telegram_parser_processedmessage_changelist')
            return format_html(
                '<a href="{}?monitored_chat__id__exact={}">{}</a>',
                url, obj.id, count
            )
        return count
    messages_count.short_description = 'Сообщений'


@admin.register(ProcessedMessage)
class ProcessedMessageAdmin(admin.ModelAdmin):
    """Админка для обработанных сообщений"""
    
    list_display = [
        'message_id', 'user', 'sender_name_display', 'short_text',
        'matched_keywords_display', 'status_flags', 'notification_sent', 'processed_at'
    ]
    list_filter = [
        'notification_sent', 'quality_status', 
        'dialog_started', 'sale_made', 'processed_at',
        'user__subscription_plan'
    ]
    search_fields = [
        'message_text', 'sender_name', 'sender_username', 
        'user__username', 'matched_keywords'
    ]
    list_select_related = ['user', 'keyword_group', 'monitored_chat', 'global_chat']
    date_hierarchy = 'processed_at'
    
    fieldsets = (
        ('Информация о сообщении', {
            'fields': (
                'user', 'keyword_group', 'global_chat', 'monitored_chat',
                'message_id', 'chat_id', 'message_link'
            )
        }),
        ('Отправитель', {
            'fields': ('sender_id', 'sender_name', 'sender_username')
        }),
        ('Содержимое', {
            'fields': ('message_text',)
        }),
        ('Результаты анализа', {
            'fields': ('matched_keywords', 'ai_result', 'ai_score')
        }),
        ('Статусы', {
            'fields': (
                'notification_sent', 'quality_status',
                'dialog_started', 'sale_made', 'telegram_message_id'
            )
        }),
        ('Дополнительно', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('processed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['processed_at', 'updated_at']
    
    # Действия
    actions = ['mark_as_qualified', 'mark_as_unqualified', 'mark_dialog_started']
    
    def sender_name_display(self, obj):
        """Отображение отправителя"""
        if obj.sender_username:
            return format_html('{} (@{})', obj.sender_name, obj.sender_username)
        return obj.sender_name or 'Неизвестно'
    sender_name_display.short_description = 'Отправитель'
    
    def short_text(self, obj):
        """Сокращенный текст сообщения"""
        return obj.short_message_text
    short_text.short_description = 'Сообщение'
    
    def matched_keywords_display(self, obj):
        """Отображение найденных ключевых слов"""
        keywords = obj.matched_keywords_display
        if len(keywords) > 50:
            return keywords[:50] + "..."
        return keywords
    matched_keywords_display.short_description = 'Ключевые слова'
    
    def status_flags(self, obj):
        """Флаги статуса"""
        flags = []
        if obj.quality_status == 'qualified':
            flags.append("⭐ Квалифицирован")
        elif obj.quality_status == 'unqualified':
            flags.append("❌ Неквалифицирован")
        elif obj.quality_status == 'spam':
            flags.append("🚫 Спам")
        if obj.dialog_started:
            flags.append("💬 Диалог")
        if obj.sale_made:
            flags.append("💰 Продажа")
        
        return " | ".join(flags) if flags else "—"
    status_flags.short_description = 'Статус'
    
    # Actions
    def mark_as_qualified(self, request, queryset):
        """Отметить как квалифицированные"""
        updated = queryset.update(quality_status='qualified')
        self.message_user(request, f"Отмечено как квалифицированные: {updated} сообщений")
    mark_as_qualified.short_description = "Отметить как квалифицированные"
    
    def mark_as_unqualified(self, request, queryset):
        """Отметить как неквалифицированные"""
        updated = queryset.update(quality_status='unqualified')
        self.message_user(request, f"Отмечено как неквалифицированные: {updated} сообщений")
    mark_as_unqualified.short_description = "Отметить как неквалифицированные"
    
    def mark_dialog_started(self, request, queryset):
        """Отметить что диалог начат"""
        updated = queryset.update(dialog_started=True)
        self.message_user(request, f"Отмечено что диалог начат: {updated} сообщений")
    mark_dialog_started.short_description = "Отметить что диалог начат"


@admin.register(BotStatus)
class BotStatusAdmin(admin.ModelAdmin):
    """Админка для статуса бота"""
    
    list_display = [
        'bot_username', 'status_display', 'uptime_display',
        'total_chats_monitored', 'total_users', 'messages_processed_today',
        'last_heartbeat'
    ]
    
    fieldsets = (
        ('Статус бота', {
            'fields': ('bot_username', 'is_running', 'last_heartbeat', 'started_at')
        }),
        ('Статистика', {
            'fields': (
                'total_chats_monitored', 'total_users',
                'messages_processed_today', 'messages_processed_total'
            )
        }),
        ('Ошибки', {
            'fields': ('errors_count', 'last_error', 'last_error_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['last_heartbeat']
    
    def status_display(self, obj):
        """Отображение статуса с цветом"""
        if obj.is_running:
            health = "🟢 Здоров" if obj.is_healthy else "🟡 Проблемы"
            return format_html('🟢 Работает ({})', health)
        return "🔴 Остановлен"
    status_display.short_description = 'Статус'
    
    def uptime_display(self, obj):
        """Отображение времени работы"""
        return obj.uptime
    uptime_display.short_description = 'Время работы'
    
    def has_add_permission(self, request):
        """Запрещаем создание нескольких записей статуса"""
        return not BotStatus.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Запрещаем удаление статуса"""
        return False


@admin.register(GlobalChat)
class GlobalChatAdmin(admin.ModelAdmin):
    """Админка для глобальных чатов"""
    
    list_display = [
        'chat_id', 'name', 'enabled_users', 'invite_link_display', 
        'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'chat_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Информация о чате', {
            'fields': ('chat_id', 'name', 'invite_link', 'is_active')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def invite_link_display(self, obj):
        """Отображение ссылки на чат"""
        if obj.invite_link:
            return format_html(
                '<a href="{}" target="_blank">Открыть <i class="fas fa-external-link-alt"></i></a>',
                obj.invite_link
            )
        return '—'
    invite_link_display.short_description = 'Ссылка'
    
    def enabled_users(self, obj):
        """Количество пользователей с включенным чатом"""
        count = obj.get_enabled_users_count()
        if count > 0:
            url = reverse('admin:telegram_parser_userchatsettings_changelist')
            return format_html(
                '<a href="{}?global_chat__id__exact={}&is_enabled__exact=1">{} 👥</a>',
                url, obj.id, count
            )
        return '0 👥'
    enabled_users.short_description = 'Активных пользователей'


@admin.register(UserChatSettings)
class UserChatSettingsAdmin(admin.ModelAdmin):
    """Админка для настроек чатов пользователей"""
    
    list_display = [
        'user', 'global_chat', 'is_enabled_display', 
        'enabled_at', 'disabled_at'
    ]
    list_filter = ['is_enabled', 'enabled_at', 'disabled_at']
    search_fields = ['user__username', 'global_chat__name']
    list_select_related = ['user', 'global_chat']
    readonly_fields = ['enabled_at', 'disabled_at']
    
    fieldsets = (
        ('Настройка', {
            'fields': ('user', 'global_chat', 'is_enabled')
        }),
        ('Метаданные', {
            'fields': ('enabled_at', 'disabled_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_enabled_display(self, obj):
        """Отображение статуса включения"""
        if obj.is_enabled:
            return format_html('<span style="color: green;">✅ Включен</span>')
        return format_html('<span style="color: red;">❌ Выключен</span>')
    is_enabled_display.short_description = 'Статус'


@admin.register(ChatRequest)
class ChatRequestAdmin(admin.ModelAdmin):
    """Админка для заявок на добавление чатов"""
    
    list_display = [
        'id', 'user', 'chat_link_short', 'status_display', 
        'created_at', 'processed_at'
    ]
    list_filter = ['status', 'created_at', 'processed_at']
    search_fields = ['user__username', 'user__email', 'chat_link', 'chat_description']
    list_select_related = ['user', 'global_chat']
    readonly_fields = ['created_at', 'processed_at']
    
    fieldsets = (
        ('Информация о заявке', {
            'fields': ('user', 'chat_link', 'chat_description')
        }),
        ('Обработка', {
            'fields': ('status', 'admin_comment', 'global_chat', 'processed_at')
        }),
        ('Метаданные', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_requests', 'reject_requests']
    
    def chat_link_short(self, obj):
        """Сокращенная ссылка на чат"""
        if len(obj.chat_link) > 50:
            return obj.chat_link[:50] + "..."
        return obj.chat_link
    chat_link_short.short_description = 'Ссылка на чат'
    
    def status_display(self, obj):
        """Цветное отображение статуса"""
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red'
        }
        icons = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }
        color = colors.get(obj.status, 'gray')
        icon = icons.get(obj.status, '❓')
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_status_display()
        )
    status_display.short_description = 'Статус'
    
    def approve_requests(self, request, queryset):
        """Одобрить заявки"""
        from django.utils import timezone
        updated = 0
        for req in queryset.filter(status='pending'):
            req.status = 'approved'
            req.processed_at = timezone.now()
            req.save()
            updated += 1
        self.message_user(request, f"Одобрено заявок: {updated}")
    approve_requests.short_description = "✅ Одобрить выбранные заявки"
    
    def reject_requests(self, request, queryset):
        """Отклонить заявки"""
        from django.utils import timezone
        updated = 0
        for req in queryset.filter(status='pending'):
            req.status = 'rejected'
            req.processed_at = timezone.now()
            req.save()
            updated += 1
        self.message_user(request, f"Отклонено заявок: {updated}")
    reject_requests.short_description = "❌ Отклонить выбранные заявки"


# Настройка админки
admin.site.site_header = "Telegram Parser SaaS"
admin.site.site_title = "Parser Admin"
admin.site.index_title = "Панель управления Telegram Parser" 
 @ a d m i n . r e g i s t e r ( M e s s a g e T e m p l a t e )  
 c l a s s   M e s s a g e T e m p l a t e A d m i n ( a d m i n . M o d e l A d m i n ) :  
         l i s t _ d i s p l a y   =   [ ' n a m e ' ,   ' u s e r ' ,   ' s u b j e c t ' ,   ' i s _ d e f a u l t ' ,   ' i s _ a c t i v e ' ,   ' c r e a t e d _ a t ' ]  
         l i s t _ f i l t e r   =   [ ' i s _ d e f a u l t ' ,   ' i s _ a c t i v e ' ,   ' c r e a t e d _ a t ' ]  
         s e a r c h _ f i e l d s   =   [ ' n a m e ' ,   ' s u b j e c t ' ,   ' t e m p l a t e _ t e x t ' ]  
 