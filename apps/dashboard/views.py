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

from apps.telegram_parser.models import KeywordGroup, MonitoredChat, ProcessedMessage, BotStatus, GlobalChat, UserChatSettings, RawMessage, MessageTemplate, RejectedMessage, SentMessageHistory
from apps.users.models import User
logger = logging.getLogger(__name__)


@login_required
def statistics(request):
    """
    Главная страница - показываем статистику
    """
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
    
    # Статистика по обработке сообщений
    # Одобренные AI (или без AI проверки)
    ai_approved = messages.filter(ai_approved=True).count()
    
    # Отклоненные AI
    ai_rejected_count = messages.filter(ai_approved=False).count()
    
    # Сообщения без AI проверки (где AI фильтр не был включен)
    messages_without_ai = messages.filter(ai_result='').count()
    
    # Сообщения, после которых написали пользователю через sender-аккаунт
    sender_contacted = messages.filter(message_sent=True).count()
    
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
    
    # Детальную статистику загружаем через AJAX - убираем из основной загрузки
    # detailed_group_stats и detailed_chat_stats будут загружены асинхронно
    
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
        'sender_contacted': sender_contacted,
        'messages_without_ai': messages_without_ai,
        'status_stats': status_stats,
        'dialog_started': dialog_started,
        'sale_made': sale_made,
        'daily_stats': daily_stats,
        'daily_stats_json': json.dumps(daily_stats),  # Для JavaScript
    }
    
    return render(request, 'dashboard/statistics.html', context)


@login_required
def keyword_groups(request):
    """
    Управление группами ключевых слов
    """
    user = request.user
    groups = KeywordGroup.objects.filter(user=user).order_by('-created_at')
    
    # Пагинация для групп
    paginator = Paginator(groups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Получаем шаблоны сообщений пользователя
    from apps.telegram_parser.models import MessageTemplate
    templates = MessageTemplate.objects.filter(user=user).order_by('-is_default', 'name')
    
    context = {
        'page_obj': page_obj,
        'templates': templates,
        'user': user,
    }
    
    return render(request, 'dashboard/keyword_groups.html', context)


@login_required
@require_http_methods(["GET", "POST"])
@login_required
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
        notification_chat_id = request.POST.get('notification_chat_id', '').strip()
        
        if not name or not keywords:
            error_msg = 'Название и ключевые слова обязательны для заполнения.'
            
            # AJAX запрос
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            
            messages.error(request, error_msg)
            return render(request, 'dashboard/create_keyword_group.html')
        
        # Проверяем лимиты подписки
        current_groups = KeywordGroup.objects.filter(user=request.user).count()
        max_groups = request.user.get_keyword_groups_limit()
        
        if current_groups >= max_groups:
            error_msg = f'Достигнут лимит групп ключевых слов для вашего тарифа ({max_groups}).'
            
            # AJAX запрос
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            
            messages.error(request, error_msg)
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
            is_active=is_active,
            notification_chat_id=int(notification_chat_id) if notification_chat_id else None
        )
        
        success_msg = f'Группа ключевых слов "{name}" успешно создана.'
        
        # AJAX запрос
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': success_msg, 'group_id': keyword_group.id})
        
        messages.success(request, success_msg)
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
        notification_chat_id = request.POST.get('notification_chat_id', '').strip()
        
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
        group.notification_chat_id = int(notification_chat_id) if notification_chat_id else None
        
        group.save()
        
        # Проверяем, является ли это AJAX запросом
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f'Группа "{group.name}" успешно обновлена.'})
        
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
            error_msg = 'Ссылка на чат обязательна для заполнения.'
            
            # AJAX запрос
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            
            messages.error(request, error_msg)
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
            bot = telebot.TeleBot(settings.TELEGRAM_NOTIFICATION_BOT_TOKEN)
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
        
        success_msg = 'Заявка на добавление чата отправлена! Мы обработаем её в ближайшее время.'
        
        # AJAX запрос
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': success_msg})
        
        messages.success(request, success_msg)
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
    Просмотр всех сообщений (CRM)
    """
    user = request.user
    
    # Фильтры
    ai_status_filter = request.GET.get('ai_status')  # all, approved, rejected
    status_filter = request.GET.get('status')
    keyword_filter = request.GET.get('keyword')
    date_filter = request.GET.get('date')
    progress_filter = request.GET.get('progress')
    
    # Получаем все сообщения
    messages_qs = ProcessedMessage.objects.filter(user=user)
    
    # Фильтр по статусу AI
    if ai_status_filter == 'approved':
        messages_qs = messages_qs.filter(ai_approved=True)
    elif ai_status_filter == 'rejected':
        messages_qs = messages_qs.filter(ai_approved=False)
    
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
    
    # Сортируем по дате и используем select_related для оптимизации запросов
    messages_qs = messages_qs.select_related('keyword_group', 'global_chat').order_by('-processed_at')
    
    # Подсчитываем количество (только для отображения, не для всех записей)
    total_count = messages_qs.count()
    approved_count = ProcessedMessage.objects.filter(user=user, ai_approved=True).count()
    rejected_count = ProcessedMessage.objects.filter(user=user, ai_approved=False).count()
    
    # Пагинация ПЕРЕД преобразованием - берем только нужную страницу
    paginator = Paginator(messages_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Преобразуем в список словарей только для текущей страницы (20 записей вместо 600+)
    all_messages = []
    for msg in page_obj:
        all_messages.append({
            'type': 'processed',
            'id': msg.id,
            'message_id': msg.message_id,
            'chat_id': msg.chat_id,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'sender_username': msg.sender_username,
            'message_text': msg.message_text,
            'message_link': msg.message_link,
            'matched_keywords': msg.matched_keywords,
            'ai_approved': msg.ai_approved,
            'ai_result': msg.ai_result,
            'ai_score': msg.ai_score,
            'quality_status': msg.quality_status,
            'dialog_started': msg.dialog_started,
            'sale_made': msg.sale_made,
            'message_sent': msg.message_sent,
            'notes': msg.notes,
            'global_chat': msg.global_chat,
            'keyword_group': msg.keyword_group,
            'date': msg.processed_at,
            'original_object': msg,
        })
    
    # Создаем новый page_obj с преобразованными данными
    from django.core.paginator import Page
    page_obj = Page(all_messages, page_obj.number, paginator)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Статистика для фильтров
    status_counts = ProcessedMessage.objects.filter(user=user).values('quality_status').annotate(count=Count('id'))
    keyword_groups = KeywordGroup.objects.filter(user=user)
    
    context = {
        'page_obj': page_obj,
        'user': user,
        'total_count': total_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'ai_status_filter': ai_status_filter,
        'status_filter': status_filter,
        'keyword_filter': keyword_filter,
        'date_filter': date_filter,
        'progress_filter': progress_filter,
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
    
    return JsonResponse({'success': True})


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
        if message.telegram_message_id:
            try:
                import telebot
                from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                
                bot = telebot.TeleBot(settings.TELEGRAM_NOTIFICATION_BOT_TOKEN)
                
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
    
    context = {
        'user': user,
    }
    
    return render(request, 'dashboard/settings.html', context)


@login_required
def sent_messages(request):
    """
    История отправленных сообщений через sender-аккаунт
    """
    user = request.user
    messages_qs = SentMessageHistory.objects.filter(user=user).order_by('-sent_at')
    
    # Фильтрация
    status_filter = request.GET.get('status')
    sender_account_filter = request.GET.get('sender_account')
    recipient_filter = request.GET.get('recipient')
    date_filter = request.GET.get('date')
    
    if status_filter:
        if status_filter == 'read':
            messages_qs = messages_qs.filter(is_read=True)
        elif status_filter == 'unread':
            messages_qs = messages_qs.filter(is_read=False)
        elif status_filter == 'replied':
            messages_qs = messages_qs.filter(is_replied=True)
        elif status_filter == 'not_replied':
            messages_qs = messages_qs.filter(is_replied=False)
    
    if sender_account_filter:
        messages_qs = messages_qs.filter(sent_from_account__icontains=sender_account_filter)
    
    if recipient_filter:
        messages_qs = messages_qs.filter(
            Q(recipient_name__icontains=recipient_filter) |
            Q(recipient_username__icontains=recipient_filter)
        )
    
    if date_filter:
        if date_filter == 'today':
            messages_qs = messages_qs.filter(sent_at__date=timezone.now().date())
        elif date_filter == 'week':
            week_ago = timezone.now() - timedelta(days=7)
            messages_qs = messages_qs.filter(sent_at__gte=week_ago)
        elif date_filter == 'month':
            month_ago = timezone.now() - timedelta(days=30)
            messages_qs = messages_qs.filter(sent_at__gte=month_ago)
    
    # Статистика
    total_count = messages_qs.count()
    read_count = messages_qs.filter(is_read=True).count()
    replied_count = messages_qs.filter(is_replied=True).count()
    
    read_percentage = (read_count / total_count * 100) if total_count > 0 else 0
    replied_percentage = (replied_count / total_count * 100) if total_count > 0 else 0
    
    # Пагинация
    paginator = Paginator(messages_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Получаем список sender-аккаунтов для фильтра
    sender_accounts = SentMessageHistory.objects.filter(user=user).values_list('sent_from_account', flat=True).distinct()
    
    context = {
        'page_obj': page_obj,
        'user': user,
        'total_count': total_count,
        'read_count': read_count,
        'replied_count': replied_count,
        'read_percentage': round(read_percentage, 1),
        'replied_percentage': round(replied_percentage, 1),
        'status_filter': status_filter,
        'sender_account_filter': sender_account_filter,
        'recipient_filter': recipient_filter,
        'date_filter': date_filter,
        'sender_accounts': sender_accounts,
    }
    
    return render(request, 'dashboard/sent_messages.html', context)


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


@login_required
def statistics_groups_ajax(request):
    """AJAX загрузка статистики по группам"""
    user = request.user
    period = request.GET.get('period', 'week')
    
    # Определяем временные рамки
    now = timezone.now()
    if period == 'day':
        start_date = now - timedelta(days=1)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = now - timedelta(days=7)
    
    # Получаем сообщения за период
    messages = ProcessedMessage.objects.filter(user=user, processed_at__gte=start_date)
    
    # Детальная статистика по группам ключевых слов
    detailed_group_stats = []
    user_groups = user.keyword_groups.all()
    
    for group in user_groups:
        group_messages = messages.filter(keyword_group=group)
        total_count = group_messages.count()
        
        if total_count > 0:
            qualified_count = group_messages.filter(quality_status='qualified').count()
            unqualified_count = group_messages.filter(quality_status='unqualified').count()
            spam_count = group_messages.filter(quality_status='spam').count()
            dialog_count = group_messages.filter(dialog_started=True).count()
            sale_count = group_messages.filter(sale_made=True).count()
            
            efficiency = (qualified_count / total_count * 100) if total_count > 0 else 0
            
            detailed_group_stats.append({
                'name': group.name,
                'total': total_count,
                'qualified': qualified_count,
                'unqualified': unqualified_count,
                'spam': spam_count,
                'dialog': dialog_count,
                'sale': sale_count,
                'efficiency': round(efficiency, 1),
            })
    
    detailed_group_stats.sort(key=lambda x: x['total'], reverse=True)
    
    return JsonResponse({'stats': detailed_group_stats})


@login_required
def statistics_chats_ajax(request):
    """AJAX загрузка статистики по чатам"""
    user = request.user
    period = request.GET.get('period', 'week')
    
    # Определяем временные рамки
    now = timezone.now()
    if period == 'day':
        start_date = now - timedelta(days=1)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = now - timedelta(days=7)
    
    # Получаем сообщения за период
    messages = ProcessedMessage.objects.filter(user=user, processed_at__gte=start_date)
    
    # Детальная статистика по чатам
    detailed_chat_stats = []
    user_chat_settings = UserChatSettings.objects.filter(user=user, is_enabled=True).select_related('global_chat')
    
    for setting in user_chat_settings:
        chat = setting.global_chat
        chat_messages = messages.filter(global_chat=chat)
        total_count = chat_messages.count()
        
        if total_count > 0:
            qualified_count = chat_messages.filter(quality_status='qualified').count()
            unqualified_count = chat_messages.filter(quality_status='unqualified').count()
            spam_count = chat_messages.filter(quality_status='spam').count()
            dialog_count = chat_messages.filter(dialog_started=True).count()
            sale_count = chat_messages.filter(sale_made=True).count()
            
            efficiency = (qualified_count / total_count * 100) if total_count > 0 else 0
            
            detailed_chat_stats.append({
                'name': chat.name,
                'total': total_count,
                'qualified': qualified_count,
                'unqualified': unqualified_count,
                'spam': spam_count,
                'dialog': dialog_count,
                'sale': sale_count,
                'efficiency': round(efficiency, 1),
            })
    
    detailed_chat_stats.sort(key=lambda x: x['total'], reverse=True)
    
    return JsonResponse({'stats': detailed_chat_stats})


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
            message_text = template
        else:
            message_text = custom_text
        
        # Заменяем переменные в тексте сообщения
        message_text = message_text.replace('{name}', message.sender_name or 'там')
        message_text = message_text.replace('{username}', f"@{message.sender_username}" if message.sender_username else 'там')
        message_text = message_text.replace('{chat_name}', message.global_chat.name if message.global_chat else 'общего чата')
        message_text = message_text.replace('{message_text}', (message.message_text[:100] + '...') if len(message.message_text) > 100 else message.message_text)
        
        # Создаем sender client
        sender = SenderClient(
            api_id=request.user.sender_api_id,
            api_hash=request.user.sender_api_hash,
            session_string=request.user.sender_session_string
        )
        
        # Отправляем сообщение асинхронно
        async def send():
            await sender.connect()
            
            # Используем username если есть, иначе ID
            if message.sender_username:
                success = await sender.send_message_by_username(message.sender_username, message_text)
            elif message.sender_id:
                success = await sender.send_message(message.sender_id, message_text)
            else:
                return False
            
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


@login_required
def sender_accounts(request):
    """Управление sender-аккаунтами (только для админов)"""
    from apps.telegram_parser.models import SenderAccount
    
    # Проверка прав доступа
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен. Только для администраторов.')
        return redirect('dashboard:dashboard')
    
    # Получаем ВСЕ sender-аккаунты (общие для всех пользователей)
    accounts = SenderAccount.objects.all().order_by('-created_at')
    
    context = {
        'user': request.user,
        'sender_accounts': accounts,
    }
    
    return render(request, 'dashboard/sender_accounts.html', context)


@login_required
@require_http_methods(['POST'])
def setup_sender_account(request):
    """Настройка sender-аккаунта"""
    import asyncio
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    
    try:
        api_id = request.POST.get('api_id')
        api_hash = request.POST.get('api_hash')
        phone = request.POST.get('phone')
        
        if not all([api_id, api_hash, phone]):
            messages.error(request, 'Заполните все поля')
            return redirect('dashboard:sender_accounts')
        
        # Сохраняем данные
        user = request.user
        user.sender_api_id = int(api_id)
        user.sender_api_hash = api_hash
        user.sender_phone = phone
        user.save()
        
        # Отправляем код подтверждения
        async def send_code():
            client = TelegramClient(StringSession(), int(api_id), api_hash)
            try:
                await client.connect()
                phone_code_request = await client.send_code_request(phone)
                # Сохраняем промежуточную сессию и phone_code_hash для последующей авторизации
                session_string = client.session.save()
                phone_code_hash = phone_code_request.phone_code_hash
                return True, (session_string, phone_code_hash)
            except Exception as e:
                logger.error(f"Error sending code: {e}")
                return False, str(e)
            finally:
                await client.disconnect()
        
        # Выполняем отправку кода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, result = loop.run_until_complete(send_code())
        loop.close()
        
        if success:
            # Сохраняем промежуточную сессию и phone_code_hash
            session_string, phone_code_hash = result
            user.sender_session_string = session_string
            user.sender_phone_code_hash = phone_code_hash
            user.save()
            logger.info(f"Code sent and temp session saved for user {user.id}")
            messages.success(request, f'Код подтверждения отправлен на {phone} в приложении Telegram!')
            return redirect('dashboard:sender_account_auth')
        else:
            messages.error(request, f'Ошибка отправки кода: {result}')
            return redirect('dashboard:sender_accounts')
        
    except Exception as e:
        logger.error(f"Error setting up sender account: {e}")
        messages.error(request, f'Ошибка: {str(e)}')
        return redirect('dashboard:sender_accounts')


@login_required
def sender_account_auth(request):
    """Страница авторизации sender-аккаунта"""
    # Проверяем что данные аккаунта сохранены
    if not request.user.sender_api_id or not request.user.sender_phone:
        messages.error(request, 'Сначала нужно ввести данные аккаунта')
        return redirect('dashboard:sender_accounts')
    
    return render(request, 'dashboard/sender_account_auth.html')


@login_required
@require_http_methods(['POST'])
def verify_sender_code(request):
    """Проверка кода подтверждения и завершение авторизации"""
    import asyncio
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
    
    user = request.user
    code = request.POST.get('code', '').strip()
    password = request.POST.get('password', '').strip()
    
    # Убираем все нецифровые символы из кода (пробелы, дефисы и т.д.)
    code = ''.join(filter(str.isdigit, code))
    
    logger.info(f"Verify sender code started for user {user.id}, phone {user.sender_phone}")
    
    if not code:
        messages.error(request, 'Введите код подтверждения')
        return redirect('dashboard:sender_account_auth')
    
    logger.info(f"Code received: {code[:2]}*** (length: {len(code)})")
    
    async def authorize_account():
        """Асинхронная авторизация"""
        # Используем временную сессию для авторизации
        # После успешной авторизации сохраним session string
        temp_session = user.sender_session_string if user.sender_session_string else ''
        
        client = TelegramClient(
            StringSession(temp_session),
            user.sender_api_id,
            user.sender_api_hash
        )
        
        try:
            logger.info("Connecting to Telegram...")
            await client.connect()
            
            logger.info("Checking authorization status...")
            is_authorized = await client.is_user_authorized()
            logger.info(f"Already authorized: {is_authorized}")
            
            # Если уже авторизованы - просто сохраняем сессию
            if is_authorized:
                logger.info("Already authorized, saving session")
                session_string = client.session.save()
                return True, session_string
            
            # Пытаемся авторизоваться с кодом
            try:
                logger.info("Attempting sign in with code...")
                # Используем сохраненный phone_code_hash
                await client.sign_in(user.sender_phone, code, phone_code_hash=user.sender_phone_code_hash)
                logger.info("Sign in successful!")
            except SessionPasswordNeededError:
                logger.info("2FA password required")
                # Требуется 2FA пароль
                if not password:
                    logger.warning("2FA required but no password provided")
                    return False, "Требуется пароль двухфакторной аутентификации. Поставьте галочку '2FA' и введите пароль."
                logger.info("Attempting sign in with 2FA password...")
                await client.sign_in(password=password)
                logger.info("2FA sign in successful!")
            except PhoneCodeInvalidError as e:
                logger.warning(f"Invalid phone code: {e}")
                return False, "Неверный код подтверждения. Проверьте код и попробуйте снова."
            except Exception as e:
                logger.error(f"Sign in error: {type(e).__name__}: {e}")
                return False, f"Ошибка авторизации: {str(e)}"
            
            # Проверяем авторизацию
            logger.info("Checking final authorization status...")
            if await client.is_user_authorized():
                # Сохраняем session string
                session_string = client.session.save()
                logger.info(f"Authorization successful! Session string length: {len(session_string)}")
                return True, session_string
            else:
                logger.error("Authorization check failed after sign in")
                return False, "Не удалось завершить авторизацию"
                
        except Exception as e:
            logger.error(f"Error during authorization: {type(e).__name__}: {e}", exc_info=True)
            return False, str(e)
        finally:
            await client.disconnect()
            logger.info("Client disconnected")
    
    # Выполняем авторизацию
    try:
        logger.info("Starting authorization process...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, result = loop.run_until_complete(authorize_account())
        loop.close()
        logger.info(f"Authorization completed: success={success}")
        
        if success:
            # Сохраняем session string
            user.sender_session_string = result
            user.save()
            logger.info(f"Session string saved for user {user.id}")
            
            messages.success(request, 'Sender-аккаунт успешно подключен! Теперь вы можете отправлять сообщения.')
            return redirect('dashboard:sender_accounts')
        else:
            logger.warning(f"Authorization failed: {result}")
            messages.error(request, f'Ошибка авторизации: {result}')
            return redirect('dashboard:sender_account_auth')
            
    except Exception as e:
        logger.error(f"Error in verify_sender_code: {type(e).__name__}: {e}", exc_info=True)
        messages.error(request, f'Ошибка: {str(e)}')
        return redirect('dashboard:sender_account_auth')


@login_required
@require_http_methods(['POST'])
def disconnect_sender_account(request):
    """Отключение sender-аккаунта"""
    user = request.user
    user.sender_api_id = None
    user.sender_api_hash = ''
    user.sender_phone = ''
    user.sender_session_string = ''
    user.save()
    
    messages.success(request, 'Sender-аккаунт отключен')
    return redirect('dashboard:sender_accounts')


@login_required
@require_http_methods(['POST'])
def create_sender_account(request):
    """Создание нового sender-аккаунта (только для админов)"""
    from apps.telegram_parser.models import SenderAccount
    
    # Проверка прав доступа
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'error': 'Доступ запрещен'
        }, status=403)
    
    try:
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        api_id = request.POST.get('api_id', '').strip()
        api_hash = request.POST.get('api_hash', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        # Получаем настройки отправки (с дефолтными значениями)
        initial_delay_min = int(request.POST.get('initial_delay_min', 30))
        initial_delay_max = int(request.POST.get('initial_delay_max', 60))
        message_delay_min = int(request.POST.get('message_delay_min', 60))
        message_delay_max = int(request.POST.get('message_delay_max', 180))
        daily_limit = int(request.POST.get('daily_limit', 30))
        
        if not all([name, phone, api_id, api_hash]):
            return JsonResponse({
                'success': False,
                'error': 'Заполните все обязательные поля'
            }, status=400)
        
        # Проверяем, нет ли уже аккаунта с таким телефоном (теперь глобально)
        if SenderAccount.objects.filter(phone=phone).exists():
            return JsonResponse({
                'success': False,
                'error': 'Аккаунт с таким номером уже добавлен'
            }, status=400)
        
        # Создаем новый аккаунт (БЕЗ привязки к пользователю - общий для всех)
        account = SenderAccount.objects.create(
            user=None,  # Не привязываем к пользователю
            name=name,
            phone=phone,
            api_id=int(api_id),
            api_hash=api_hash,
            is_active=is_active,
            initial_delay_min=initial_delay_min,
            initial_delay_max=initial_delay_max,
            message_delay_min=message_delay_min,
            message_delay_max=message_delay_max,
            daily_limit=daily_limit
        )
        
        logger.info(f"Admin {request.user.id} created global sender account {account.id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Аккаунт успешно добавлен. Теперь нужно пройти авторизацию.',
            'account_id': account.id
        })
        
    except Exception as e:
        logger.error(f"Error creating sender account: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(['POST'])
def update_sender_account(request, account_id):
    """Обновление sender-аккаунта (только для админов)"""
    from apps.telegram_parser.models import SenderAccount
    
    # Проверка прав доступа
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'error': 'Доступ запрещен'
        }, status=403)
    
    try:
        # Убрана фильтрация по user - аккаунты общие
        account = get_object_or_404(SenderAccount, id=account_id)
        
        name = request.POST.get('name', '').strip()
        api_id = request.POST.get('api_id', '').strip()
        api_hash = request.POST.get('api_hash', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        # Получаем настройки отправки
        initial_delay_min = int(request.POST.get('initial_delay_min', account.initial_delay_min))
        initial_delay_max = int(request.POST.get('initial_delay_max', account.initial_delay_max))
        message_delay_min = int(request.POST.get('message_delay_min', account.message_delay_min))
        message_delay_max = int(request.POST.get('message_delay_max', account.message_delay_max))
        daily_limit = int(request.POST.get('daily_limit', account.daily_limit))
        
        if not all([name, api_id, api_hash]):
            return JsonResponse({
                'success': False,
                'error': 'Заполните все обязательные поля'
            }, status=400)
        
        # Обновляем данные
        account.name = name
        account.api_id = int(api_id)
        account.api_hash = api_hash
        account.is_active = is_active
        account.initial_delay_min = initial_delay_min
        account.initial_delay_max = initial_delay_max
        account.message_delay_min = message_delay_min
        account.message_delay_max = message_delay_max
        account.daily_limit = daily_limit
        account.save()
        
        logger.info(f"Admin {request.user.id} updated global sender account {account.id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Аккаунт успешно обновлен'
        })
        
    except Exception as e:
        logger.error(f"Error updating sender account: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(['POST'])
def delete_sender_account(request, account_id):
    """Удаление sender-аккаунта (только для админов)"""
    from apps.telegram_parser.models import SenderAccount
    
    # Проверка прав доступа
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'error': 'Доступ запрещен'
        }, status=403)
    
    try:
        # Убрана фильтрация по user - аккаунты общие
        account = get_object_or_404(SenderAccount, id=account_id)
        account_name = account.name
        account.delete()
        
        logger.info(f"Admin {request.user.id} deleted global sender account {account_id}")
        logger.info(f"Deleted sender account {account_id} ({account_name}) for user {request.user.id}")
        
        return JsonResponse({
            'success': True,
            'message': f'Аккаунт "{account_name}" успешно удален'
        })
        
    except Exception as e:
        logger.error(f"Error deleting sender account: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def authorize_sender_account(request, account_id):
    """Страница авторизации конкретного sender-аккаунта (только для админов)"""
    from apps.telegram_parser.models import SenderAccount
    
    # Проверка прав доступа
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard:dashboard')
    
    # Убрана фильтрация по user - аккаунты общие
    account = get_object_or_404(SenderAccount, id=account_id)
    
    if account.is_connected:
        messages.info(request, f'Аккаунт "{account.name}" уже подключен')
        return redirect('dashboard:sender_accounts')
    
    # TODO: Реализовать логику авторизации через Telegram
    # Пока просто показываем заглушку
    return render(request, 'dashboard/sender_account_authorize.html', {
        'account': account
    })


@login_required
def create_message_template(request):
    """Создание шаблона сообщения"""
    if request.method == 'POST':
        name = request.POST.get('name')
        subject = request.POST.get('subject', '')
        template_text = request.POST.get('template_text')
        is_default = request.POST.get('is_default') == 'on'

        # Проверка AJAX запроса
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not name or not template_text:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': 'Заполните обязательные поля'
                })
            messages.error(request, 'Заполните обязательные поля')
            return redirect('dashboard:keyword_groups')

        template = MessageTemplate.objects.create(
            user=request.user,
            name=name,
            subject=subject,
            template_text=template_text,
            is_default=is_default
        )

        if is_ajax:
            return JsonResponse({
                'success': True,
                'template_id': template.id,
                'message': f'Шаблон "{name}" создан'
            })

        messages.success(request, f'Шаблон "{name}" создан')
        return redirect('dashboard:keyword_groups')

    return redirect('dashboard:keyword_groups')


@login_required
def edit_message_template(request, template_id):
    """Редактирование шаблона"""
    template = get_object_or_404(MessageTemplate, id=template_id, user=request.user)

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        template.name = request.POST.get('name')
        template.subject = request.POST.get('subject', '')
        template.template_text = request.POST.get('template_text')
        template.is_default = request.POST.get('is_default') == 'on'
        template.save()

        if is_ajax:
            return JsonResponse({
                'success': True,
                'template_id': template.id,
                'message': f'Шаблон "{template.name}" обновлен'
            })

        messages.success(request, f'Шаблон "{template.name}" обновлен')
        return redirect('dashboard:keyword_groups')

    # GET запрос для получения данных шаблона
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return JsonResponse({
            'success': True,
            'id': template.id,
            'name': template.name,
            'subject': template.subject,
            'template_text': template.template_text,
            'is_default': template.is_default
        })

    return redirect('dashboard:keyword_groups')


@login_required
@require_http_methods(['POST'])
def delete_message_template(request, template_id):
    """Удаление шаблона"""
    template = get_object_or_404(MessageTemplate, id=template_id, user=request.user)
    name = template.name
    template.delete()

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': f'Шаблон "{name}" удален'
        })

    messages.success(request, f'Шаблон "{name}" удален')
    return redirect('dashboard:keyword_groups')


@login_required
@require_http_methods(['GET'])
def get_message_template(request, template_id):
    """Получение текста шаблона (AJAX)"""
    template = get_object_or_404(MessageTemplate, id=template_id, user=request.user)

    return JsonResponse({
        'success': True,
        'id': template.id,
        'name': template.name,
        'subject': template.subject,
        'template_text': template.template_text,
        'is_default': template.is_default
    })

