import re
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import IntegrityError, transaction
from logs.models import MailLog
import os
import uuid

class Command(BaseCommand):
    help = 'Parse mail log and store in database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=r'D:\app\vlog\mail_dashboard\maillog',
            help='Path to mail log file',
        )

    def handle(self, *args, **options):
        log_file = options['file']
        
        if not os.path.exists(log_file):
            self.stdout.write(self.style.ERROR(f'File {log_file} not found'))
            return

        log_pattern = re.compile(
            r'(?P<timestamp>\w+\s+\d+\s+\d+:\d+:\d+)\s+'
            r'(?P<hostname>\S+)\s+'
            r'(?P<process>\S+?\[\d+\]):\s+'
            r'(?P<message>.*)'
        )

        try:
            parsed_count = 0
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    match = log_pattern.match(line)
                    if match:
                        data = match.groupdict()
                        if self.parse_line(data):
                            parsed_count += 1
            
            self.stdout.write(self.style.SUCCESS(f'Successfully parsed {parsed_count} lines from maillog'))
            
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File {log_file} not found'))
        except PermissionError:
            self.stdout.write(self.style.ERROR(f'Permission denied to read {log_file}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error reading file: {e}'))

    def parse_line(self, data):
        message = data['message']
        
        if 'status=' in message and ('to=<' in message or 'relay=' in message):
            return self.parse_delivery_status(data)
        elif 'connect from' in message:
            return self.parse_connection(data, 'connect')
        elif 'disconnect from' in message:
            return self.parse_connection(data, 'disconnect')
        elif 'from=<' in message and ('size=' in message or 'nrcpt=' in message):
            return self.parse_received_message(data)
        elif 'SASL LOGIN authentication failed' in message:
            return self.parse_auth_failure(data)
        elif 'NOQUEUE: reject:' in message or 'reject:' in message:
            return self.parse_rejection(data)
        
        return False

    def parse_delivery_status(self, data):
        status_pattern = re.compile(
            r'([A-Z0-9]+):\s+'
            r'(?:to=<([^>]+)>,\s+)?'
            r'(?:relay=([^,]+),\s+)?'
            r'(?:delay=([\d.]+),\s+)?'
            r'(?:delays=([\d./]+),\s+)?'
            r'(?:dsn=([\d.]+),\s+)?'
            r'status=(\w+)'
        )
        
        match = status_pattern.search(data['message'])
        if match:
            message_id, to_email, relay, delay, delays, dsn, status = match.groups()
            
            timestamp = self.parse_timestamp(data['timestamp'])
            if timestamp:
                # Используем атомарную транзакцию для избежания конкурентности
                try:
                    with transaction.atomic():
                        # Проверяем, существует ли уже запись с таким message_id
                        existing = MailLog.objects.filter(message_id=message_id).first()
                        if existing:
                            # Обновляем существующую запись
                            existing.to_email = to_email or existing.to_email
                            existing.relay = relay or existing.relay
                            existing.delay = float(delay) if delay else existing.delay
                            existing.delays = delays or existing.delays
                            existing.dsn = dsn or existing.dsn
                            existing.status = status or existing.status
                            existing.save()
                        else:
                            # Создаем новую запись
                            MailLog.objects.create(
                                timestamp=timestamp,
                                hostname=data['hostname'],
                                process=data['process'],
                                message_id=message_id,
                                to_email=to_email or '',
                                relay=relay or '',
                                delay=float(delay) if delay else None,
                                delays=delays or '',
                                dsn=dsn or '',
                                status=status or ''
                            )
                        return True
                except IntegrityError:
                    # Если все же возникла ошибка уникальности, пропускаем запись
                    self.stdout.write(self.style.WARNING(f'Integrity error for message_id: {message_id}'))
                    return False
        return False

    def parse_received_message(self, data):
        received_pattern = re.compile(
            r'([A-Z0-9]+):\s+'
            r'from=<([^>]+)>,\s+'
            r'(?:size=(\d+),\s+)?'
            r'(?:nrcpt=(\d+))?'
        )
        
        match = received_pattern.search(data['message'])
        if match:
            message_id, from_email, size, nrcpt = match.groups()
            
            timestamp = self.parse_timestamp(data['timestamp'])
            if timestamp:
                try:
                    with transaction.atomic():
                        # Проверяем, существует ли уже запись с таким message_id
                        existing = MailLog.objects.filter(message_id=message_id).first()
                        if existing:
                            # Обновляем существующую запись
                            existing.from_email = from_email or existing.from_email
                            existing.size = int(size) if size else existing.size
                            existing.nrcpt = int(nrcpt) if nrcpt else existing.nrcpt
                            existing.save()
                        else:
                            # Создаем новую запись
                            MailLog.objects.create(
                                timestamp=timestamp,
                                hostname=data['hostname'],
                                process=data['process'],
                                message_id=message_id,
                                from_email=from_email or '',
                                size=int(size) if size else None,
                                nrcpt=int(nrcpt) if nrcpt else None
                            )
                        return True
                except IntegrityError:
                    self.stdout.write(self.style.WARNING(f'Integrity error for message_id: {message_id}'))
                    return False
        return False

    def parse_connection(self, data, connection_type):
        connect_pattern = re.compile(
            r'(connect|disconnect) from ([^\[]+)\[([^\]]+)\]'
        )
        
        match = connect_pattern.search(data['message'])
        if match:
            action, host, ip = match.groups()
            
            timestamp = self.parse_timestamp(data['timestamp'])
            if timestamp:
                # Генерируем уникальный ID для подключений
                unique_id = f"{action}_{host}_{ip}_{int(timestamp.timestamp())}_{uuid.uuid4().hex[:8]}"
                
                MailLog.objects.create(
                    timestamp=timestamp,
                    hostname=data['hostname'],
                    process=data['process'],
                    status=f'{action}_from',
                    from_email=f'{host}[{ip}]',
                    message_id=unique_id
                )
                return True
        return False

    def parse_auth_failure(self, data):
        auth_pattern = re.compile(
            r'warning: ([^\[]+)\[([^\]]+)\]: SASL LOGIN authentication failed'
        )
        
        match = auth_pattern.search(data['message'])
        if match:
            host, ip = match.groups()
            
            timestamp = self.parse_timestamp(data['timestamp'])
            if timestamp:
                # Генерируем уникальный ID для ошибок аутентификации
                unique_id = f"AUTH_{host}_{ip}_{int(timestamp.timestamp())}_{uuid.uuid4().hex[:8]}"
                
                MailLog.objects.create(
                    timestamp=timestamp,
                    hostname=data['hostname'],
                    process=data['process'],
                    status='auth_failed',
                    from_email=f'{host}[{ip}]',
                    message_id=unique_id
                )
                return True
        return False

    def parse_rejection(self, data):
        rejection_pattern = re.compile(
            r'reject:\s+[^:]+:\s+'
            r'(?:from=<([^>]+)>)?.*?'
            r'(?:to=<([^>]+)>)?.*?'
            r'(\d+\s+\d+\.\d+\.\d+)'
        )
        
        match = rejection_pattern.search(data['message'])
        if match:
            from_email, to_email, error_code = match.groups()
            
            timestamp = self.parse_timestamp(data['timestamp'])
            if timestamp:
                # Генерируем уникальный ID для отклонений
                unique_id = f"REJ_{int(timestamp.timestamp())}_{uuid.uuid4().hex[:8]}"
                
                MailLog.objects.create(
                    timestamp=timestamp,
                    hostname=data['hostname'],
                    process=data['process'],
                    status='rejected',
                    from_email=from_email or '',
                    to_email=to_email or '',
                    dsn=error_code or '',
                    message_id=unique_id
                )
                return True
        return False

    def parse_timestamp(self, timestamp_str):
        current_year = datetime.now().year
        
        # Пробуем разные форматы дат
        formats_to_try = [
            '%b %d %H:%M:%S %Y',  # Стандартный формат с двузначным днем
            '%b %d %H:%M:%S %Y',  # Формат с однозначным днем (исправим ниже)
        ]
        
        # Нормализуем строку даты: добавляем ведущий нуль к дню, если он однозначный
        parts = timestamp_str.split()
        if len(parts) >= 3 and len(parts[1]) == 1:
            parts[1] = f"0{parts[1]}"  # Добавляем ведущий нуль
            timestamp_str = " ".join(parts)
        
        full_timestamp_str = f"{timestamp_str} {current_year}"
        
        for fmt in formats_to_try:
            try:
                timestamp = datetime.strptime(full_timestamp_str, fmt)
                return timezone.make_aware(timestamp)
            except ValueError:
                continue
        
        # Если ни один формат не сработал, попробуем обработать вручную
        try:
            # Парсим компоненты вручную
            month_str, day_str, time_str = timestamp_str.split()[:3]
            hour, minute, second = map(int, time_str.split(':'))
            
            # Преобразуем название месяца в число
            month_map = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
                'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
                'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            month = month_map[month_str]
            day = int(day_str)
            
            timestamp = datetime(current_year, month, day, hour, minute, second)
            return timezone.make_aware(timestamp)
        except (ValueError, KeyError) as e:
            self.stdout.write(self.style.ERROR(f'Error parsing timestamp {timestamp_str}: {e}'))
            return None