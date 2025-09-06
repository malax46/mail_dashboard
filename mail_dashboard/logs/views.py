from django.shortcuts import render
from django.db.models import Count, Q, Min, Max
from django.utils import timezone
from django.http import JsonResponse
from .models import MailLog
from datetime import timedelta
import json

def dashboard(request):
    # Получаем общую статистику для отображения
    total_messages = MailLog.objects.count()
    sent_messages = MailLog.objects.filter(status='sent').count()
    bounced_messages = MailLog.objects.filter(status='bounced').count()
    rejected_messages = MailLog.objects.filter(status='rejected').count()
    auth_failures = MailLog.objects.filter(status='auth_failed').count()
    recent_messages = MailLog.objects.order_by('-timestamp')[:20]
    
    # Получаем диапазон дат в базе данных
    date_range = MailLog.objects.aggregate(
        min_date=Min('timestamp'),
        max_date=Max('timestamp')
    )
    
    # Топ отправителей
    top_senders = MailLog.objects.exclude(from_email='').values('from_email').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Топ получателей
    top_recipients = MailLog.objects.exclude(to_email='').values('to_email').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    context = {
        'total_messages': total_messages,
        'sent_messages': sent_messages,
        'bounced_messages': bounced_messages,
        'rejected_messages': rejected_messages,
        'auth_failures': auth_failures,
        'recent_messages': recent_messages,
        'top_senders': top_senders,
        'top_recipients': top_recipients,
        'min_date': date_range['min_date'],
        'max_date': date_range['max_date'],
    }
    return render(request, 'logs/dashboard.html', context)

def get_chart_data(request):
    # Получаем диапазон дат в базе данных
    date_range = MailLog.objects.aggregate(
        min_date=Min('timestamp'),
        max_date=Max('timestamp')
    )
    
    # Если данных нет, возвращаем пустые наборы
    if not date_range['min_date'] or not date_range['max_date']:
        return JsonResponse({
            'status_labels': [],
            'status_data': [],
            'hourly_labels': [],
            'hourly_data': [],
            'daily_labels': [],
            'daily_data': [],
        })
    
    # Используем весь доступный диапазон дат вместо последних 7 дней
    start_date = date_range['min_date']
    end_date = date_range['max_date']
    
    # График по статусам
    status_stats = MailLog.objects.exclude(status='').values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # График по часам (исправленный запрос для SQLite)
    hourly_stats = MailLog.objects.extra(
        select={'hour': "strftime('%H', timestamp)"}
    ).values('hour').annotate(count=Count('id')).order_by('hour')
    
    # График по дням
    daily_stats = MailLog.objects.extra(
        select={'day': "strftime('%Y-%m-%d', timestamp)"}
    ).values('day').annotate(count=Count('id')).order_by('day')
    
    # Подготовка данных для графиков
    status_labels = [item['status'] for item in status_stats]
    status_data = [item['count'] for item in status_stats]
    
    # Создаем полный список часов (0-23) для правильного отображения
    hours = [f"{i:02d}" for i in range(24)]
    hourly_counts = {item['hour']: item['count'] for item in hourly_stats}
    hourly_data = [hourly_counts.get(hour, 0) for hour in hours]
    
    # Данные по дням
    daily_labels = [item['day'] for item in daily_stats]
    daily_data = [item['count'] for item in daily_stats]
    
    return JsonResponse({
        'status_labels': status_labels,
        'status_data': status_data,
        'hourly_labels': hours,
        'hourly_data': hourly_data,
        'daily_labels': daily_labels,
        'daily_data': daily_data,
        'date_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
    })