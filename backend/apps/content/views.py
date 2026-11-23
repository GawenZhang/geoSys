from django.db.models import Q
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.responses import fail, ok, paginate, parse_json

from .models import Article, ArticleType, CompanyKeyword, CompanyQuestion
from .serializers import (
    article_payload,
    article_type_payload,
    keyword_payload,
    question_payload,
)


def _user_or_401(request):
    if not request.user.is_authenticated:
        return None, fail('unauthenticated', '未登录', status=401)
    return request.user, None


def _owned(model, user):
    return model.objects.filter(owner=user)


def _parse_body(request):
    try:
        return parse_json(request), None
    except ValueError:
        return None, fail('invalid_json', '请求体必须是 JSON', status=400)


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


def _as_str(value, *, required=False, max_length=255):
    text = '' if value is None else str(value).strip()
    if required and not text:
        raise ValueError('必填字段不能为空')
    return text[:max_length]


def _as_text(value, *, required=False):
    text = '' if value is None else str(value)
    if required and not text.strip():
        raise ValueError('必填字段不能为空')
    return text


def _as_int(value, *, default=0, required=False, min_value=None, max_value=None, allow_none=False):
    if value in (None, ''):
        if allow_none and not required:
            return None
        if not required:
            return default
        raise ValueError('需要整数')
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('需要整数') from exc
    if min_value is not None and number < min_value:
        raise ValueError('数值过小')
    if max_value is not None and number > max_value:
        raise ValueError('数值过大')
    return number


def _list_or_mutate(request, *, model, serializer, search_fields, apply_create, apply_update):
    user, err = _user_or_401(request)
    if err:
        return err
    qs = _owned(model, user)

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
            return ok(serializer(obj))
        q = (request.GET.get('q') or request.GET.get('search') or '').strip()
        if q and search_fields:
            query = Q()
            for field in search_fields:
                query |= Q(**{f'{field}__icontains': q})
            qs = qs.filter(query)
        # Optional field filters from common search forms (status, type_id, ...)
        for key, value in request.GET.items():
            if key in ('page', 'page_size', 'q', 'search', 'id', 'subtype') or value in (None, ''):
                continue
            if hasattr(model, key):
                qs = qs.filter(**{key: value})
        return ok(paginate(qs, request, serializer))

    body, err = _parse_body(request)
    if err:
        return err

    if request.method == 'POST':
        try:
            obj = apply_create(user, body)
        except ValueError as exc:
            return fail('validation_error', str(exc), status=400)
        obj.save()
        return ok(serializer(obj), status=201)

    if request.method in ('PUT', 'PATCH'):
        try:
            obj_id = int(body.get('id'))
        except (TypeError, ValueError):
            return fail('validation_error', '缺少有效 id', status=400)
        obj = qs.filter(id=obj_id).first()
        if not obj:
            return fail('not_found', '记录不存在', status=404)
        try:
            apply_update(obj, user, body)
        except ValueError as exc:
            return fail('validation_error', str(exc), status=400)
        obj.save()
        return ok(serializer(obj))

    if request.method == 'DELETE':
        ids = _ids(body)
        if not ids:
            return fail('validation_error', '请提供要删除的 ids', status=400)
        deleted, _ = qs.filter(id__in=ids).delete()
        return ok({'deleted': deleted})

    return fail('method_not_allowed', '不支持的方法', status=405)


def _keyword_from_body(user, body):
    kid = body.get('company_keyword_id', body.get('company_keyword'))
    if kid in (None, '', 0, '0'):
        return None
    try:
        kid = int(kid)
    except (TypeError, ValueError) as exc:
        raise ValueError('关键词 ID 无效') from exc
    obj = CompanyKeyword.objects.filter(owner=user, id=kid).first()
    if not obj:
        raise ValueError('关联关键词不存在')
    return obj


def _article_type_from_body(user, body):
    tid = body.get('type_id', body.get('article_type'))
    if tid in (None, '', 0, '0'):
        return None
    try:
        tid = int(tid)
    except (TypeError, ValueError) as exc:
        raise ValueError('分类 ID 无效') from exc
    obj = ArticleType.objects.filter(owner=user, id=tid).first()
    if not obj:
        raise ValueError('文章分类不存在')
    return obj


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def keywords(request):
    def create(user, body):
        return CompanyKeyword(
            owner=user,
            keyword=_as_str(body.get('keyword'), required=True),
            hit_word=_as_str(body.get('hit_word'), required=False),
            tuozhan_status=_as_int(body.get('tuozhan_status'), default=0, min_value=0, max_value=1),
            zhengliu_question=_as_text(body.get('zhengliu_question'), required=False),
        )

    def update(obj, user, body):
        if 'keyword' in body:
            obj.keyword = _as_str(body.get('keyword'), required=True)
        if 'hit_word' in body:
            obj.hit_word = _as_str(body.get('hit_word'), required=False)
        if 'tuozhan_status' in body:
            obj.tuozhan_status = _as_int(body.get('tuozhan_status'), default=0, min_value=0, max_value=1)
        if 'zhengliu_question' in body:
            obj.zhengliu_question = _as_text(body.get('zhengliu_question'), required=False)

    return _list_or_mutate(
        request,
        model=CompanyKeyword,
        serializer=keyword_payload,
        search_fields=('keyword', 'hit_word'),
        apply_create=create,
        apply_update=update,
    )


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def questions(request):
    def create(user, body):
        return CompanyQuestion(
            owner=user,
            company_keyword=_keyword_from_body(user, body),
            question=_as_text(body.get('question'), required=True),
        )

    def update(obj, user, body):
        if 'company_keyword_id' in body or 'company_keyword' in body:
            obj.company_keyword = _keyword_from_body(user, body)
        if 'question' in body:
            obj.question = _as_text(body.get('question'), required=True)

    return _list_or_mutate(
        request,
        model=CompanyQuestion,
        serializer=question_payload,
        search_fields=('question',),
        apply_create=create,
        apply_update=update,
    )


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def article_types(request):
    def create(user, body):
        name = body.get('type_name', body.get('name'))
        return ArticleType(owner=user, type_name=_as_str(name, required=True, max_length=128))

    def update(obj, user, body):
        if 'type_name' in body or 'name' in body:
            name = body.get('type_name', body.get('name'))
            obj.type_name = _as_str(name, required=True, max_length=128)

    return _list_or_mutate(
        request,
        model=ArticleType,
        serializer=article_type_payload,
        search_fields=('type_name',),
        apply_create=create,
        apply_update=update,
    )


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def articles(request):
    def create(user, body):
        return Article(
            owner=user,
            title=_as_str(body.get('title'), required=True),
            article_type=_article_type_from_body(user, body),
            image_type_id=_as_int(body.get('image_type_id'), allow_none=True, required=False),
            content=_as_text(body.get('content'), required=False),
            status=_as_int(body.get('status'), default=1, min_value=0, max_value=2),
        )

    def update(obj, user, body):
        if 'title' in body:
            obj.title = _as_str(body.get('title'), required=True)
        if 'type_id' in body or 'article_type' in body:
            obj.article_type = _article_type_from_body(user, body)
        if 'image_type_id' in body:
            obj.image_type_id = _as_int(body.get('image_type_id'), allow_none=True, required=False)
        if 'content' in body:
            obj.content = _as_text(body.get('content'), required=False)
        if 'status' in body:
            obj.status = _as_int(body.get('status'), default=1, min_value=0, max_value=2)

    return _list_or_mutate(
        request,
        model=Article,
        serializer=article_payload,
        search_fields=('title',),
        apply_create=create,
        apply_update=update,
    )


@require_GET
def keyword_options(request):
    user, err = _user_or_401(request)
    if err:
        return err
    items = [
        {'id': item.id, 'label': item.keyword}
        for item in _owned(CompanyKeyword, user).order_by('-id')[:200]
    ]
    return ok({'items': items})


@require_GET
def article_type_options(request):
    user, err = _user_or_401(request)
    if err:
        return err
    items = [
        {'id': item.id, 'label': item.type_name}
        for item in _owned(ArticleType, user).order_by('-id')[:200]
    ]
    return ok({'items': items})
