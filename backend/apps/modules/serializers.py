TITLE_KEYS = (
    'title', 'name', 'task_name', 'type_name', 'keyword', 'brand',
    'prompt', 'question', 'media_name', 'order_nid', 'nickname',
)


def pick_title(payload: dict) -> str:
    for key in TITLE_KEYS:
        value = payload.get(key)
        if value not in (None, ''):
            text = str(value).strip().splitlines()[0]
            if text:
                return text[:255]
    return ''


def pick_status(payload: dict, default=1) -> int:
    if 'status' not in payload or payload.get('status') in (None, ''):
        return default
    try:
        return int(payload.get('status'))
    except (TypeError, ValueError):
        return default


def record_payload(obj):
    data = dict(obj.data or {})
    flat = {
        'id': obj.id,
        'module': obj.module,
        'subtype': obj.subtype,
        'title': obj.title,
        'status': obj.status,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
        'addtime': obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'data': data,
    }
    # Promote common fields for table rendering
    for key, value in data.items():
        if key not in flat:
            flat[key] = value
    if 'title' not in data and obj.title:
        flat.setdefault('title', obj.title)
    if 'name' not in data and obj.title:
        flat.setdefault('name', obj.title)
    return flat
