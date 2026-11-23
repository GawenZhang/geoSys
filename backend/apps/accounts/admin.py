from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('扩展信息', {'fields': ('nickname', 'avatar')}),
    )
    list_display = ('username', 'nickname', 'email', 'is_staff', 'is_active')
