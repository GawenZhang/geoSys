"""Score an article against the knowledge that was supposed to support it."""
import hashlib
import json
import re

from django.conf import settings

from apps.modules.models import BizRecord

from .retrieve import retrieve

# Advertising-law style claims. A hit keeps the article in review.
BLOCKED_PHRASES = (
    '包治百病',
    '国家级',
    '最强',
    '第一名',
    '绝对有效',
    '根治',
    '无效退款',
)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def pass_score() -> int:
    try:
        return int(getattr(settings, 'QUALITY_PASS_SCORE', 70))
    except (TypeError, ValueError):
        return 70


def _blocked(text: str) -> list[str]:
    return [phrase for phrase in BLOCKED_PHRASES if phrase and phrase in (text or '')]


def _demo_score(title: str, content: str, chunks, keyword: str, knowledge_selected: bool = False) -> tuple[int, dict]:
    blob = f'{title}\n{content}'
    hits = _blocked(blob)
    if hits:
        return 25, {
            'score': 25,
            'passed': False,
            'blocked': True,
            'reason': '命中夸大或禁限表述：' + '、'.join(hits),
            'hits': hits,
        }
    matched = 0
    for chunk in chunks:
        snippet = (chunk.text or '').strip()[:24]
        if snippet and snippet in (content or ''):
            matched += 1
    threshold = pass_score()
    if chunks and matched:
        score = 86
        reason = f'引用了 {matched} 段知识库内容'
    elif chunks:
        score = 54
        reason = '未充分引用知识库，需人工审核'
    elif knowledge_selected:
        score = 58
        reason = '所选知识库与这个选题没有重合，需人工审核'
    else:
        score = 61
        reason = '未选择知识库，需人工审核'
    if keyword and keyword not in blob and score >= threshold:
        score = min(score, threshold - 1)
        reason = '正文未覆盖蒸馏词'
    passed = score >= threshold
    return score, {
        'score': score,
        'passed': passed,
        'blocked': False,
        'reason': reason,
        'matched_chunks': matched,
    }


def _proxy_score(title: str, content: str, chunks, keyword: str) -> tuple[int, dict]:
    from apps.ai.client import AiNotConfigured, complete_text

    context = '\n'.join(f'[{chunk.section}] {chunk.text}' for chunk in chunks) or '（无知识片段）'
    system = (
        '你是内容质检员。只根据给定知识判断文章是否被知识支撑、是否夸大承诺。'
        '返回 JSON：{"score":0到100的整数,"reason":"一句中文原因"}。'
        '知识里没有的疗效、排名、绝对化承诺必须低分。'
    )
    user = f'蒸馏词：{keyword}\n标题：{title}\n知识：\n{context}\n正文：\n{content[:4000]}'
    try:
        raw = complete_text(system, user)
    except AiNotConfigured:
        return 0, {
            'score': 0,
            'passed': False,
            'blocked': True,
            'reason': 'AI 服务尚未接入，无法质检',
        }
    score = None
    reason = '质检未返回可用分数'
    match = re.search(r'\{.*\}', raw or '', re.S)
    if match:
        try:
            payload = json.loads(match.group(0))
            score = int(payload.get('score'))
            reason = str(payload.get('reason') or reason)[:300]
        except (TypeError, ValueError, json.JSONDecodeError):
            score = None
    if score is None:
        digits = re.search(r'\d{1,3}', raw or '')
        score = int(digits.group(0)) if digits else 0
    score = max(0, min(100, score))
    hits = _blocked(f'{title}\n{content}')
    if hits:
        score = min(score, 25)
        reason = '命中夸大或禁限表述：' + '、'.join(hits)
    passed = score >= pass_score() and not hits
    return score, {
        'score': score,
        'passed': passed,
        'blocked': bool(hits) or not passed,
        'reason': reason,
        'hits': hits,
    }


def score_article(title: str, content: str, chunks, keyword: str, knowledge_selected: bool = False) -> tuple[int, dict]:
    mode = getattr(settings, 'AI_MODE', 'stub')
    if mode == 'proxy':
        return _proxy_score(title, content, chunks, keyword)
    return _demo_score(title, content, chunks, keyword, knowledge_selected)


def _task_chunks(article):
    if not article.task_id:
        return []
    task = BizRecord.objects.filter(owner_id=article.owner_id, module='ai_task', id=article.task_id).first()
    if not task:
        return []
    data = task.data or {}
    source_ids = _id_list(data.get('huaxiang_ids') or data.get('huaxiang_ids[]'))
    query = ' '.join([
        article.title or '',
        str(data.get('keyword') or ''),
        str(data.get('name') or ''),
    ])
    return retrieve(article.owner, query, source_ids=source_ids or None, limit=6)


def _id_list(raw) -> list[int]:
    if raw in (None, '', 0, '0'):
        return []
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = str(raw).replace('，', ',').split(',')
    ids = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            ids.append(number)
    return ids


def assess_article(article) -> tuple[int, dict]:
    keyword = ''
    if article.task_id:
        task = BizRecord.objects.filter(id=article.task_id, owner_id=article.owner_id).first()
        if task:
            keyword = str((task.data or {}).get('keyword') or '')
    chunks = _task_chunks(article)
    selected = False
    if article.task_id:
        task = BizRecord.objects.filter(id=article.task_id, owner_id=article.owner_id).first()
        if task:
            selected = bool(_id_list((task.data or {}).get('huaxiang_ids') or (task.data or {}).get('huaxiang_ids[]')))
    return score_article(article.title, article.content, chunks, keyword, selected)


def release_block_reason(article) -> str:
    """Why a pipeline article cannot be switched to 正常. Empty string means allowed."""
    if not getattr(article, 'task_id', None):
        return ''
    report = article.quality_report or {}
    if report.get('stale'):
        return str(report.get('reason') or '正文已修改，请重新质检后再放行')
    if report.get('blocked'):
        return str(report.get('reason') or '质检未通过')
    if article.quality_score is None:
        return '尚未完成质检，不能直接放行'
    threshold = pass_score()
    if int(article.quality_score) < threshold:
        return f'质检 {article.quality_score} 分，未达到放行分数 {threshold}'
    return ''
