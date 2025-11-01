from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Админка для пользователей"""
    
    # Отображение в списке
    list_display = [
        'username', 'email', 'subscription_plan', 'has_telegram_bot_status',
        'is_active', 'is_staff', 'created_at'
    ]
    list_filter = ['subscription_plan', 'is_active', 'is_staff', 'created_at']
    search_fields = ['username', 'email', 'telegram_user_id']
    
    # Поля для редактирования
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Telegram Settings', {
            'fields': ('telegram_user_id', 'telegram_bot_token', 'notification_chat_id')
        }),
        ('Subscription', {
            'fields': ('subscription_plan',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def has_telegram_bot_status(self, obj):
        """Показывает статус настройки Telegram бота"""
        return "✅ Настроен" if obj.has_telegram_bot else "❌ Не настроен"
    has_telegram_bot_status.short_description = "Telegram Bot"
    
    def get_queryset(self, request):
        """Оптимизируем запросы"""
        return super().get_queryset(request).select_related()