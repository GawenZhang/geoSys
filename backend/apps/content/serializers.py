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
    return {
        'id': obj.id,
        'title': obj.title,
        'type_id': obj.article_type_id,
        'type_name': obj.article_type.type_name if obj.article_type_id else '',
        'image_type_id': obj.image_type_id,
        'content': obj.content,
        'status': obj.status,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }
