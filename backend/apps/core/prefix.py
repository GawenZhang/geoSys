"""Rewrite root-relative URLs when the app is mounted under a path prefix."""
import re

# Any root-relative path except "/" itself, protocol-relative "//", and an existing prefix.
_QUOTED = re.compile(r"""(?P<q>["'])/(?!/|geo/)(?P<rest>[^"']+)""")
_CSS_URL = re.compile(r'url\(\s*/(?!/|geo/)')
_HREF_ROOT = re.compile(r'(?P<attr>href|action)=(?P<q>["\'])/(?P=q)')
_TEXT_MARKERS = (
    'text/html',
    'text/css',
    'javascript',
    'application/json',
)


def rewrite_text(text, prefix):
    prefix = '/' + prefix.strip('/')

    def quoted(match):
        return f"{match.group('q')}{prefix}/{match.group('rest')}"

    def css(match):
        return match.group(0).replace('/', f'{prefix}/', 1)

    def href(match):
        return f"{match.group('attr')}={match.group('q')}{prefix}/{match.group('q')}"

    text = _QUOTED.sub(quoted, text)
    text = _CSS_URL.sub(css, text)
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
