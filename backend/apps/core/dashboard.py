"""Dashboard stats for the homepage."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.content.models import Article, CompanyKeyword, CompanyQuestion
from apps.core.responses import fail, ok
from apps.modules.models import BizRecord


def _month_start():
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@require_GET
def dashboard(request):
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)

    user = request.user
    month_start = _month_start()
    days = []
    counts = []
    for offset in range(6, -1, -1):
        day = (timezone.now() - timedelta(days=offset)).date()
        days.append(day.strftime('%m-%d'))
        day_start = timezone.make_aware(datetime.combine(day, time.min))
        day_end = day_start + timedelta(days=1)
        counts.append(
            BizRecord.objects.filter(owner=user, created_at__gte=day_start, created_at__lt=day_end).count()
            + Article.objects.filter(owner=user, created_at__gte=day_start, created_at__lt=day_end).count()
        )

    money_qs = BizRecord.objects.filter(owner=user, module='user_money_log', created_at__gte=month_start)
    score_qs = BizRecord.objects.filter(owner=user, module='user_score_log', created_at__gte=month_start)
    month_money = Decimal('0')
    month_score = 0
    for row in money_qs:
        try:
            month_money += Decimal(str((row.data or {}).get('money') or 0))
        except Exception:
            pass
    for row in score_qs:
        try:
            month_score += int((row.data or {}).get('score') or 0)
        except (TypeError, ValueError):
            pass

    module_counts = list(
        BizRecord.objects.filter(owner=user)
        .values('module')
        .annotate(count=Count('id'))
        .order_by('-count')[:8]
    )

    return ok({
        'user': {
            'id': user.id,
            'username': user.username,
            'nickname': user.nickname or user.username,
            'avatar': user.avatar or '',
            'balance': float(user.balance),
            'score': int(user.score),
            'unlimited': bool(user.is_unlimited()),
        },
        'stats': {
            'keywords': CompanyKeyword.objects.filter(owner=user).count(),
            'questions': CompanyQuestion.objects.filter(owner=user).count(),
            'articles': Article.objects.filter(owner=user).count(),
            'records': BizRecord.objects.filter(owner=user).count(),
            'month_money_delta': float(month_money),
            'month_score_delta': month_score,
        },
        'chart': {
            'labels': days,
            'series': counts,
        },
        'modules': module_counts,
    })
