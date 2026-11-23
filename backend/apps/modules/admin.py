from django.contrib import admin

from .models import BizRecord


@admin.register(BizRecord)
class BizRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'subtype', 'title', 'status', 'owner', 'created_at')
    list_filter = ('module', 'status')
    search_fields = ('title', 'module')
