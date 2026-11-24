"""Rewrite root-relative URLs when the app is mounted under a path prefix."""
import re

_HREF_ROOT = re.compile(r'(?P<attr>href|action)=(?P<q>["\'])/(?P=q)')
_PATH = r'[A-Za-z0-9_@.+\-~/?=&:%#]+'
_TEXT_MARKERS = (
    'text/html',
    'text/css',
    'javascript',
    'application/json',
)


def rewrite_text(text, prefix):
    prefix = '/' + prefix.strip('/')
    skip = re.escape(prefix.strip('/'))
    quoted = re.compile(
        rf"""(?P<q>["'])/(?!/|{skip}/)(?P<rest>{_PATH})(?P=q)"""
    )
    css_url = re.compile(rf'url\(\s*/(?!/|{skip}/)(?P<rest>{_PATH})\s*\)')

    def quoted_repl(match):
        quote = match.group('q')
        return f"{quote}{prefix}/{match.group('rest')}{quote}"

    def css_repl(match):
        return f"url({prefix}/{match.group('rest')})"

    def href(match):
        return f"{match.group('attr')}={match.group('q')}{prefix}/{match.group('q')}"

    text = quoted.sub(quoted_repl, text)
    text = css_url.sub(css_repl, text)
    return _HREF_ROOT.sub(href, text)


def _prefix(request):
    raw = (request.META.get('HTTP_X_FORWARDED_PREFIX') or '').strip()
    if not re.fullmatch(r'/[A-Za-z0-9_-]+', raw):
        return ''
    return raw


def _is_text(content_type):
    value = (content_type or '').lower()
    return any(marker in value for marker in _TEXT_MARKERS)


class ForwardedPrefixMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        prefix = _prefix(request)
        if prefix:
            request.META['SCRIPT_NAME'] = prefix
        response = self.get_response(request)
        if not prefix:
            return response
        self._rewrite_cookies(response, prefix)
        self._rewrite_location(response, prefix)
        self._rewrite_body(response, prefix)
        return response

    def _rewrite_cookies(self, response, prefix):
        for morsel in response.cookies.values():
            if (morsel['path'] or '/') == '/':
                morsel['path'] = prefix

    def _rewrite_location(self, response, prefix):
        location = response.get('Location')
        if not location or not location.startswith('/'):
            return
        if location == prefix or location.startswith(prefix + '/'):
            return
        response['Location'] = prefix + location

    def _rewrite_body(self, response, prefix):
        if response.get('Content-Encoding'):
            return
        streaming = getattr(response, 'streaming', False)
        if not _is_text(response.get('Content-Type', '')):
            return
        raw = b''.join(response.streaming_content) if streaming else response.content
        rewritten = raw
        if len(raw) <= 30 * 1024 * 1024:
            try:
                rewritten = rewrite_text(raw.decode('utf-8'), prefix).encode('utf-8')
            except UnicodeDecodeError:
                rewritten = raw
        if streaming:
            response.streaming_content = iter([rewritten])
        elif rewritten is not raw:
            response.content = rewritten
        response['Content-Length'] = str(len(rewritten))
