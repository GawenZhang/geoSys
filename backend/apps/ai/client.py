"""OpenAI-compatible chat used by the writing pipeline."""
import json
import urllib.error
import urllib.request

from django.conf import settings


class AiNotConfigured(RuntimeError):
    pass


def complete_text(system: str, user: str) -> str:
    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode == 'stub':
        raise AiNotConfigured('AI 服务尚未接入，请先配置服务接口。')
    if mode == 'demo':
        raise AiNotConfigured('demo 模式不调用上游模型')
    url = getattr(settings, 'AI_UPSTREAM_URL', '') or ''
    if not url:
        raise AiNotConfigured('未配置 AI_UPSTREAM_URL')
    api_key = getattr(settings, 'AI_UPSTREAM_KEY', '') or ''
    model = getattr(settings, 'AI_UPSTREAM_MODEL', 'gpt-4o-mini') or 'gpt-4o-mini'
    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'temperature': 0.4,
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'geoSys-ai-proxy/1.0',
    }
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    timeout = float(getattr(settings, 'AI_UPSTREAM_TIMEOUT', 60) or 60)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read().decode('utf-8', errors='ignore')[:300]
        except Exception:
            detail = ''
        raise RuntimeError(detail or f'上游 HTTP {exc.code}') from exc
    data = json.loads(raw)
    text = ''
    if isinstance(data, dict):
        choices = data.get('choices')
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get('message') or {}
            if isinstance(message, dict):
                text = str(message.get('content') or '')
        if not text and data.get('content'):
            text = str(data.get('content'))
    if not text:
        raise RuntimeError('上游未返回可用内容')
    return text
