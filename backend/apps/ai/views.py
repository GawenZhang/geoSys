import json
import urllib.error
import urllib.request

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.core.responses import fail, parse_json

from .models import AiRequestLog


def _demo_result(operation: str, payload: dict) -> dict:
    fields = payload.get('fields') if isinstance(payload.get('fields'), dict) else {}
    page = str(payload.get('page') or '')
    snippets = []
    for key, value in list(fields.items())[:8]:
        text = str(value or '').strip()
        if text:
            snippets.append(f'{key}: {text[:120]}')
    joined = '\n'.join(snippets) or '（未填写表单字段）'

    brand = str(fields.get('brand_name') or fields.get('brand') or fields.get('title') or '该品牌').strip()
    company = str(fields.get('full_name') or '').strip()
    industry = str(fields.get('industry') or '').strip()
    region = str(fields.get('region') or '').strip()
    competitors = str(fields.get('competitors') or '').strip()
    platforms = str(fields.get('platforms') or '').strip()
    need_advice = str(fields.get('need_advice') or '0') == '1'
    profile = {
        'full_name': company or f'{brand}（请核对工商全称）',
        'industry': industry,
        'region': region or '服务全球',
        'competitors': competitors,
    }

    if operation == 'detect':
        lines = ['诊断任务已创建。当前账号为无限额度，本次不扣费。', '', f'品牌：{brand}']
        if company:
            lines.append(f'企业：{company}')
        if industry:
            lines.append(f'行业词：{industry}')
        if region:
            lines.append(f'地区：{region}')
        if competitors:
            lines.append(f'竞品：{competitors}')
        if platforms:
            lines.append(f'诊断平台：{platforms}')
        lines.append('')
        lines.append(
            f'可见度判断：在已选平台的公开回答中可以识别「{brand}」'
            + (f'与「{industry}」的关联' if industry else '')
            + '，问答覆盖和权威引用仍可以加强。'
        )
        if need_advice:
            lines.extend([
                '',
                '优化建议：',
                '1）把品牌全称和简称一起写进标题与问答。',
                f'2）围绕行业词「{industry or "核心业务"}」补充对比问答和场景说明。',
                '3）在已选平台持续发布可被引用的企业介绍、案例和参数。',
            ])
        else:
            lines.extend(['', '本次仅生成可见度报告，未附带优化建议。'])
        content = '\n'.join(lines)
    elif operation == 'analyze':
        content = (
            f'已根据「{brand}」整理全网资料。\n'
            '企业全称、行业、地区和竞品已填入下方，可继续创建诊断任务。\n\n'
            f'{joined}'
        )
    else:
        content = (
            '【演示生成内容】\n'
            f'页面：{page or "-"}\n'
            '这是本地 demo 模式生成的示例文案，便于联调前后端。'
            '配置 AI_MODE=proxy 与上游密钥后即可切换真实模型。\n\n'
            f'{joined}\n\n'
            '——\n生成于 geoSys AI demo 模式。'
        )
    return {
        'text': content,
        'content': content,
        'mode': 'demo',
        'operation': operation,
        'page': page,
        'profile': profile,
    }


def _call_upstream(operation: str, payload: dict) -> dict:
    url = getattr(settings, 'AI_UPSTREAM_URL', '') or ''
    api_key = getattr(settings, 'AI_UPSTREAM_KEY', '') or ''
    model = getattr(settings, 'AI_UPSTREAM_MODEL', 'gpt-4o-mini') or 'gpt-4o-mini'
    if not url:
        raise RuntimeError('未配置 AI_UPSTREAM_URL')

    fields = payload.get('fields') if isinstance(payload.get('fields'), dict) else payload
    user_prompt = json.dumps({'operation': operation, 'input': fields}, ensure_ascii=False)
    system_prompt = (
        '你是 geoSys 后台的内容助手。根据 operation 返回简洁中文结果：'
        'generate=生成文案，detect=诊断，analyze=分析。直接输出可用正文。'
    )
    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.7,
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode('utf-8')
    data = json.loads(raw)
    text = ''
    if isinstance(data, dict):
        choices = data.get('choices')
        if isinstance(choices, list) and choices:
            message = choices[0].get('message') if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                text = str(message.get('content') or '')
        if not text and data.get('data') is not None:
            return data.get('data')
        if not text and data.get('content'):
            text = str(data.get('content'))
    if not text:
        raise RuntimeError('上游未返回可用内容')
    return {'text': text, 'content': text, 'mode': 'proxy', 'operation': operation, 'raw': data}


@require_POST
def ai_proxy(request):
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)

    try:
        body = parse_json(request)
    except ValueError:
        return fail('invalid_json', '请求体必须是 JSON', status=400)

    operation = str(body.get('operation') or '').strip()
    if not operation:
        return fail('validation_error', '缺少 operation', status=400)

    payload = body.get('input')
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return fail('validation_error', 'input 必须是对象', status=400)

    page = str(payload.get('page') or '')[:128]
    mode = getattr(settings, 'AI_MODE', 'stub')

    if mode == 'stub':
        result = {
            'ok': False,
            'error': {
                'code': 'not_configured',
                'message': 'AI 服务尚未接入，请先配置服务接口。',
            },
            'data': None,
        }
        AiRequestLog.objects.create(
            owner=request.user,
            operation=operation,
            page=page,
            input_payload=payload,
            status='not_configured',
            response_payload=result,
        )
        return JsonResponse(result, status=200)

    if mode == 'demo':
        data = _demo_result(operation, payload)
        result = {'ok': True, 'data': data}
        AiRequestLog.objects.create(
            owner=request.user,
            operation=operation,
            page=page,
            input_payload=payload,
            status='ok',
            response_payload=result,
        )
        return JsonResponse(result, status=200)

    try:
        data = _call_upstream(operation, payload)
        result = {'ok': True, 'data': data}
        AiRequestLog.objects.create(
            owner=request.user,
            operation=operation,
            page=page,
            input_payload=payload,
            status='ok',
            response_payload={'ok': True, 'data': {'text': data.get('text'), 'mode': data.get('mode')}},
        )
        return JsonResponse(result, status=200)
    except urllib.error.HTTPError as exc:
        message = f'上游 HTTP {exc.code}'
        try:
            message = exc.read().decode('utf-8', errors='ignore')[:300] or message
        except Exception:
            pass
        result = {
            'ok': False,
            'error': {'code': 'service_error', 'message': message},
            'data': None,
        }
        AiRequestLog.objects.create(
            owner=request.user,
            operation=operation,
            page=page,
            input_payload=payload,
            status='error',
            response_payload=result,
        )
        return JsonResponse(result, status=502)
    except Exception as exc:
        result = {
            'ok': False,
            'error': {'code': 'service_error', 'message': str(exc)[:300]},
            'data': None,
        }
        AiRequestLog.objects.create(
            owner=request.user,
            operation=operation,
            page=page,
            input_payload=payload,
            status='error',
            response_payload=result,
        )
        return JsonResponse(result, status=502)
