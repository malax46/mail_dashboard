from django.db import models

class MailLog(models.Model):
    timestamp = models.DateTimeField()
    hostname = models.CharField(max_length=100)
    process = models.CharField(max_length=100)
    message_id = models.CharField(max_length=50, blank=True, null=True)  # Разрешаем NULL
    from_email = models.CharField(max_length=255, blank=True)
    to_email = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, blank=True)
    size = models.IntegerField(null=True, blank=True)
    delay = models.FloatField(null=True, blank=True)
    delays = models.CharField(max_length=100, blank=True)
    dsn = models.CharField(max_length=10, blank=True)
    relay = models.CharField(max_length=255, blank=True)
    nrcpt = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['message_id']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.message_id} - {self.status}"