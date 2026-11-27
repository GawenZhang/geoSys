"""Topics, link checks, manual publish orders, visibility and prompt trials."""
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.content.models import Article, CompanyKeyword
from apps.modules.models import BizRecord

from .knowledge import sync_knowledge
from .models import LinkItem, PageHit, PublishOrder, Topic, TopicArticle, VisibilityNote
from .publish import PublishError, _is_public_http
from .quality import assess_article, content_hash, pass_score
from .retrieve import retrieve
from .worker import _demo_body, _instruction, _model_text, _record

_PLATFORMS = {
    'toutiao': '头条号',
    'sohu': '搜狐号',
    'netease': '网易号',
}
_ORDER_NEXT = {
    'pending': {'claimed', 'rejected'},
    'claimed': {'submitted', 'rejected'},
    'submitted': {'confirmed', 'rejected'},
    'confirmed': set(),
    'rejected': set(),
}
_ORDER_LABEL = {
    'pending': '待领取',
    'claimed': '已领取',
    'submitted': '已回执',
    'confirmed': '已确认',
    'rejected': '已退回',
}
_LAYOUTS = {
    Topic.LAYOUT_CARD: '标准卡片',
    Topic.LAYOUT_GUIDE: '阅读指南',
    Topic.LAYOUT_TIMELINE: '时间汇总',
}
_CRAWLERS = (
    'gptbot', 'claudebot', 'google-extended', 'bytespider', 'ccbot', 'perplexitybot',
    'amazonbot', 'applebot-extended', 'bingbot', 'baiduspider', 'googlebot',
)


class StudioError(Exception):
    pass


def import_knowledge_text(record, filename: str, text: str) -> int:
    return append_knowledge_sources(record, [(filename, text)])


def append_knowledge_sources(record, sources) -> int:
    if record.module != 'user_huaxiang':
        raise StudioError('只能导入到企业知识库')
    with transaction.atomic():
        record = BizRecord.objects.select_for_update().get(pk=record.pk)
        data = dict(record.data or {})
        blocks = [str(data.get('imported') or '').strip()]
        blocks.extend(f'【{filename}】\n{text.strip()}' for filename, text in sources)
        data['imported'] = '\n\n'.join(filter(None, blocks))
        record.data = data
        record.save(update_fields=['data', 'updated_at'])
        return sync_knowledge(record)


def test_prompt(owner, body: dict) -> dict:
    title = str(body.get('title') or body.get('keyword') or '试写标题').strip()[:255]
    keyword = ''
    keyword_id = body.get('company_keyword_id') or body.get('keyword_id')
    if keyword_id:
        row = CompanyKeyword.objects.filter(owner=owner, id=keyword_id).first()
        keyword = row.keyword if row else ''
    keyword = str(body.get('keyword') or keyword).strip()
    if not title:
        title = keyword or '试写标题'
    instruction = str(body.get('zhiling') or '').strip()
    if not instruction:
        instruction = _instruction(_record(owner, 'zhiling', body.get('zhiling_id')))
    source_id = body.get('huaxiang_id') or body.get('huaxiang_ids')
    source_ids = source_id if isinstance(source_id, list) else ([source_id] if source_id else None)
    chunks = retrieve(owner, f'{title}\n{keyword}\n{instruction}', source_ids=source_ids, limit=4)
    from django.conf import settings

    if getattr(settings, 'AI_MODE', 'stub') == 'proxy':
        context = '\n'.join(f'[{chunk.section}] {chunk.text}' for chunk in chunks) or '（没有检索到知识）'
        html = _model_text(
            '只依据给出的知识写一段 HTML，不要编造数据。',
            f'标题：{title}\n蒸馏词：{keyword}\n指令：{instruction or "写一段说明"}\n知识：\n{context}',
        )
    else:
        html = _demo_body(title, keyword, instruction, chunks)
    score, report = assess_preview(title, html, chunks, keyword, bool(source_ids))
    return {
        'title': title,
        'html': html,
        'quality_score': score,
        'quality_report': report,
        'chunks': [{'section': chunk.section, 'text': chunk.text[:180]} for chunk in chunks],
        'saved': False,
    }


def assess_preview(title, html, chunks, keyword, selected):
    from .quality import score_article

    return score_article(title, html, chunks, keyword, selected)


def optimize_article(article) -> Article:
    text = article.content or ''
    from .quality import BLOCKED_PHRASES

    for phrase in BLOCKED_PHRASES:
        text = text.replace(phrase, '')
    score, report = assess_article(_preview_article(article, text))
    if not report.get('passed'):
        chunks = _article_chunks(article)
        for chunk in chunks:
            snippet = (chunk.text or '').strip()
            if snippet and snippet[:24] not in text:
                text += f'<p>{snippet}</p>'
                break
        score, report = assess_article(_preview_article(article, text))
    article.content = text
    article.quality_score = score
    article.quality_report = report
    article.content_hash = content_hash(text)
    if article.task_id and report.get('passed') and score >= pass_score() and not report.get('blocked'):
        article.status = Article.STATUS_NORMAL
    article.save(update_fields=['content', 'quality_score', 'quality_report', 'content_hash', 'status', 'updated_at'])
    return article


def _preview_article(article, content):
    article.content = content
    return article


def _article_chunks(article):
    if not article.task_id:
        return []
    task = BizRecord.objects.filter(id=article.task_id, owner_id=article.owner_id).first()
    if not task:
        return []
    data = task.data or {}
    return retrieve(
        article.owner,
        f'{article.title}\n{data.get("keyword") or ""}',
        source_ids=data.get('huaxiang_ids') or data.get('huaxiang_ids[]'),
        limit=3,
    )


def topic_payload(topic: Topic) -> dict:
    return {
        'id': topic.id,
        'title': topic.title,
        'summary': topic.summary,
        'layout': topic.layout,
        'layout_label': _LAYOUTS.get(topic.layout, topic.layout),
        'status': topic.status,
        'status_label': '已发布' if topic.status == Topic.STATUS_PUBLISHED else '草稿',
        'article_ids': ','.join(str(item.article_id) for item in topic.items.all()),
        'article_count': topic.items.count(),
        'group_name': '',
        'created_at': topic.created_at.isoformat(),
    }


def save_topic(owner, body: dict, topic: Topic | None = None) -> Topic:
    title = str(body.get('title') or '').strip()
    if not title:
        raise StudioError('请填写专题标题')
    layout = str(body.get('layout') or Topic.LAYOUT_CARD)
    if layout not in _LAYOUTS:
        layout = Topic.LAYOUT_CARD
    try:
        status = int(body.get('status') if body.get('status') not in (None, '') else Topic.STATUS_DRAFT)
    except (TypeError, ValueError):
        status = Topic.STATUS_DRAFT
    status = Topic.STATUS_PUBLISHED if status == Topic.STATUS_PUBLISHED else Topic.STATUS_DRAFT
    article_ids = _id_list(body.get('article_ids'))
    articles = list(Article.objects.filter(owner=owner, id__in=article_ids))
    if status == Topic.STATUS_PUBLISHED:
        if not articles:
            raise StudioError('发布专题前请选择已审核文章')
        pending = [item.title for item in articles if item.status != Article.STATUS_NORMAL]
        if pending:
            raise StudioError('这些文章还不能公开：' + '、'.join(pending[:5]))
    if topic is None:
        topic = Topic(owner=owner)
    topic.title = title[:200]
    topic.summary = str(body.get('summary') or '')[:4000]
    topic.layout = layout
    topic.status = status
    topic.save()
    if 'article_ids' in body:
        group = str(body.get('group_name') or '')[:64]
        topic.items.all().delete()
        TopicArticle.objects.bulk_create([
            TopicArticle(topic=topic, article=article, group_name=group, sort=index)
            for index, article in enumerate(articles)
        ])
    return topic


def link_payload(item: LinkItem) -> dict:
    labels = {0: '未检查', 1: '可访问', 2: '不可访问'}
    return {
        'id': item.id,
        'title': item.title,
        'url': item.url,
        'category': item.category,
        'keywords': item.keywords,
        'status': item.status,
        'status_label': labels.get(item.status, ''),
        'last_status': item.last_status,
        'created_at': item.created_at.isoformat(),
    }


def save_link(owner, body: dict, item: LinkItem | None = None) -> LinkItem:
    title = str(body.get('title') or '').strip()
    url = str(body.get('url') or '').strip()
    if not title or not url:
        raise StudioError('请填写链接标题和地址')
    try:
        _is_public_http(url)
    except PublishError as exc:
        raise StudioError(str(exc)) from exc
    if item is None:
        item = LinkItem(owner=owner)
    item.title = title[:200]
    item.url = url[:500]
    item.category = str(body.get('category') or '')[:64]
    item.keywords = str(body.get('keywords') or '')[:200]
    item.save()
    return item


def check_link(item: LinkItem) -> LinkItem:
    try:
        _is_public_http(item.url)
        request = urllib.request.Request(item.url, method='GET', headers={'User-Agent': 'geoSys-link-check'})
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=6) as response:
            code = getattr(response, 'status', 200)
        item.status = LinkItem.STATUS_HEALTHY if 200 <= code < 400 else LinkItem.STATUS_FAILED
        item.last_status = str(code)
    except (PublishError, urllib.error.URLError, TimeoutError, OSError) as exc:
        item.status = LinkItem.STATUS_FAILED
        item.last_status = str(exc)[:80]
    item.last_checked = timezone.now()
    item.save(update_fields=['status', 'last_status', 'last_checked'])
    return item


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def order_payload(order: PublishOrder) -> dict:
    return {
        'id': order.id,
        'title': order.article.title,
        'article_id': order.article_id,
        'platform': order.platform,
        'platform_label': _PLATFORMS.get(order.platform, order.platform),
        'status': order.status,
        'status_label': _ORDER_LABEL.get(order.status, order.status),
        'note': order.note,
        'receipt': order.receipt,
        'created_at': order.created_at.isoformat(),
    }


def save_order(owner, body: dict, order: PublishOrder | None = None) -> PublishOrder:
    platform = str(body.get('platform') or '')
    if order is None:
        if platform not in _PLATFORMS:
            raise StudioError('平台只支持头条号、搜狐号、网易号')
        try:
            article_id = int(body.get('article_id'))
        except (TypeError, ValueError):
            raise StudioError('请选择文章')
        article = Article.objects.filter(owner=owner, id=article_id).first()
        if not article:
            raise StudioError('文章不存在')
        if article.status != Article.STATUS_NORMAL:
            raise StudioError('只有已审核文章可以进入人工发布')
        order = PublishOrder(owner=owner, article=article, platform=platform, status='pending')
    else:
        next_status = str(body.get('status') or order.status)
        if next_status != order.status and next_status not in _ORDER_NEXT.get(order.status, set()):
            raise StudioError(f'不能从{_ORDER_LABEL.get(order.status, order.status)}直接改为{_ORDER_LABEL.get(next_status, next_status)}')
        order.status = next_status
        if 'platform' in body and body.get('platform') in _PLATFORMS:
            order.platform = body.get('platform')
    if 'note' in body:
        order.note = str(body.get('note') or '')[:2000]
    if 'receipt' in body:
        order.receipt = str(body.get('receipt') or '')[:2000]
    order.save()
    return order


def record_hit(request, path: str) -> None:
    agent = (request.META.get('HTTP_USER_AGENT') or '')[:180]
    kind = 'crawler' if any(name in agent.lower() for name in _CRAWLERS) else 'visit'
    PageHit.objects.create(path=path[:200], kind=kind, user_agent=agent)


def visibility_report(owner) -> dict:
    note, _created = VisibilityNote.objects.get_or_create(owner=owner)
    keywords = []
    for keyword in CompanyKeyword.objects.filter(owner=owner).order_by('id')[:50]:
        articles = Article.objects.filter(owner=owner, title__icontains=keyword.keyword)
        scores = [item.quality_score for item in articles if item.quality_score is not None]
        keywords.append({
            'keyword': keyword.keyword,
            'articles': articles.count(),
            'published': articles.filter(status=Article.STATUS_NORMAL).count(),
            'avg_score': round(sum(scores) / len(scores)) if scores else None,
        })
    topics = [
        {'id': topic.id, 'title': topic.title, 'status_label': '已发布' if topic.status else '草稿', 'articles': topic.items.count()}
        for topic in Topic.objects.filter(owner=owner)[:30]
    ]
    words = Counter()
    for article in Article.objects.filter(owner=owner).only('title')[:200]:
        for token in re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}', article.title or ''):
            words[token.lower()] += 1
    since = timezone.now() - timedelta(days=7)
    hits = PageHit.objects.filter(created_at__gte=since)
    return {
        'keywords': keywords,
        'topics': topics,
        'words': [{'word': word, 'count': count} for word, count in words.most_common(20)],
        'sources': [
            {'title': item.title, 'url': f'/p/{item.id}'}
            for item in Article.objects.filter(owner=owner, status=Article.STATUS_NORMAL).order_by('-id')[:20]
        ],
        'visits': {
            'pages': hits.filter(kind='visit').count(),
            'crawlers': hits.filter(kind='crawler').count(),
        },
        'competitors': note.competitors,
    }


def save_competitors(owner, text: str) -> str:
    note, _created = VisibilityNote.objects.get_or_create(owner=owner)
    note.competitors = (text or '')[:2000]
    note.save(update_fields=['competitors', 'updated_at'])
    return note.competitors


def articles_markdown(owner, ids) -> str:
    qs = Article.objects.filter(owner=owner).order_by('-id')
    if ids:
        qs = qs.filter(id__in=ids)
    else:
        qs = qs.filter(status=Article.STATUS_NORMAL)
    blocks = []
    for article in qs[:50]:
        plain = re.sub(r'<[^>]+>', '', article.content or '')
        blocks.append(f'# {article.title}\n\n{plain.strip()}\n')
    return '\n---\n\n'.join(blocks) or '# 没有可导出的文章\n'


def _id_list(raw) -> list[int]:
    if raw in (None, '', []):
        return []
    values = raw if isinstance(raw, list) else str(raw).replace('，', ',').split(',')
    ids = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            ids.append(number)
    return ids
