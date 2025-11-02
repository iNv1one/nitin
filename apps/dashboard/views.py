from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from apps.telegram_parser.models import KeywordGroup, MonitoredChat, ProcessedMessage, BotStatus, GlobalChat, UserChatSettings, RawMessage
from apps.users.models import User


@login_required
def dashboard(request):
    """
    Главная страница dashboard пользователя
    """
    user = request.user
    
    # Получаем статистику пользователя
    keyword_groups = KeywordGroup.objects.filter(user=user)
    monitored_chats = MonitoredChat.objects.filter(user=user, is_active=True)
    
    # Статистика за последние 7 дней
    week_ago = timezone.now() - timedelta(days=7)
    recent_messages = ProcessedMessage.objects.filter(
        user=user,
        processed_at__gte=week_ago
    )
    
    # Подготавливаем контекст
    context = {
        'user': user,
        'keyword_groups_count': keyword_groups.count(),
        'monitored_chats_count': monitored_chats.count(),
        'recent_messages_count': recent_messages.count(),
        'keyword_groups': keyword_groups[:5],  # Показываем только первые 5
        'monitored_chats': monitored_chats[:5],  # Показываем только первые 5
        'recent_messages': recent_messages.order_by('-processed_at')[:10],
        'subscription_plan': user.subscription_plan,
        'messages_this_month': user.messages_this_month,
        'message_limit': user.get_message_limit(),
        'bot_status': BotStatus.objects.first(),
    }
    
    return render(request, 'dashboard/dashboard.html', context)


@login_required
def keyword_groups(request):
    """
    Управление группами ключевых слов
    """
    user = request.user
    groups = KeywordGroup.objects.filter(user=user).order_by('-created_at')
    
    # Пагинация
    paginator = Paginator(groups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'user': user,
    }
    
    return render(request, 'dashboard/keyword_groups.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def create_keyword_group(request):
    """
    Создание новой группы ключевых слов
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        keywords = request.POST.get('keywords')
        ai_prompt = request.POST.get('ai_prompt', '')
        use_ai_filter = request.POST.get('use_ai_filter') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not keywords:
            messages.error(request, 'Название и ключевые слова обязательны для заполнения.')
            return render(request, 'dashboard/create_keyword_group.html')
        
        # Проверяем лимиты подписки
        current_groups = KeywordGroup.objects.filter(user=request.user).count()
        max_groups = request.user.get_keyword_groups_limit()
        
        if current_groups >= max_groups:
            messages.error(request, f'Достигнут лимит групп ключевых слов для вашего тарифа ({max_groups}).')
            return redirect('dashboard:keyword_groups')
        
        # Парсим ключевые слова (разделенные запятыми или переносами строк)
        keywords_list = [kw.strip() for kw in keywords.replace('\n', ',').split(',') if kw.strip()]
        
        # Создаем группу
        keyword_group = KeywordGroup.objects.create(
            user=request.user,
            name=name,
            keywords=keywords_list,
            ai_prompt=ai_prompt,
            use_ai_filter=use_ai_filter,
            is_active=is_active
        )
        
        messages.success(request, f'Группа ключевых слов "{name}" успешно создана.')
        return redirect('dashboard:keyword_groups')
    
    return render(request, 'dashboard/create_keyword_group.html')


@login_required
@require_http_methods(["GET", "POST"])
def edit_keyword_group(request, group_id):
    """
    Редактирование группы ключевых слов
    """
    group = get_object_or_404(KeywordGroup, id=group_id, user=request.user)
    
    if request.method == 'POST':
        name = request.POST.get('name', group.name)
        keywords = request.POST.get('keywords', '')
        ai_prompt = request.POST.get('ai_prompt', group.ai_prompt)
        use_ai_filter = request.POST.get('use_ai_filter') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        
        # Парсим ключевые слова так же как при создании
        if keywords:
            keywords_list = [kw.strip() for kw in keywords.replace('\n', ',').split(',') if kw.strip()]
        else:
            keywords_list = group.keywords
        
        group.name = name
        group.keywords = keywords_list
        group.ai_prompt = ai_prompt
        group.use_ai_filter = use_ai_filter
        group.is_active = is_active
        
        group.save()
        
        messages.success(request, f'Группа "{group.name}" успешно обновлена.')
        return redirect('dashboard:keyword_groups')
    
    context = {
        'group': group,
    }
    
    return render(request, 'dashboard/edit_keyword_group.html', context)


@login_required
@require_http_methods(["POST"])
def delete_keyword_group(request, group_id):
    """
    Удаление группы ключевых слов
    """
    group = get_object_or_404(KeywordGroup, id=group_id, user=request.user)
    group_name = group.name
    group.delete()
    
    messages.success(request, f'Группа "{group_name}" успешно удалена.')
    return redirect('dashboard:keyword_groups')


@login_required
def monitored_chats(request):
    """
    Управление отслеживаемыми чатами
    """
    user = request.user
    chats = MonitoredChat.objects.filter(user=user).order_by('-added_at')
    
    # Фильтрация
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    
    if status_filter == 'active':
        chats = chats.filter(is_active=True)
    elif status_filter == 'inactive':
        chats = chats.filter(is_active=False)
    
    if search_query:
        chats = chats.filter(
            Q(chat_name__icontains=search_query) |
            Q(chat_username__icontains=search_query)
        )
    
    # Пагинация
    paginator = Paginator(chats, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'user': user,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'dashboard/monitored_chats.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def add_monitored_chat(request):
    """
    Добавление нового отслеживаемого чата
    """
    if request.method == 'POST':
        chat_id = request.POST.get('chat_id')
        chat_name = request.POST.get('chat_name', '')
        chat_username = request.POST.get('chat_username', '')
        
        if not chat_id:
            messages.error(request, 'ID чата обязательно для заполнения.')
            return render(request, 'dashboard/add_monitored_chat.html')
        
        # Проверяем лимиты подписки
        current_chats = MonitoredChat.objects.filter(user=request.user, is_active=True).count()
        max_chats = request.user.get_chats_limit()
        
        if current_chats >= max_chats:
            messages.error(request, f'Достигнут лимит чатов для вашего тарифа ({max_chats}).')
            return redirect('dashboard:monitored_chats')
        
        # Проверяем, не добавлен ли уже этот чат
        if MonitoredChat.objects.filter(user=request.user, chat_id=chat_id).exists():
            messages.error(request, 'Этот чат уже добавлен в список отслеживаемых.')
            return render(request, 'dashboard/add_monitored_chat.html')
        
        # Создаем запись
        monitored_chat = MonitoredChat.objects.create(
            user=request.user,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_username=chat_username,
            is_active=True
        )
        
        messages.success(request, f'Чат "{chat_name or chat_id}" добавлен в отслеживаемые.')
        return redirect('dashboard:monitored_chats')
    
    return render(request, 'dashboard/add_monitored_chat.html')


@login_required
@require_http_methods(["POST"])
def toggle_chat_monitoring(request, chat_id):
    """
    Включение/выключение мониторинга чата
    """
    chat = get_object_or_404(MonitoredChat, id=chat_id, user=request.user)
    chat.is_active = not chat.is_active
    chat.save()
    
    status = "включен" if chat.is_active else "выключен"
    messages.success(request, f'Мониторинг чата "{chat.chat_name or chat.chat_id}" {status}.')
    
    return redirect('dashboard:monitored_chats')


@login_required
@require_http_methods(["POST"])
def delete_monitored_chat(request, chat_id):
    """
    Удаление отслеживаемого чата
    """
    chat = get_object_or_404(MonitoredChat, id=chat_id, user=request.user)
    chat_name = chat.chat_name or chat.chat_id
    chat.delete()
    
    messages.success(request, f'Чат "{chat_name}" удален из отслеживаемых.')
    return redirect('dashboard:monitored_chats')


@login_required
def processed_messages(request):
    """
    Просмотр обработанных сообщений (CRM)
    """
    user = request.user
    messages_qs = ProcessedMessage.objects.filter(user=user).order_by('-processed_at')
    
    # Фильтрация
    status_filter = request.GET.get('status')
    keyword_filter = request.GET.get('keyword')
    date_filter = request.GET.get('date')
    
    if status_filter:
        messages_qs = messages_qs.filter(crm_status=status_filter)
    
    if keyword_filter:
        messages_qs = messages_qs.filter(keyword_group__name__icontains=keyword_filter)
    
    if date_filter:
        if date_filter == 'today':
            messages_qs = messages_qs.filter(processed_at__date=timezone.now().date())
        elif date_filter == 'week':
            week_ago = timezone.now() - timedelta(days=7)
            messages_qs = messages_qs.filter(processed_at__gte=week_ago)
        elif date_filter == 'month':
            month_ago = timezone.now() - timedelta(days=30)
            messages_qs = messages_qs.filter(processed_at__gte=month_ago)
    
    # Пагинация
    paginator = Paginator(messages_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Статистика для фильтров
    status_counts = ProcessedMessage.objects.filter(user=user).values('crm_status').annotate(count=Count('id'))
    keyword_groups = KeywordGroup.objects.filter(user=user)
    
    context = {
        'page_obj': page_obj,
        'user': user,
        'status_filter': status_filter,
        'keyword_filter': keyword_filter,
        'date_filter': date_filter,
        'status_counts': status_counts,
        'keyword_groups': keyword_groups,
    }
    
    return render(request, 'dashboard/processed_messages.html', context)


@login_required
@require_http_methods(["POST"])
def update_message_status(request, message_id):
    """
    Обновление CRM статуса сообщения
    """
    message = get_object_or_404(ProcessedMessage, id=message_id, user=request.user)
    new_status = request.POST.get('status')
    
    if new_status in ['new', 'in_progress', 'completed', 'rejected']:
        message.crm_status = new_status
        message.save()
        
        messages.success(request, 'Статус сообщения обновлен.')
    else:
        messages.error(request, 'Неверный статус.')
    
    return redirect('dashboard:processed_messages')


@login_required
def settings(request):
    """
    Настройки пользователя
    """
    user = request.user
    
    if request.method == 'POST':
        # Обновляем настройки бота
        bot_token = request.POST.get('bot_token', '').strip()
        notification_chat_id = request.POST.get('notification_chat_id', '').strip()
        
        # Валидация токена бота (простая проверка)
        if bot_token and not bot_token.count(':') == 1:
            messages.error(request, 'Неверный формат токена Telegram бота.')
            return render(request, 'dashboard/settings.html', {'user': user})
        
        # Сохраняем токен (или пустую строку если удалили)
        user.telegram_bot_token = bot_token if bot_token else ''
        
        # Сохраняем chat_id (или None если удалили)
        if notification_chat_id:
            try:
                user.notification_chat_id = int(notification_chat_id)
            except (ValueError, TypeError):
                messages.error(request, 'Chat ID должен быть числом.')
                return render(request, 'dashboard/settings.html', {'user': user})
        else:
            user.notification_chat_id = None
        
        user.save()
        messages.success(request, 'Настройки успешно сохранены.')
        
        return redirect('dashboard:settings')
    
    context = {
        'user': user,
    }
    
    return render(request, 'dashboard/settings.html', context)


@login_required
def api_status(request):
    """
    API для получения статуса системы (AJAX)
    """
    bot_status = BotStatus.objects.first()
    
    data = {
        'is_healthy': bot_status.is_healthy if bot_status else False,
        'last_heartbeat': bot_status.last_heartbeat.isoformat() if bot_status and bot_status.last_heartbeat else None,
        'messages_processed_today': bot_status.messages_processed_today if bot_status else 0,
        'total_users': bot_status.total_users if bot_status else 0,
        'total_chats_monitored': bot_status.total_chats_monitored if bot_status else 0,
    }
    
    return JsonResponse(data)


@login_required
def global_chats(request):
    """
    Просмотр и управление глобальными чатами
    """
    user = request.user
    
    # Получаем все глобальные чаты
    all_chats = GlobalChat.objects.filter(is_active=True).order_by('name')
    
    # Получаем настройки пользователя для чатов
    user_settings = UserChatSettings.objects.filter(user=user).select_related('global_chat')
    user_settings_dict = {s.global_chat_id: s for s in user_settings}
    
    # Создаем список чатов с информацией о статусе для текущего пользователя
    chats_with_status = []
    for chat in all_chats:
        setting = user_settings_dict.get(chat.id)
        chats_with_status.append({
            'chat': chat,
            'is_enabled': setting.is_enabled if setting else True,  # По умолчанию включено
            'setting_id': setting.id if setting else None
        })
    
    # Pagination
    paginator = Paginator(chats_with_status, 50)  # 50 чатов на страницу
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Поиск
    search_query = request.GET.get('search', '').strip()
    if search_query:
        chats_with_status = [
            item for item in chats_with_status 
            if search_query.lower() in item['chat'].name.lower()
        ]
        paginator = Paginator(chats_with_status, 50)
        page_obj = paginator.get_page(page_number)
    
    # Статистика
    enabled_count = sum(1 for item in chats_with_status if item['is_enabled'])
    disabled_count = len(chats_with_status) - enabled_count
    
    context = {
        'page_obj': page_obj,
        'total_chats': all_chats.count(),
        'enabled_count': enabled_count,
        'disabled_count': disabled_count,
        'search_query': search_query,
    }
    
    return render(request, 'dashboard/global_chats.html', context)


@login_required
@require_http_methods(["POST"])
def toggle_global_chat(request, chat_id):
    """
    Включить/выключить глобальный чат для пользователя (AJAX)
    """
    try:
        global_chat = get_object_or_404(GlobalChat, id=chat_id, is_active=True)
        user = request.user
        
        # Получаем или создаем настройку
        setting, created = UserChatSettings.objects.get_or_create(
            user=user,
            global_chat=global_chat,
            defaults={'is_enabled': True}
        )
        
        if not created:
            # Переключаем статус
            setting.toggle()
        
        return JsonResponse({
            'success': True,
            'is_enabled': setting.is_enabled,
            'message': f'Чат {"включен" if setting.is_enabled else "выключен"}'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def toggle_all_global_chats(request):
    """
    Включить/выключить все глобальные чаты для пользователя (AJAX)
    """
    try:
        action = request.POST.get('action')  # 'enable' или 'disable'
        user = request.user
        
        if action not in ['enable', 'disable']:
            return JsonResponse({
                'success': False,
                'message': 'Неверное действие'
            }, status=400)
        
        is_enabled = (action == 'enable')
        
        # Получаем все активные глобальные чаты
        global_chats = GlobalChat.objects.filter(is_active=True)
        
        # Обновляем или создаем настройки для всех чатов
        for chat in global_chats:
            setting, created = UserChatSettings.objects.get_or_create(
                user=user,
                global_chat=chat,
                defaults={'is_enabled': is_enabled}
            )
            
            if not created and setting.is_enabled != is_enabled:
                setting.is_enabled = is_enabled
                if not is_enabled:
                    setting.disabled_at = timezone.now()
                setting.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Все чаты {"включены" if is_enabled else "выключены"}',
            'action': action
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required
@require_http_methods(['GET'])
def parser_control(request):
    bot_status, created = BotStatus.objects.get_or_create(bot_username='master_parser', defaults={'is_running': False})
    total_global_chats = GlobalChat.objects.filter(is_active=True).count()
    total_users = User.objects.filter(is_active=True).count()
    context = {'bot_status': bot_status, 'total_global_chats': total_global_chats, 'total_users': total_users}
    return render(request, 'dashboard/parser_control.html', context)

@login_required
@require_http_methods(['POST'])
def start_parser(request):
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Только администраторы могут управлять парсером'}, status=403)
    try:
        from apps.telegram_parser.tasks import start_telegram_parser
        bot_status = BotStatus.objects.first()
        if bot_status and bot_status.is_running:
            return JsonResponse({'success': False, 'message': 'Парсер уже запущен'})
        start_telegram_parser.delay()
        if not bot_status:
            bot_status = BotStatus.objects.create(bot_username='master_parser', is_running=True, started_at=timezone.now())
        else:
            bot_status.is_running = True
            bot_status.started_at = timezone.now()
            bot_status.save()
        return JsonResponse({'success': True, 'message': ' Парсер успешно запущен', 'started_at': bot_status.started_at.isoformat() if bot_status.started_at else None})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка при запуске: {str(e)}'}, status=500)

@login_required
@require_http_methods(['POST'])
def stop_parser(request):
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Только администраторы могут управлять парсером'}, status=403)
    try:
        from apps.telegram_parser.tasks import stop_telegram_parser
        bot_status = BotStatus.objects.first()
        if bot_status and not bot_status.is_running:
            return JsonResponse({'success': False, 'message': 'Парсер уже остановлен'})
        stop_telegram_parser.delay()
        if bot_status:
            bot_status.is_running = False
            bot_status.save()
        return JsonResponse({'success': True, 'message': ' Парсер остановлен'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка при остановке: {str(e)}'}, status=500)

@login_required
@require_http_methods(['GET'])
def parser_status(request):
    try:
        bot_status = BotStatus.objects.first()
        if not bot_status:
            return JsonResponse({'is_running': False, 'is_healthy': False, 'message': 'Статус не найден'})
        return JsonResponse({'is_running': bot_status.is_running, 'is_healthy': bot_status.is_healthy, 'uptime': bot_status.uptime, 'started_at': bot_status.started_at.isoformat() if bot_status.started_at else None, 'total_chats': bot_status.total_chats_monitored, 'total_users': bot_status.total_users, 'messages_today': bot_status.messages_processed_today, 'messages_total': bot_status.messages_processed_total, 'errors_count': bot_status.errors_count, 'last_error': bot_status.last_error if bot_status.last_error else None, 'last_heartbeat': bot_status.last_heartbeat.isoformat() if bot_status.last_heartbeat else None})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def raw_messages(request):
    """Просмотр всех сырых сообщений, полученных парсером"""
    messages_list = RawMessage.objects.all().order_by('-received_at')
    
    # Пагинация
    paginator = Paginator(messages_list, 50)  # 50 сообщений на страницу
    page_number = request.GET.get('page')
    messages_page = paginator.get_page(page_number)
    
    context = {
        'raw_messages': messages_page,  # Переименовали с 'messages' на 'raw_messages'
        'total_count': messages_list.count(),
    }
    
    return render(request, 'dashboard/raw_messages.html', context)
