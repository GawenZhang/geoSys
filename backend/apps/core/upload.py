"""File upload + UEditor-compatible controller."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.responses import fail, ok

ALLOWED_EXT = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    '.zip', '.rar', '.xls', '.xlsx', '.mp3', '.mp4', '.mov', '.pdf', '.doc', '.docx',
}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
MAX_BYTES = 20 * 1024 * 1024

UEDITOR_CONFIG = {
    'imageActionName': 'uploadimage',
    'imageFieldName': 'upfile',
    'imageMaxSize': MAX_BYTES,
    'imageAllowFiles': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
    'imageCompressEnable': False,
    'imageInsertAlign': 'none',
    'imageUrlPrefix': '',
    'imagePathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'scrawlActionName': 'uploadscrawl',
    'scrawlFieldName': 'upfile',
    'scrawlPathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'scrawlMaxSize': MAX_BYTES,
    'scrawlUrlPrefix': '',
    'snapscreenActionName': 'uploadimage',
    'snapscreenPathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'snapscreenUrlPrefix': '',
    'catcherLocalDomain': ['127.0.0.1', 'localhost'],
    'catcherActionName': 'catchimage',
    'catcherFieldName': 'source',
    'catcherPathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'catcherUrlPrefix': '',
    'catcherMaxSize': MAX_BYTES,
    'catcherAllowFiles': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
    'videoActionName': 'uploadvideo',
    'videoFieldName': 'upfile',
    'videoPathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'videoUrlPrefix': '',
    'videoMaxSize': MAX_BYTES,
    'videoAllowFiles': ['.mp4', '.mov'],
    'fileActionName': 'uploadfile',
    'fileFieldName': 'upfile',
    'filePathFormat': '/media/ueditor/{yyyy}{mm}{dd}/{time}{rand:6}',
    'fileUrlPrefix': '',
    'fileMaxSize': MAX_BYTES,
    'fileAllowFiles': list(ALLOWED_EXT),
}


def _auth_or_fail(request):
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)
    return None


def _safe_ext(name: str) -> str:
    suffix = Path(name or '').suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise ValueError(f'不支持的文件类型: {suffix or "(无)"}')
    return suffix


def _store_file(uploaded, *, subdir: str = 'uploads') -> dict:
    if uploaded is None:
        raise ValueError('未收到文件')
    if uploaded.size and uploaded.size > MAX_BYTES:
        raise ValueError('文件过大（最大 20MB）')
    ext = _safe_ext(uploaded.name)
    now = datetime.now()
    relative_dir = Path(subdir) / now.strftime('%Y%m%d')
    dest_dir = Path(settings.MEDIA_ROOT) / relative_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex}{ext}'
    dest = dest_dir / filename
    with dest.open('wb') as out:
        for chunk in uploaded.chunks():
            out.write(chunk)
    url = f'{settings.MEDIA_URL.rstrip("/")}/{relative_dir.as_posix()}/{filename}'
    return {
        'url': url,
        'name': uploaded.name or filename,
        'filename': filename,
        'size': uploaded.size or dest.stat().st_size,
        'ext': ext,
        'is_image': ext in IMAGE_EXT,
    }


@require_http_methods(['POST'])
def upload(request):
    err = _auth_or_fail(request)
    if err:
        return err
    files = request.FILES.getlist('file') or request.FILES.getlist('files')
    if not files:
        single = request.FILES.get('file') or request.FILES.get('upfile')
        files = [single] if single else []
    if not files:
        return fail('validation_error', '请选择要上传的文件', status=400)
    category = re.sub(r'[^a-zA-Z0-9_-]', '', str(request.POST.get('category') or 'uploads')) or 'uploads'
    saved = []
    try:
        for item in files:
            saved.append(_store_file(item, subdir=category))
    except ValueError as exc:
        return fail('validation_error', str(exc), status=400)
    data = saved[0] if len(saved) == 1 else {'items': saved}
    return ok(data, status=201)


def _ueditor_ok(payload: dict) -> HttpResponse:
    body = json.dumps(payload, ensure_ascii=False)
    return HttpResponse(body, content_type='application/json; charset=utf-8')


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def ueditor_controller(request):
    """UEditor serverUrl endpoint (action=config|uploadimage|...)."""
    if not request.user.is_authenticated:
        return _ueditor_ok({'state': '未登录'})

    action = (request.GET.get('action') or request.POST.get('action') or 'config').strip()
    if action == 'config':
        callback = request.GET.get('callback')
        payload = json.dumps(UEDITOR_CONFIG, ensure_ascii=False)
        if callback and re.match(r'^[\w.]+$', callback):
            return HttpResponse(f'{callback}({payload});', content_type='application/javascript; charset=utf-8')
        return HttpResponse(payload, content_type='application/json; charset=utf-8')

    if action in ('uploadimage', 'uploadfile', 'uploadvideo', 'uploadscrawl'):
        field = 'upfile'
        uploaded = request.FILES.get(field) or request.FILES.get('file')
        try:
            info = _store_file(uploaded, subdir='ueditor')
        except ValueError as exc:
            return _ueditor_ok({'state': str(exc)})
        return _ueditor_ok({
            'state': 'SUCCESS',
            'url': info['url'],
            'title': info['filename'],
            'original': info['name'],
            'type': info['ext'],
            'size': info['size'],
        })

    return _ueditor_ok({'state': f'不支持的 action: {action}'})
