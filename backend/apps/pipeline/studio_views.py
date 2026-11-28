"""Authenticated studio endpoints for the admin pages."""
from django.http import HttpResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.content.models import Article
from apps.core.responses import fail, ok, paginate, parse_json
from apps.modules.models import BizRecord

from .documents import extract_upload
from .models import LinkItem, PublishOrder, Topic
from .studio import (
    StudioError,
    articles_markdown,
    check_link,
    import_knowledge_text,
    link_payload,
    optimize_article,
    order_payload,
    save_competitors,
    save_link,
    save_order,
    save_topic,
    test_prompt,
    topic_payload,
    visibility_report,
)


def _user_or_401(request):
    if not request.user.is_authenticated:
        return None, fail('unauthenticated', '未登录', status=401)
    return request.user, None


def _body(request):
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
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            ids.append(number)
    return ids


@require_POST
def knowledge_import(request, record_id: int):
    user, err = _user_or_401(request)
    if err:
        return err
    record = BizRecord.objects.filter(owner=user, module='user_huaxiang', id=record_id).first()
    if not record:
        return fail('not_found', '知识库不存在', status=404)
    upload = request.FILES.get('file')
    if not upload:
        return fail('validation_error', '请选择文件', status=400)
    try:
        text = extract_upload(upload)
        count = import_knowledge_text(record, upload.name, text)
    except ValueError as exc:
        return fail('validation_error', str(exc), status=400)
    except StudioError as exc:
        return fail('validation_error', str(exc), status=400)
    return ok({'id': record.id, 'chunks': count, 'filename': upload.name})


@require_POST
def prompt_test(request):
    user, err = _user_or_401(request)
    if err:
        return err
    body, err = _body(request)
    if err:
        return err
    return ok(test_prompt(user, body))


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def topics(request):
    return _collection(request, Topic, topic_payload, save_topic, ('title',))


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def links(request):
    return _collection(request, LinkItem, link_payload, save_link, ('title', 'url', 'category'))


@require_POST
def link_check(request, link_id: int):
    user, err = _user_or_401(request)
    if err:
        return err
    item = LinkItem.objects.filter(owner=user, id=link_id).first()
    if not item:
        return fail('not_found', '链接不存在', status=404)
    return ok(link_payload(check_link(item)))


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def orders(request):
    return _collection(request, PublishOrder, order_payload, save_order, ('platform', 'status'))


@require_http_methods(['GET', 'POST'])
def visibility(request):
    user, err = _user_or_401(request)
    if err:
        return err
    if request.method == 'POST':
        body, err = _body(request)
        if err:
            return err
        save_competitors(user, str(body.get('competitors') or ''))
    return ok(visibility_report(user))


@require_GET
def article_export(request):
    user, err = _user_or_401(request)
    if err:
        return err
    raw = request.GET.get('ids') or ''
    ids = []
    for part in raw.split(','):
        try:
            number = int(part)
        except ValueError:
            continue
        if number > 0:
            ids.append(number)
    response = HttpResponse(articles_markdown(user, ids), content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="articles.md"'
    return response


@require_POST
def article_optimize(request, article_id: int):
    user, err = _user_or_401(request)
    if err:
        return err
    article = Article.objects.filter(owner=user, id=article_id).first()
    if not article:
        return fail('not_found', '文章不存在', status=404)
    article = optimize_article(article)
    return ok({
        'id': article.id,
        'status': article.status,
        'quality_score': article.quality_score,
        'quality_report': article.quality_report,
    })


def _collection(request, model, serializer, saver, search_fields):
    user, err = _user_or_401(request)
    if err:
        return err
    qs = model.objects.filter(owner=user)
    if request.method == 'GET':
        raw_id = request.GET.get('id')
        if raw_id not in (None, ''):
            obj = qs.filter(id=raw_id).first()
            if not obj:
                return fail('not_found', '记录不存在', status=404)
            return ok(serializer(obj))
        q = (request.GET.get('q') or '').strip()
        if q:
            from django.db.models import Q
            query = Q()
            for field in search_fields:
                query |= Q(**{f'{field}__icontains': q})
            qs = qs.filter(query)
        return ok(paginate(qs, request, serializer))
    body, err = _body(request)
    if err:
        return err
    if request.method == 'POST':
        try:
            obj = saver(user, body)
        except StudioError as exc:
            return fail('validation_error', str(exc), status=400)
        return ok(serializer(obj), status=201)
    if request.method in ('PUT', 'PATCH'):
        obj = qs.filter(id=body.get('id')).first()
        if not obj:
            return fail('not_found', '记录不存在', status=404)
        try:
            obj = saver(user, body, obj)
        except StudioError as exc:
            return fail('validation_error', str(exc), status=400)
        return ok(serializer(obj))
    ids = _ids(body)
    if not ids:
        return fail('validation_error', '请提供要删除的 ids', status=400)
    deleted, _detail = qs.filter(id__in=ids).delete()
    return ok({'deleted': deleted})
