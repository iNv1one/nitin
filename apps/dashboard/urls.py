from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р° dashboard
    path('', views.dashboard, name='dashboard'),
    
    # РЈРїСЂР°РІР»РµРЅРёРµ РіСЂСѓРїРїР°РјРё РєР»СЋС‡РµРІС‹С… СЃР»РѕРІ
    path('keywords/', views.keyword_groups, name='keyword_groups'),
    path('keywords/create/', views.create_keyword_group, name='create_keyword_group'),
    path('keywords/<int:group_id>/edit/', views.edit_keyword_group, name='edit_keyword_group'),
    path('keywords/<int:group_id>/delete/', views.delete_keyword_group, name='delete_keyword_group'),
    
    # РЈРїСЂР°РІР»РµРЅРёРµ РѕС‚СЃР»РµР¶РёРІР°РµРјС‹РјРё С‡Р°С‚Р°РјРё
    path('chats/', views.monitored_chats, name='monitored_chats'),
    path('chats/add/', views.add_monitored_chat, name='add_monitored_chat'),
    path('chats/<int:chat_id>/toggle/', views.toggle_chat_monitoring, name='toggle_chat_monitoring'),
    path('chats/<int:chat_id>/delete/', views.delete_monitored_chat, name='delete_monitored_chat'),
    
    # РЈРїСЂР°РІР»РµРЅРёРµ РіР»РѕР±Р°Р»СЊРЅС‹РјРё С‡Р°С‚Р°РјРё
    path('global-chats/', views.global_chats, name='global_chats'),
    path('global-chats/<int:chat_id>/toggle/', views.toggle_global_chat, name='toggle_global_chat'),
    path('global-chats/toggle-all/', views.toggle_all_global_chats, name='toggle_all_global_chats'),
    
    # РћР±СЂР°Р±РѕС‚Р°РЅРЅС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ (CRM)
    path('messages/', views.processed_messages, name='processed_messages'),
    path('messages/<int:message_id>/status/', views.update_message_status, name='update_message_status'),
    
    # РќР°СЃС‚СЂРѕР№РєРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    path('settings/', views.settings, name='settings'),
    # Управление парсером
    path('parser/', views.parser_control, name='parser_control'),
    path('parser/start/', views.start_parser, name='start_parser'),
    path('parser/stop/', views.stop_parser, name='stop_parser'),
    path('parser/status/', views.parser_status, name='parser_status'),
    
    # Сырые сообщения (отладка)
    path('raw-messages/', views.raw_messages, name='raw_messages'),

    
    # API endpoints
    path('api/status/', views.api_status, name='api_status'),
]
