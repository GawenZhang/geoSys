from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as media_serve

from apps.core.dashboard import dashboard
from apps.core.frontend import frontend
from apps.core.upload import ueditor_controller, upload
from apps.core.views import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health', health, name='health'),
    path('api/dashboard', dashboard, name='dashboard'),
    path('api/upload', upload, name='upload'),
    path('api/ueditor', ueditor_controller, name='ueditor'),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/', include('apps.content.urls')),
    path('api/', include('apps.modules.urls')),
    path('api/', include('apps.ai.urls')),
    re_path(
        r'^media/(?P<path>.*)$',
        media_serve,
        {'document_root': settings.MEDIA_ROOT},
        name='media',
    ),
    re_path(r'^(?P<path>.*)$', frontend, name='frontend'),
]
