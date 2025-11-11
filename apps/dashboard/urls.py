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
    path('message/<int:message_id>/update-status/', views.ajax_update_message_status, name='ajax_update_message_status'),
    path('messages/<int:message_id>/status/', views.update_message_status, name='update_message_status'),
    path('message/<int:message_id>/send/', views.send_message_to_lead, name='send_message_to_lead'),
    
    # Отправленные сообщения
    path('sent-messages/', views.sent_messages, name='sent_messages'),
    
    # РќР°СЃС‚СЂРѕР№РєРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    path('settings/', views.settings, name='settings'),
    # Управление парсером
    path('parser/', views.parser_control, name='parser_control'),
    path('parser/start/', views.start_parser, name='start_parser'),
    path('parser/stop/', views.stop_parser, name='stop_parser'),
    path('parser/status/', views.parser_status, name='parser_status'),
    
    # Сырые сообщения (отладка)
    path('raw-messages/', views.raw_messages, name='raw_messages'),
    
    # AJAX для детальной статистики (используется на главной)
    path('statistics/groups/', views.statistics_groups_ajax, name='statistics_groups_ajax'),
    path('statistics/chats/', views.statistics_chats_ajax, name='statistics_chats_ajax'),
    
    # Sender-аккаунты
    path('sender-accounts/', views.sender_accounts, name='sender_accounts'),
    path('sender-accounts/setup/', views.setup_sender_account, name='setup_sender_account'),
    path('sender-accounts/auth/', views.sender_account_auth, name='sender_account_auth'),
    path('sender-accounts/verify/', views.verify_sender_code, name='verify_sender_code'),
    path('sender-accounts/disconnect/', views.disconnect_sender_account, name='disconnect_sender_account'),
    
    # Шаблоны сообщений
    path('templates/', views.message_templates, name='message_templates'),
    path('templates/create/', views.create_message_template, name='create_message_template'),
    path('templates/<int:template_id>/edit/', views.edit_message_template, name='edit_message_template'),
    path('templates/<int:template_id>/delete/', views.delete_message_template, name='delete_message_template'),
    path('templates/<int:template_id>/get/', views.get_message_template, name='get_message_template'),

    
    # API endpoints
    path('api/status/', views.api_status, name='api_status'),
]
