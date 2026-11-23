import json
from django.http import JsonResponse


def ok(data=None, status=200):
    return JsonResponse({'ok': True, 'data': data}, status=status)


def fail(code, message, status=400, data=None):
    payload = {
        'ok': False,
        'data': data,
        'error': {'code': code, 'message': message},
    }
    return JsonResponse(payload, status=status)


def parse_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid JSON body') from exc


def paginate(queryset, request, serializer):
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(100, max(1, int(request.GET.get('page_size', 20))))
    except (TypeError, ValueError):
        page_size = 20
    total = queryset.count()
    start = (page - 1) * page_size
    items = [serializer(obj) for obj in queryset[start:start + page_size]]
    return {
        'items': items,
        'page': page,
        'page_size': page_size,
        'total': total,
    }
