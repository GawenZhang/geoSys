from django.db.models import Q
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.responses import fail, ok, paginate, parse_json

from .models import BizRecord
from .registry import MODULES, module_exists, resolve_page
from .serializers import pick_status, pick_title, record_payload


def _user_or_401(request):
    if not request.user.is_authenticated:
        return None, fail('unauthenticated', '未登录', status=401)
    return request.user, None


def _ids(body):
    raw = body.get('ids')
    if raw is None and body.get('id') is not None:
        raw = [body.get('id')]
    if not isinstance(raw, list):
        return []
    ids = []
    for value in raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _normalize_payload(body: dict) -> dict:
    payload = {}
    for key, value in (body or {}).items():
        if key in ('id', 'module', 'subtype', 'ids', 'page', 'page_size'):
            continue
        if key == 'data' and isinstance(value, dict):
            payload.update(value)
            continue
        payload[key] = value
    return payload


@require_GET
def module_list(request):
    user, err = _user_or_401(request)
    if err:
        return err
    items = [
        {'key': key, 'label': label, 'count': BizRecord.objects.filter(owner=user, module=key).count()}
        for key, label in MODULES.items()
    ]
    return ok({'items': items})


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def module_records(request, module):
    user, err = _user_or_401(request)
    if err:
        return err
    if not module_exists(module):
        return fail('not_found', f'未知模块: {module}', status=404)

    qs = BizRecord.objects.filter(owner=user, module=module)
    subtype = (request.GET.get('subtype') or '').strip()
    if subtype:
        qs = qs.filter(subtype=subtype)

    if request.method == 'GET':
        raw_id = request.GET.get('id')
        if raw_id not in (None, ''):
            try:
                obj_id = int(raw_id)
            except (TypeError, ValueError):
                return fail('validation_error', 'id 无效', status=400)
            obj = qs.filter(id=obj_id).first()
            if not obj:
                return fail('not_found', '记录不存在', status=404)
            return ok(record_payload(obj))
        q = (request.GET.get('q') or request.GET.get('search') or '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q))
        status_raw = request.GET.get('status')
        if status_raw not in (None, ''):
            try:
                qs = qs.filter(status=int(status_raw))
            except (TypeError, ValueError):
                pass
        return ok(paginate(qs, request, record_payload))

    body, parse_err = _parse(request)
    if parse_err:
        return parse_err

    if request.method == 'POST':
        subtype_value = str(body.get('subtype') or subtype or '').strip()
        payload = _normalize_payload(body)
        obj = BizRecord(
            owner=user,
            module=module,
            subtype=subtype_value,
            title=pick_title(payload) or f'{MODULES.get(module, module)}记录',
            status=pick_status(payload, 1),
            data=payload,
        )
        obj.save()
        return ok(record_payload(obj), status=201)

    if request.method in ('PUT', 'PATCH'):
        try:
            obj_id = int(body.get('id'))
        except (TypeError, ValueError):
            return fail('validation_error', '缺少有效 id', status=400)
        obj = qs.filter(id=obj_id).first()
        if not obj:
            return fail('not_found', '记录不存在', status=404)
        payload = _normalize_payload(body)
        if payload:
            merged = dict(obj.data or {})
            merged.update(payload)
            obj.data = merged
            obj.title = pick_title(merged) or obj.title
            obj.status = pick_status(merged, obj.status)
        if 'subtype' in body:
            obj.subtype = str(body.get('subtype') or '').strip()
        obj.save()
        return ok(record_payload(obj))

    if request.method == 'DELETE':
        ids = _ids(body)
        if not ids:
            return fail('validation_error', '请提供要删除的 ids', status=400)
        deleted, _ = qs.filter(id__in=ids).delete()
        return ok({'deleted': deleted})

    return fail('method_not_allowed', '不支持的方法', status=405)


@require_GET
def resolve(request):
    """Resolve a frontend pageKey to module API metadata."""
    page_key = (request.GET.get('page') or '').strip()
    module, subtype = resolve_page(page_key)
    if not module:
        return ok({'module': None, 'subtype': None, 'resource': None})
    resource = f'/api/modules/{module}/'
    if subtype:
        resource = f'{resource}?subtype={subtype}'
    return ok({
        'module': module,
        'subtype': subtype or '',
        'label': MODULES.get(module, module),
        'resource': resource,
    })


@require_GET
def module_options(request, module):
    """Lightweight options list for selects (id + label)."""
    user, err = _user_or_401(request)
    if err:
        return err
    if not module_exists(module):
        return fail('not_found', f'未知模块: {module}', status=404)
    qs = BizRecord.objects.filter(owner=user, module=module)
    subtype = (request.GET.get('subtype') or '').strip()
    if subtype:
        qs = qs.filter(subtype=subtype)
    items = []
    for obj in qs.order_by('-id')[:200]:
        items.append({'id': obj.id, 'label': obj.title or f'{module}#{obj.id}'})
    return ok({'items': items})


def _parse(request):
    try:
        return parse_json(request), None
    except ValueError:
        return None, fail('invalid_json', '请求体必须是 JSON', status=400)
