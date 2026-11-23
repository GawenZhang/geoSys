from django.conf import settings
from django.db import models


class AiRequestLog(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_logs',
    )
    operation = models.CharField(max_length=64)
    page = models.CharField(max_length=128, blank=True, default='')
    input_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, default='not_configured')
    response_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'AI 请求日志'
        verbose_name_plural = 'AI 请求日志'
