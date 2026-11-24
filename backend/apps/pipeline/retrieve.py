"""Keyword overlap retrieval over knowledge chunks. No vector store."""
from .knowledge import tokenize
from .models import KnowledgeChunk


def retrieve(owner, query: str, source_ids=None, limit: int = 6):
    tokens = tokenize(query)
    if not tokens:
        return []
    qs = KnowledgeChunk.objects.filter(owner=owner)
    if source_ids:
        qs = qs.filter(source_id__in=list(source_ids))
    scored = []
    for chunk in qs.iterator():
        overlap = tokens & tokenize(chunk.text)
        if not overlap:
            continue
        scored.append((len(overlap), chunk.id, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit]]
