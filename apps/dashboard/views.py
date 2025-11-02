from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
import json
import logging

from apps.telegram_parser.models import KeywordGroup, MonitoredChat, ProcessedMessage, BotStatus, GlobalChat, UserChatSettings, RawMessage
from apps.users.models import User

logger = logging.getLogger(__name__)


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
    Создание заявки на добавление нового чата
    """
    if request.method == 'POST':
        chat_link = request.POST.get('chat_link', '').strip()
        chat_description = request.POST.get('chat_description', '').strip()
        
        if not chat_link:
            messages.error(request, 'Ссылка на чат обязательна для заполнения.')
            return render(request, 'dashboard/add_monitored_chat.html')
        
        # Импортируем ChatRequest
        from apps.telegram_parser.models import ChatRequest
        import telebot
        
        # Создаем заявку
        chat_request = ChatRequest.objects.create(
            user=request.user,
            chat_link=chat_link,
            chat_description=chat_description,
            status='pending'
        )
        
        # Отправляем уведомление администратору
        try:
            bot = telebot.TeleBot('7193620780:AAEM_QlyHeGMFbppRp2Uw7ObBrL73lEjkL0')
            admin_message = f"""
🆕 <b>Новая заявка на добавление чата</b>

👤 <b>Пользователь:</b> {request.user.username} (ID: {request.user.id})
📧 <b>Email:</b> {request.user.email}

🔗 <b>Ссылка на чат:</b> {chat_link}

📝 <b>Описание:</b>
{chat_description if chat_description else 'Не указано'}

🆔 <b>ID заявки:</b> {chat_request.id}
"""
            bot.send_message(911873673, admin_message, parse_mode='HTML')
        except Exception as e:
            print(f"Error sending notification to admin: {e}")
        
        messages.success(request, 'Заявка на добавление чата отправлена! Мы обработаем её в ближайшее время.')
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
    progress_filter = request.GET.get('progress')
    
    if status_filter:
        messages_qs = messages_qs.filter(quality_status=status_filter)
    
    if progress_filter:
        if progress_filter == 'dialog':
            messages_qs = messages_qs.filter(dialog_started=True)
        elif progress_filter == 'sale':
            messages_qs = messages_qs.filter(sale_made=True)
    
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
    status_counts = ProcessedMessage.objects.filter(user=user).values('quality_status').annotate(count=Count('id'))
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
    Обновление статуса сообщения
    """
    message = get_object_or_404(ProcessedMessage, id=message_id, user=request.user)
    
    # Обновление quality_status
    quality_status = request.POST.get('quality_status')
    if quality_status in ['none', 'unqualified', 'qualified', 'spam']:
        message.quality_status = quality_status
    
    # Обновление boolean флагов
    dialog_started = request.POST.get('dialog_started')
    if dialog_started is not None:
        message.dialog_started = dialog_started == 'true'
    
    sale_made = request.POST.get('sale_made')
    if sale_made is not None:
        message.sale_made = sale_made == 'true'
    
    # Обновление заметок
    notes = request.POST.get('notes')
    if notes is not None:
        message.notes = notes
    
    message.save()
    messages.success(request, 'Статус сообщения обновлен.')
    
    return redirect('dashboard:processed_messages')


@login_required
@require_http_methods(["POST"])
def ajax_update_message_status(request, message_id):
    """
    AJAX обновление статуса сообщения с синхронизацией в Telegram
    """
    try:
        message = get_object_or_404(ProcessedMessage, id=message_id, user=request.user)
        
        # Обновление quality_status
        quality_status = request.POST.get('quality_status')
        if quality_status in ['none', 'unqualified', 'qualified', 'spam']:
            message.quality_status = quality_status
        
        # Обновление boolean флагов
        dialog_started = request.POST.get('dialog_started')
        if dialog_started is not None:
            message.dialog_started = dialog_started == 'true'
        
        sale_made = request.POST.get('sale_made')
        if sale_made is not None:
            message.sale_made = sale_made == 'true'
        
        message.save()
        
        # Обновляем сообщение в Telegram, если есть telegram_message_id
        if message.telegram_message_id and request.user.telegram_bot_token:
            try:
                import telebot
                from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                
                bot = telebot.TeleBot(request.user.telegram_bot_token)
                
                # Формируем клавиатуру с обновленными статусами
                keyboard = InlineKeyboardMarkup(row_width=3)
                
                # Первый ряд - качество
                btn_unqualified = InlineKeyboardButton(
                    f"{'✅ ' if message.quality_status == 'unqualified' else ''}Неквал",
                    callback_data=f"unqualified:{message.id}"
                )
                btn_qualified = InlineKeyboardButton(
                    f"{'✅ ' if message.quality_status == 'qualified' else ''}Квал",
                    callback_data=f"qualified:{message.id}"
                )
                btn_spam = InlineKeyboardButton(
                    f"{'✅ ' if message.quality_status == 'spam' else ''}Спам",
                    callback_data=f"spam:{message.id}"
                )
                
                # Второй ряд - прогресс
                btn_dialog = InlineKeyboardButton(
                    f"{'✅ ' if message.dialog_started else ''}Начали диалог",
                    callback_data=f"dialog_started:{message.id}"
                )
                btn_sale = InlineKeyboardButton(
                    f"{'✅ ' if message.sale_made else ''}Есть продажа",
                    callback_data=f"sale_made:{message.id}"
                )
                
                keyboard.add(btn_unqualified, btn_qualified, btn_spam)
                keyboard.add(btn_dialog, btn_sale)
                
                # Обновляем сообщение
                bot.edit_message_reply_markup(
                    chat_id=request.user.notification_chat_id,
                    message_id=message.telegram_message_id,
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"Error updating Telegram message: {e}")
        
        return JsonResponse({'success': True})
    except Exception as e:
        print(f"Error in ajax_update_message_status: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


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
    messages_list = RawMessage.objects.all()
    
    # Фильтрация по чату
    chat_id = request.GET.get('chat_id')
    if chat_id:
        messages_list = messages_list.filter(chat_id=chat_id)
    
    # Фильтрация по названию чата
    chat_name = request.GET.get('chat_name')
    if chat_name:
        messages_list = messages_list.filter(chat_name__icontains=chat_name)
    
    # Фильтрация по отправителю
    sender = request.GET.get('sender')
    if sender:
        messages_list = messages_list.filter(
            Q(sender_name__icontains=sender) | Q(sender_username__icontains=sender)
        )
    
    # Фильтрация по тексту
    search_text = request.GET.get('search_text')
    if search_text:
        messages_list = messages_list.filter(message_text__icontains=search_text)
    
    # Фильтрация по дате
    date_from = request.GET.get('date_from')
    if date_from:
        try:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            messages_list = messages_list.filter(message_date__gte=date_from_obj)
        except ValueError:
            pass
    
    date_to = request.GET.get('date_to')
    if date_to:
        try:
            from datetime import datetime
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Добавляем 1 день для включения всего дня
            date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
            messages_list = messages_list.filter(message_date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Фильтр по типу (канал/чат)
    is_channel = request.GET.get('is_channel')
    if is_channel == 'true':
        messages_list = messages_list.filter(is_channel_post=True)
    elif is_channel == 'false':
        messages_list = messages_list.filter(is_channel_post=False)
    
    # Сортировка
    messages_list = messages_list.order_by('-received_at')
    
    # Получаем список уникальных чатов для фильтра
    unique_chats = RawMessage.objects.values('chat_id', 'chat_name').distinct().order_by('chat_name')
    
    # Пагинация
    paginator = Paginator(messages_list, 50)  # 50 сообщений на страницу
    page_number = request.GET.get('page')
    messages_page = paginator.get_page(page_number)
    
    context = {
        'raw_messages': messages_page,
        'total_count': messages_list.count(),
        'unique_chats': unique_chats,
        'filters': {
            'chat_id': chat_id or '',
            'chat_name': chat_name or '',
            'sender': sender or '',
            'search_text': search_text or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
            'is_channel': is_channel or '',
        }
    }
    
    return render(request, 'dashboard/raw_messages.html', context)


@login_required
def statistics(request):
    """Страница статистики"""
    user = request.user
    
    # Получаем период из GET параметров (по умолчанию - неделя)
    period = request.GET.get('period', 'week')
    
    # Определяем временные рамки
    now = timezone.now()
    if period == 'day':
        start_date = now - timedelta(days=1)
        period_name = 'За последний день'
    elif period == 'week':
        start_date = now - timedelta(days=7)
        period_name = 'За последнюю неделю'
    elif period == 'month':
        start_date = now - timedelta(days=30)
        period_name = 'За последний месяц'
    else:
        start_date = now - timedelta(days=7)
        period_name = 'За последнюю неделю'
    
    # Получаем все сообщения пользователя за период
    messages = ProcessedMessage.objects.filter(
        user=user,
        processed_at__gte=start_date
    )
    
    # Общая статистика
    total_messages = messages.count()
    
    # Статистика по AI фильтру
    ai_approved = messages.exclude(ai_result='').exclude(ai_result__icontains='error').filter(
        Q(ai_result__icontains='YES') | Q(ai_result__icontains='Y')
    ).count()
    
    ai_rejected_count = messages.exclude(ai_result='').exclude(ai_result__icontains='error').count() - ai_approved
    
    # Статистика по статусам quality_status
    status_stats = {
        'none': messages.filter(quality_status='none').count(),
        'unqualified': messages.filter(quality_status='unqualified').count(),
        'qualified': messages.filter(quality_status='qualified').count(),
        'spam': messages.filter(quality_status='spam').count(),
    }
    
    # Статистика по дополнительным флагам
    dialog_started = messages.filter(dialog_started=True).count()
    sale_made = messages.filter(sale_made=True).count()
    
    # Статистика по группам ключевых слов
    keyword_group_stats = messages.values('keyword_group__name').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Статистика по дням (для графика)
    daily_stats = []
    for i in range(7 if period == 'week' else (1 if period == 'day' else 30)):
        day_start = now - timedelta(days=i)
        day_end = day_start - timedelta(days=1)
        
        day_messages = messages.filter(
            processed_at__gte=day_end,
            processed_at__lt=day_start
        ).count()
        
        daily_stats.insert(0, {
            'date': day_start.strftime('%d.%m'),
            'count': day_messages
        })
    
    context = {
        'period': period,
        'period_name': period_name,
        'total_messages': total_messages,
        'ai_approved': ai_approved,
        'ai_rejected': ai_rejected_count,
        'status_stats': status_stats,
        'dialog_started': dialog_started,
        'sale_made': sale_made,
        'keyword_group_stats': keyword_group_stats,
        'daily_stats': daily_stats,
        'daily_stats_json': json.dumps(daily_stats),  # Для JavaScript
    }
    
    return render(request, 'dashboard/statistics.html', context)


@login_required
@require_http_methods(['POST'])
def send_message_to_lead(request, message_id):
    """Отправка сообщения лиду через sender-аккаунт"""
    import asyncio
    from apps.telegram_parser.sender_client import SenderClient
    from django.utils import timezone
    
    try:
        # Получаем сообщение
        message = get_object_or_404(ProcessedMessage, id=message_id, user=request.user)
        
        # Проверяем, настроен ли sender-аккаунт
        if not request.user.has_sender_account:
            return JsonResponse({
                'success': False,
                'message': 'Sender-аккаунт не настроен. Настройте его в настройках профиля.'
            }, status=400)
        
        # Проверяем, есть ли sender_id у лида
        if not message.sender_id:
            return JsonResponse({
                'success': False,
                'message': 'У этого сообщения нет ID отправителя'
            }, status=400)
        
        # Получаем текст сообщения
        custom_text = request.POST.get('message_text', '').strip()
        
        if not custom_text:
            # Используем шаблон по умолчанию
            template = request.user.default_message_template
            if not template:
                return JsonResponse({
                    'success': False,
                    'message': 'Введите текст сообщения или настройте шаблон по умолчанию'
                }, status=400)
            
            # Заменяем переменные в шаблоне
            message_text = template.replace('{name}', message.sender_name or 'там')
        else:
            message_text = custom_text
        
        # Создаем sender client
        sender = SenderClient(
            api_id=request.user.sender_api_id,
            api_hash=request.user.sender_api_hash,
            session_string=request.user.sender_session_string
        )
        
        # Отправляем сообщение асинхронно
        async def send():
            await sender.connect()
            success = await sender.send_message(message.sender_id, message_text)
            await sender.disconnect()
            return success
        
        # Запускаем в event loop
        success = asyncio.run(send())
        
        if success:
            # Обновляем запись
            message.message_sent = True
            message.message_sent_at = timezone.now()
            message.sent_message_text = message_text
            message.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Сообщение успешно отправлено!'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Ошибка при отправке сообщения. Проверьте логи.'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error sending message to lead: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Ошибка: {str(e)}'
        }, status=500)
