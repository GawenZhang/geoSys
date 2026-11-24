"""Turn an AI writing task into reviewed articles."""
import re

from django.conf import settings
from django.utils.html import escape

from apps.content.models import Article, ArticleType, CompanyKeyword, CompanyQuestion
from apps.modules.models import BizRecord

from .quality import content_hash, pass_score, score_article
from .retrieve import retrieve


class PipelineError(Exception):
    pass


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _id_list(raw) -> list[int]:
    if raw in (None, '', 0, '0'):
        return []
    if isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = re.split(r'[,，\s]+', str(raw))
    ids = []
    for value in values:
        number = _as_int(value, 0)
        if number > 0:
            ids.append(number)
    return ids


def _record(owner, module, record_id):
    number = _as_int(record_id, 0)
    if number <= 0:
        return None
    return BizRecord.objects.filter(owner=owner, module=module, id=number).first()


def _instruction(record) -> str:
    if not record:
        return ''
    data = record.data or {}
    return str(data.get('zhiling') or data.get('content') or data.get('prompt') or '').strip()


def _image_urls(owner, image_type_id, count: int, query: str = '') -> list[str]:
    if count <= 0 or _as_int(image_type_id, 0) <= 0:
        return []
    from .knowledge import tokenize

    type_id = _as_int(image_type_id, 0)
    wanted = tokenize(query)
    scored = []
    records = BizRecord.objects.filter(owner=owner, module='images_type')
    for record in records:
        data = record.data or {}
        linked = _as_int(data.get('images_type_id') or data.get('type_id'), 0)
        if record.id != type_id and linked != type_id:
            continue
        blob = ' '.join(str(data.get(key) or '') for key in ('title', 'name', 'remark', 'tags', 'alt', 'note'))
        blob = f'{record.title} {blob}'
        score = len(wanted & tokenize(blob)) if wanted else 0
        for url in _urls_in(data):
            scored.append((score, len(scored), url))
    scored.sort(key=lambda item: (-item[0], item[1]))
    deduped = []
    for _score, _order, url in scored:
        if url not in deduped:
            deduped.append(url)
    return deduped[:count]


def _urls_in(value) -> list[str]:
    found = []

    def walk(node, key=''):
        if isinstance(node, str):
            interesting = key in {
                'image', 'image_url', 'url', 'images', 'urls', 'files', 'image_urls',
            } or key.endswith('_url')
            if not interesting and key:
                return
            for part in re.split(r'[\s,，]+', node):
                if part.startswith(('http://', 'https://', '/media/')):
                    found.append(part)
            return
        if isinstance(node, list):
            for item in node:
                walk(item, key)
            return
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, str(child_key))

    walk(value, '')
    return found


def _insert_images(html: str, urls: list[str]) -> str:
    if not urls:
        return html
    tags = ''.join(f'<p><img src="{escape(url)}" alt=""></p>' for url in urls)
    return f'{html}{tags}'


def _demo_title(title: str, instruction: str) -> str:
    text = (instruction or '').strip()
    if not text:
        return title
    extra = text.splitlines()[0].strip()[:40]
    if not extra or extra in title:
        return title
    return f'{title}：{extra}'[:255]


def _demo_body(title: str, keyword: str, instruction: str, chunks) -> str:
    parts = [f'<p>{escape(title)}</p>']
    if keyword:
        parts.append(f'<p>蒸馏词：{escape(keyword)}</p>')
    for chunk in chunks:
        parts.append(f'<p>{escape(chunk.text)}</p>')
    if instruction:
        parts.append(f'<p>{escape(instruction)}</p>')
    if not chunks:
        parts.append('<p>本次未引用企业知识库，生成结果需要人工核对。</p>')
    return ''.join(parts)


def _model_text(system: str, user: str) -> str:
    from apps.ai.client import AiNotConfigured, complete_text

    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode == 'stub':
        raise PipelineError('AI 服务尚未接入，请先配置服务接口。')
    if mode == 'demo':
        raise PipelineError('demo')
    try:
        return complete_text(system, user)
    except AiNotConfigured as exc:
        raise PipelineError(str(exc)) from exc


def _write_title(title: str, instruction: str, keyword: str) -> str:
    if not instruction:
        return title[:255]
    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode != 'proxy':
        return _demo_title(title, instruction)
    text = _model_text(
        '你是标题编辑。根据指令改写标题，只输出一行标题，不要解释。',
        f'原标题：{title}\n蒸馏词：{keyword}\n指令：{instruction}',
    )
    line = (text or '').strip().splitlines()[0].strip()
    return (line or title)[:255]


def _write_body(title: str, keyword: str, instruction: str, chunks) -> str:
    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode != 'proxy':
        if mode == 'stub':
            raise PipelineError('AI 服务尚未接入，请先配置服务接口。')
        return _demo_body(title, keyword, instruction, chunks)
    context = '\n'.join(f'[{chunk.section}] {chunk.text}' for chunk in chunks) or '（未选择知识库）'
    system = (
        '你是企业内容写作助手。只依据给出的知识写作，不要编造知识里没有的数据、疗效或排名。'
        '输出 HTML 段落，不要使用 Markdown。'
    )
    user = (
        f'标题：{title}\n蒸馏词：{keyword}\n写作指令：{instruction or "写一篇可被引用的说明"}\n'
        f'知识：\n{context}'
    )
    text = _model_text(system, user).strip()
    if not text.startswith('<'):
        text = ''.join(f'<p>{escape(line)}</p>' for line in text.splitlines() if line.strip())
    return text


def _save_task(task, **fields):
    data = dict(task.data or {})
    data.update(fields)
    task.data = data
    if 'success_count' in fields:
        data['success_count'] = fields['success_count']
    task.save(update_fields=['data', 'status', 'title', 'updated_at'])


def execute_task(task_id: int) -> dict:
    task = BizRecord.objects.filter(module='ai_task', id=task_id).first()
    if not task:
        raise PipelineError('写作任务不存在')
    owner = task.owner
    data = dict(task.data or {})
    limit = getattr(settings, 'PIPELINE_MAX_ARTICLES', 20)
    max_count = min(limit, max(1, _as_int(data.get('max_count'), 1)))
    keyword = CompanyKeyword.objects.filter(owner=owner, id=_as_int(data.get('company_keyword_id'), 0)).first()
    if not keyword:
        data.update({
            'pipeline_status': 'failed',
            'success_count': 0,
            'error': '请选择蒸馏训练词',
        })
        task.data = data
        task.status = 2
        task.save(update_fields=['data', 'status', 'updated_at'])
        return {'id': task.id, 'pipeline_status': 'failed', 'success_count': 0, 'error': data['error'], 'article_ids': []}

    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode == 'stub':
        message = 'AI 服务尚未接入，请先配置服务接口。'
        data.update({'pipeline_status': 'failed', 'success_count': 0, 'error': message, 'keyword': keyword.keyword})
        task.data = data
        task.status = 2
        task.save(update_fields=['data', 'status', 'updated_at'])
        raise PipelineError(message)

    questions = list(
        CompanyQuestion.objects.filter(owner=owner, company_keyword=keyword).order_by('id')[:max_count]
    )
    topics = [(item.id, item.question.strip()) for item in questions if item.question and item.question.strip()]
    if not topics:
        topics = [(None, keyword.keyword)]
    topics = topics[:max_count]

    source_ids = _id_list(data.get('huaxiang_ids') or data.get('huaxiang_ids[]'))
    body_prompt = _instruction(_record(owner, 'zhiling', data.get('zhiling_id')))
    title_prompt = _instruction(_record(owner, 'zhiling', data.get('title_zhiling_id')))
    image_urls = _image_urls(
        owner,
        data.get('image_type_id'),
        _as_int(data.get('image_count'), 0),
        keyword.keyword,
    )
    desired_normal = _as_int(data.get('article_status'), 0) == 1
    article_type = _article_type(owner, data, task)

    data.update({
        'pipeline_status': 'running',
        'error': '',
        'keyword': keyword.keyword,
        'keywordgroup': {'keyword': keyword.keyword},
        'max_count': max_count,
        'is_knowledge': '是' if source_ids else '否',
        'success_count': 0,
    })
    task.data = data
    task.status = 0
    task.title = data.get('name') or task.title
    task.save(update_fields=['data', 'status', 'title', 'updated_at'])

    article_ids = []
    errors = []
    for question_id, raw_title in topics:
        try:
            title = _write_title(raw_title, title_prompt, keyword.keyword)
            query = ' '.join(part for part in (title, keyword.keyword, keyword.hit_word, body_prompt) if part)
            chunks = retrieve(owner, query, source_ids=source_ids or None, limit=6)
            html = _insert_images(_write_body(title, keyword.keyword, body_prompt, chunks), image_urls)
            score, report = score_article(title, html, chunks, keyword.keyword, bool(source_ids))
            status = Article.STATUS_PENDING
            if desired_normal and score >= pass_score() and not report.get('blocked') and report.get('passed'):
                status = Article.STATUS_NORMAL
            article = Article.objects.create(
                owner=owner,
                title=title[:255],
                article_type=article_type,
                image_type_id=_as_int(data.get('image_type_id'), 0) or None,
                content=html,
                status=status,
                task_id=task.id,
                question_id=question_id,
                quality_score=score,
                quality_report=report,
                content_hash=content_hash(html),
            )
            article_ids.append(article.id)
            data['success_count'] = len(article_ids)
            task.data = data
            task.save(update_fields=['data', 'updated_at'])
        except PipelineError as exc:
            errors.append(str(exc)[:200])
        except Exception as exc:
            errors.append(str(exc)[:200])

    status_name = 'done' if article_ids else 'failed'
    error = '；'.join(errors)[:500]
    data.update({
        'pipeline_status': status_name,
        'success_count': len(article_ids),
        'error': error,
    })
    task.data = data
    task.status = 1 if article_ids else 2
    task.save(update_fields=['data', 'status', 'updated_at'])
    return {
        'id': task.id,
        'pipeline_status': status_name,
        'success_count': len(article_ids),
        'error': error,
        'article_ids': article_ids,
    }


def _article_type(owner, data, task):
    type_id = _as_int(data.get('article_type_id') or data.get('type_id'), 0)
    if type_id > 0:
        found = ArticleType.objects.filter(owner=owner, id=type_id).first()
        if found:
            return found
    name = str(data.get('name') or task.title or '未命名任务').strip()[:128] or '未命名任务'
    article_type, _ = ArticleType.objects.get_or_create(owner=owner, type_name=name)
    return article_type


def queued_tasks():
    for task in BizRecord.objects.filter(module='ai_task').order_by('id'):
        if (task.data or {}).get('pipeline_status') == 'queued':
            yield task
