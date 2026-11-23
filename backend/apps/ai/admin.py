from django.contrib import admin

from .models import AiRequestLog


@admin.register(AiRequestLog)
class AiRequestLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation', 'page', 'status', 'owner', 'created_at')
    list_filter = ('status', 'operation')
    search_fields = ('page',)
