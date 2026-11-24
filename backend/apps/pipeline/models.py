from django.conf import settings
from django.db import models


class KnowledgeChunk(models.Model):
    """A searchable slice of an enterprise knowledge record."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_chunks',
    )
    source = models.ForeignKey(
        'modules.BizRecord',
        on_delete=models.CASCADE,
        related_name='knowledge_chunks',
    )
    section = models.CharField(max_length=64)
    text = models.TextField()
    keywords = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['owner', 'source']),
        ]

    def __str__(self):
        return f'{self.section}:{self.text[:24]}'


class Topic(models.Model):
    LAYOUT_CARD = 'card'
    LAYOUT_GUIDE = 'guide'
    LAYOUT_TIMELINE = 'timeline'
    STATUS_DRAFT = 0
    STATUS_PUBLISHED = 1

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, default='')
    layout = models.CharField(max_length=16, default=LAYOUT_CARD)
    status = models.PositiveSmallIntegerField(default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']


class TopicArticle(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='items')
    article = models.ForeignKey('content.Article', on_delete=models.CASCADE, related_name='topic_items')
    group_name = models.CharField(max_length=64, blank=True, default='')
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort', 'id']
        unique_together = [('topic', 'article')]


class LinkItem(models.Model):
    STATUS_UNKNOWN = 0
    STATUS_HEALTHY = 1
    STATUS_FAILED = 2

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='link_items')
    title = models.CharField(max_length=200)
    url = models.CharField(max_length=500)
    category = models.CharField(max_length=64, blank=True, default='')
    keywords = models.CharField(max_length=200, blank=True, default='')
    status = models.PositiveSmallIntegerField(default=STATUS_UNKNOWN)
    last_status = models.CharField(max_length=80, blank=True, default='')
    last_checked = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']


class PublishOrder(models.Model):
    """Human work order for platforms that are not posted by the server."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='publish_orders')
    article = models.ForeignKey('content.Article', on_delete=models.CASCADE, related_name='publish_orders')
    platform = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default='pending')
    note = models.TextField(blank=True, default='')
    receipt = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']


class PageHit(models.Model):
    path = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, default='visit')
    user_agent = models.CharField(max_length=180, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['kind', 'created_at'])]


class VisibilityNote(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='visibility_note')
    competitors = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)
