from django.urls import path
from django.http import JsonResponse
from .models import BotStatus

def api_bot_status(request):
    """API endpoint для статуса бота"""
    bot_status = BotStatus.objects.first()
    data = {
        'is_healthy': bot_status.is_healthy if bot_status else False,
        'last_heartbeat': bot_status.last_heartbeat.isoformat() if bot_status and bot_status.last_heartbeat else None,
        'messages_processed_today': bot_status.messages_processed_today if bot_status else 0,
    }
    return JsonResponse(data)


urlpatterns = [
    path('bot-status/', api_bot_status, name='api_bot_status'),
]