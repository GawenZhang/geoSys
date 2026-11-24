"""Split enterprise knowledge records into retrievable chunks."""
import re

from django.db import transaction

from .models import KnowledgeChunk

SECTIONS = (
    ('company_name', '公司名'),
    ('company_other_name', '品牌简称'),
    ('product', '产品服务'),
    ('tese', '产品特点'),
    ('gushi', '品牌故事'),
    ('tongdian', '用户痛点'),
    ('beishu', '信任背书'),
    ('anli', '客户案例'),
    ('other_info', '其他信息'),
    ('summary', '汇总信息'),
    ('imported', '导入文档'),
)

_CHUNK_SIZE = 500


def tokenize(text: str) -> set[str]:
    found = set()
    for word in re.findall(r'[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}', text or ''):
        token = word.lower()
        found.add(token)
        if re.fullmatch(r'[\u4e00-\u9fff]+', token) and len(token) > 2:
            for index in range(len(token) - 1):
                found.add(token[index:index + 2])
    return found


def _split_text(text: str) -> list[str]:
    cleaned = (text or '').strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in re.split(r'\n+', cleaned) if part.strip()]
    chunks = []
    buffer = ''
    for part in parts:
        if buffer and len(buffer) + len(part) + 1 > _CHUNK_SIZE:
            chunks.append(buffer)
            buffer = part
        else:
            buffer = f'{buffer}\n{part}'.strip()
    if buffer:
        chunks.append(buffer)
    return chunks


def sync_knowledge(record) -> int:
    """Rebuild chunks for one user_huaxiang record. Returns the chunk count."""
    if record.module != 'user_huaxiang':
        return 0
    data = record.data or {}
    rows = []
    for key, label in SECTIONS:
        for piece in _split_text(str(data.get(key) or '')):
            tokens = tokenize(piece)
            rows.append(KnowledgeChunk(
                owner_id=record.owner_id,
                source=record,
                section=label,
                text=piece,
                keywords=' '.join(sorted(tokens))[:2000],
            ))
    with transaction.atomic():
        KnowledgeChunk.objects.filter(source=record).delete()
        if rows:
            KnowledgeChunk.objects.bulk_create(rows)
    return len(rows)
