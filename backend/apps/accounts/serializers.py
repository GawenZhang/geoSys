def user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'nickname': user.nickname or user.username,
        'avatar': user.avatar or '',
        'balance': float(getattr(user, 'balance', 0) or 0),
        'score': int(getattr(user, 'score', 0) or 0),
        'unlimited': bool(getattr(user, 'is_unlimited', lambda: False)()),
        'is_staff': user.is_staff,
    }
