"""Push approved articles to WordPress or a webhook. Local preview is /p/<id>."""
import base64
import json
import socket
from urllib.parse import urlparse
import urllib.error
import urllib.request

from apps.content.models import Article
from apps.modules.models import BizRecord

from .quality import release_block_reason
from .worker import _as_int


class PublishError(Exception):
    pass


_BLOCKED_HOSTS = {'localhost', 'localhost.localdomain', '0.0.0.0'}


def _is_public_http(url: str) -> None:
    parsed = urlparse(url or '')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise PublishError('站点地址必须是 http 或 https URL')
    host = parsed.hostname.lower().rstrip('.')
    if host in _BLOCKED_HOSTS or host.endswith('.local'):
        raise PublishError('站点地址不能指向本机')
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror as exc:
        raise PublishError('站点地址无法解析') from exc
    for info in infos:
        ip = info[4][0]
        if _private_ip(ip):
            raise PublishError('站点地址不能指向内网')


def _private_ip(ip: str) -> bool:
    if ip.startswith('127.') or ip == '::1' or ip.startswith('0.'):
        return True
    if ip.startswith('10.') or ip.startswith('192.168.') or ip.startswith('169.254.'):
        return True
    if ip.startswith('172.'):
        try:
            second = int(ip.split('.')[1])
        except (IndexError, ValueError):
            return True
        if 16 <= second <= 31:
            return True
    if ip.startswith('fe80:') or ip.startswith('fc') or ip.startswith('fd'):
        return True
    return False


def http_post(url: str, payload: dict, headers: dict, timeout: int = 20) -> tuple[int, str]:
    _is_public_http(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode('utf-8', errors='ignore')[:2000]
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read().decode('utf-8', errors='ignore')[:300]
        except Exception:
            detail = ''
        return exc.code, detail or f'HTTP {exc.code}'


def _endpoint(site) -> tuple[str, dict, str]:
    data = site.data or {}
    site_type = _as_int(data.get('site_type'), 0)
    site_url = str(data.get('site_url') or '').strip().rstrip('/')
    if site_type == 3:
        url = f'{site_url}/wp-json/wp/v2/posts'
        username = str(data.get('site_username') or '')
        password = str(data.get('api_password') or data.get('api_key') or '')
        token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
        headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'geoSys-publish/1.0',
        }
        return url, headers, 'wordpress'
    if site_type == 10:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'geoSys-publish/1.0',
        }
        api_key = str(data.get('api_key') or '').strip()
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        return site_url, headers, 'webhook'
    raise PublishError('当前只支持 WordPress 和自定义 Webhook')


def _already_published(owner, site_id: int) -> set[int]:
    ids = set()
    rows = BizRecord.objects.filter(owner=owner, module='user_site_record')
    for row in rows:
        data = row.data or {}
        if _as_int(data.get('user_site_id'), 0) != site_id:
            continue
        if _as_int(data.get('status'), 0) != 1:
            continue
        article_id = _as_int(data.get('article_id'), 0)
        if article_id:
            ids.add(article_id)
    return ids


def publish_site_task(task_id: int, owner) -> dict:
    task = BizRecord.objects.filter(owner=owner, module='user_site_task', id=task_id).first()
    if not task:
        raise PublishError('站点任务不存在')
    data = task.data or {}
    site = BizRecord.objects.filter(
        owner=owner,
        module='user_site',
        id=_as_int(data.get('user_site_id'), 0),
    ).first()
    if not site:
        raise PublishError('请选择站点')
    url, headers, kind = _endpoint(site)
    _is_public_http(url)
    type_id = _as_int(data.get('article_type_id'), 0)
    limit = min(20, max(1, _as_int(data.get('day_send_count'), 5) or 5))
    articles = Article.objects.filter(owner=owner, status=Article.STATUS_NORMAL).order_by('id')
    if type_id:
        articles = articles.filter(article_type_id=type_id)
    done = _already_published(owner, site.id)
    published = []
    failed = []
    for article in articles:
        if len(published) >= limit:
            break
        if article.id in done:
            continue
        if release_block_reason(article):
            continue
        payload = {
            'title': article.title,
            'content': article.content,
            'status': 'publish',
            'article_id': article.id,
            'scode': data.get('scode') or (site.data or {}).get('scode') or '',
        }
        status_code, body = http_post(url, payload, headers)
        ok = 200 <= status_code < 300
        record_data = {
            'title': article.title,
            'article_id': article.id,
            'user_site_id': site.id,
            'user_site_task_id': task.id,
            'status': 1 if ok else 0,
            'channel': kind,
            'response_status': status_code,
            'error': '' if ok else body[:300],
        }
        BizRecord.objects.create(
            owner=owner,
            module='user_site_record',
            title=article.title[:255],
            status=1 if ok else 0,
            data=record_data,
        )
        if ok:
            published.append(article.id)
        else:
            failed.append({'article_id': article.id, 'error': body[:300]})
    if not published and not failed:
        message = '没有可推送的已审核文章'
    elif failed and not published:
        message = '推送失败'
    else:
        message = f'已推送 {len(published)} 篇'
    return {
        'published': len(published),
        'article_ids': published,
        'failed': failed,
        'message': message,
        'channel': kind,
    }
