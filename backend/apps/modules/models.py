from django.conf import settings
from django.db import models


class BizRecord(models.Model):
    """Generic store for remaining admin modules (JSON payload)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='biz_records',
    )
    module = models.CharField(max_length=64, db_index=True)
    subtype = models.CharField(max_length=64, blank=True, default='', db_index=True)
    title = models.CharField(max_length=255, blank=True, default='')
    status = models.IntegerField(default=1)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['owner', 'module', 'subtype']),
        ]
        verbose_name = '业务记录'
        verbose_name_plural = '业务记录'

    def __str__(self):
        return f'{self.module}:{self.title or self.id}'
