"""Serve the static frontend from app/dist with SPA-friendly route fallbacks."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

DIST = Path(settings.FRONTEND_DIST)


def _safe_file(relative: str) -> Path | None:
    if not DIST.exists():
        return None
    candidate = (DIST / relative).resolve()
    try:
        candidate.relative_to(DIST.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _guess_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        '.html': 'text/html; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
        '.map': 'application/json',
        '.txt': 'text/plain; charset=utf-8',
    }.get(suffix, 'application/octet-stream')


def _response(path: Path):
    response = FileResponse(path.open('rb'), content_type=_guess_type(path))
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@ensure_csrf_cookie
@require_GET
def frontend(request, path=''):
    get_token(request)
    relative = path.lstrip('/')
    # Exact file
    found = _safe_file(relative)
    if found:
        return _response(found)
    # Directory index
    if relative:
        found = _safe_file(f'{relative.rstrip("/")}/index.html')
        if found:
            return _response(found)
    else:
        found = _safe_file('index.html')
        if found:
            return _response(found)
    # Common login aliases
    if relative in ('user/index/login', 'user/index/login/'):
        found = _safe_file('user/index/login/index.html') or _safe_file('index.html')
        if found:
            return _response(found)
    not_found = _safe_file('404.html')
    if not_found:
        response = _response(not_found)
        response.status_code = 404
        return response
    raise Http404('Frontend asset not found')
