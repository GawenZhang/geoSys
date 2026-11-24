"""Public reading pages and crawl files for approved articles and topics."""
import json
import re

from django.http import Http404, HttpResponse
from django.utils.html import escape

from apps.content.models import Article

from .models import Topic
from .studio import record_hit


def article_page(request, article_id: int):
    article = Article.objects.filter(id=article_id, status=Article.STATUS_NORMAL).select_related('article_type').first()
    if not article:
        raise Http404('文章不存在或尚未审核')
    record_hit(request, f'/p/{article.id}')
    return HttpResponse(_document(
        request,
        article.title,
        _plain(article.content)[:160],
        f'/p/{article.id}',
        'Article',
        _article_body(article),
    ))


def topic_page(request, topic_id: int):
    topic = Topic.objects.filter(id=topic_id, status=Topic.STATUS_PUBLISHED).first()
    if not topic:
        raise Http404('专题不存在或尚未发布')
    record_hit(request, f'/t/{topic.id}')
    items = list(topic.items.select_related('article').filter(article__status=Article.STATUS_NORMAL))
    return HttpResponse(_document(
        request,
        topic.title,
        (topic.summary or topic.title)[:160],
        f'/t/{topic.id}',
        'CollectionPage',
        _topic_body(topic, items),
    ))


def robots_txt(request):
    origin = request.build_absolute_uri('/').rstrip('/')
    body = (
        'User-agent: *\n'
        'Allow: /p/\n'
        'Allow: /t/\n'
        'Disallow: /api/\n'
        'Disallow: /user/\n'
        'Disallow: /admin/\n'
        'Disallow: /media/\n'
        f'Sitemap: {origin}/sitemap.xml\n'
    )
    return HttpResponse(body, content_type='text/plain; charset=utf-8')


def sitemap_xml(request):
    urls = _public_urls(request)
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        body.append(f'<url><loc>{escape(url)}</loc></url>')
    body.append('</urlset>')
    return HttpResponse('\n'.join(body), content_type='application/xml; charset=utf-8')


def sitemap_txt(request):
    return HttpResponse('\n'.join(_public_urls(request)) + '\n', content_type='text/plain; charset=utf-8')


def llms_txt(request):
    lines = ['# 已发布内容', '']
    for article in Article.objects.filter(status=Article.STATUS_NORMAL).order_by('-id')[:200]:
        lines.append(f'- [{article.title}]({request.build_absolute_uri(f"/p/{article.id}")})')
    for topic in Topic.objects.filter(status=Topic.STATUS_PUBLISHED).order_by('-id')[:100]:
        lines.append(f'- [{topic.title}]({request.build_absolute_uri(f"/t/{topic.id}")})')
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


def _public_urls(request) -> list[str]:
    urls = [request.build_absolute_uri(f'/p/{item.id}') for item in Article.objects.filter(status=Article.STATUS_NORMAL).order_by('id')[:500]]
    urls.extend(
        request.build_absolute_uri(f'/t/{item.id}')
        for item in Topic.objects.filter(status=Topic.STATUS_PUBLISHED).order_by('id')[:200]
    )
    return urls


def _article_body(article) -> str:
    category = escape(article.article_type.type_name) if article.article_type_id else ''
    category_html = f'<p class="meta">{category}</p>' if category else ''
    return f'<h1>{escape(article.title)}</h1>{category_html}<article>{_safe_html(article.content or "")}</article>'


def _topic_body(topic, items) -> str:
    summary = f'<p>{escape(topic.summary)}</p>' if topic.summary else ''
    if topic.layout == Topic.LAYOUT_TIMELINE:
        rows = ''.join(
            f'<li><time>{escape(item.article.created_at.date().isoformat())}</time> <a href="/p/{item.article_id}">{escape(item.article.title)}</a></li>'
            for item in items
        )
        listing = f'<ol class="timeline">{rows}</ol>'
    elif topic.layout == Topic.LAYOUT_GUIDE:
        rows = ''.join(
            f'<section><h2>{index}. {escape(item.article.title)}</h2><p><a href="/p/{item.article_id}">阅读原文</a></p></section>'
            for index, item in enumerate(items, start=1)
        )
        listing = rows or '<p>这个专题还没有可公开的文章。</p>'
    else:
        rows = ''.join(
            f'<a class="card" href="/p/{item.article_id}"><strong>{escape(item.article.title)}</strong></a>'
            for item in items
        )
        listing = f'<div class="cards">{rows}</div>'
    return f'<h1>{escape(topic.title)}</h1>{summary}{listing}'


def _document(request, title: str, description: str, path: str, schema_type: str, body: str) -> str:
    canonical = escape(request.build_absolute_uri(path))
    safe_title = escape(title)
    safe_description = escape(description or title)
    payload = json.dumps({
        '@context': 'https://schema.org',
        '@type': schema_type,
        'headline': title,
        'description': description or title,
        'url': request.build_absolute_uri(path),
    }, ensure_ascii=False)
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<meta name="description" content="{safe_description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="{safe_description}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">
<script type="application/ld+json">{payload}</script>
<style>
body{{margin:0;background:#f6f7fb;color:#1f2430;font:16px/1.75 "Segoe UI",sans-serif;}}
main{{max-width:760px;margin:40px auto;padding:32px;background:#fff;border-radius:12px;}}
h1{{font-size:28px;line-height:1.35;margin:0 0 8px;}}
.meta{{color:#667;margin-top:0;}}
img,.cards{{max-width:100%;}}
.cards{{display:grid;gap:12px;}}
.card{{display:block;padding:14px 16px;border:1px solid #e4e7f2;border-radius:10px;text-decoration:none;color:inherit;}}
</style>
</head>
<body><main>{body}</main></body>
</html>'''


def _safe_html(html: str) -> str:
    cleaned = re.sub(r'(?is)<script.*?>.*?</script>', '', html or '')
    cleaned = re.sub(r'(?i)\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', cleaned)
    cleaned = re.sub(r'(?i)javascript:', '', cleaned)
    return cleaned


def _plain(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()
