import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mail_dashboard.settings')
django.setup()

from logs.models import MailLog
from django.db.models import Count

# Находим и удаляем дубликаты
duplicates = MailLog.objects.values('message_id').annotate(
    count=Count('id')
).filter(count__gt=1)

for duplicate in duplicates:
    message_id = duplicate['message_id']
    if message_id:  # Пропускаем пустые message_id
        records = MailLog.objects.filter(message_id=message_id).order_by('timestamp')
        # Оставляем первую запись, удаляем остальные
        for record in records[1:]:
            record.delete()
        print(f"Removed duplicates for message_id: {message_id}")

print("Duplicate cleaning completed")