def keyword_payload(obj):
    return {
        'id': obj.id,
        'keyword': obj.keyword,
        'hit_word': obj.hit_word,
        'tuozhan_status': obj.tuozhan_status,
        'zhengliu_question': obj.zhengliu_question,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }


def question_payload(obj):
    return {
        'id': obj.id,
        'company_keyword_id': obj.company_keyword_id,
        'company_keyword': obj.company_keyword.keyword if obj.company_keyword_id else '',
        'question': obj.question,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }


def article_type_payload(obj):
    return {
        'id': obj.id,
        'type_name': obj.type_name,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }


def article_payload(obj):
    from apps.pipeline.quality import release_block_reason

    report = obj.quality_report or {}
    return {
        'id': obj.id,
        'title': obj.title,
        'type_id': obj.article_type_id,
        'type_name': obj.article_type.type_name if obj.article_type_id else '',
        'image_type_id': obj.image_type_id,
        'content': obj.content,
        'status': obj.status,
        'task_id': obj.task_id,
        'question_id': obj.question_id,
        'quality_score': obj.quality_score,
        'quality_report': report,
        'quality_passed': obj.task_id is not None and release_block_reason(obj) == '',
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }
