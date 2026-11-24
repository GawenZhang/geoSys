from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import transaction
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.responses import fail, ok, parse_json
from apps.modules.models import BizRecord

from .serializers import user_payload


@ensure_csrf_cookie
@require_GET
def csrf(request):
    return ok({'csrfToken': get_token(request)})


@require_POST
def login_view(request):
    try:
        body = parse_json(request)
    except ValueError:
        return fail('invalid_json', '请求体必须是 JSON', status=400)

    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    keep = bool(body.get('keeplogin') or body.get('remember'))

    if not username or not password:
        return fail('validation_error', '请输入账号和密码', status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return fail('auth_failed', '演示账号或密码错误', status=401)
    if not user.is_active:
        return fail('auth_failed', '账号已禁用', status=403)

    login(request, user)
    if keep:
        request.session.set_expiry(60 * 60 * 24 * 30)
    else:
        request.session.set_expiry(0)
    return ok(user_payload(user))


@require_POST
def logout_view(request):
    logout(request)
    return ok({'logged_out': True})


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)
    return ok(user_payload(request.user))


@require_http_methods(['PUT', 'POST'])
def profile(request):
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)
    try:
        body = parse_json(request)
    except ValueError:
        return fail('invalid_json', '请求体必须是 JSON', status=400)

    user = request.user
    if 'nickname' in body:
        user.nickname = str(body.get('nickname') or '').strip()[:64]
    if 'avatar' in body:
        user.avatar = str(body.get('avatar') or '').strip()[:512]

    password = body.get('password')
    if password:
        password = str(password)
        if len(password) < 6:
            return fail('validation_error', '密码至少 6 位', status=400)
        user.set_password(password)

    user.save()
    if password:
        login(request, user)
    return ok(user_payload(user))


@require_POST
def wallet_adjust(request):
    """Demo wallet adjustment (local recharge / score grant). Not a real payment gateway."""
    if not request.user.is_authenticated:
        return fail('unauthenticated', '未登录', status=401)
    try:
        body = parse_json(request)
    except ValueError:
        return fail('invalid_json', '请求体必须是 JSON', status=400)

    kind = str(body.get('kind') or 'score').strip().lower()
    memo = str(body.get('memo') or '演示调整')[:255]
    try:
        amount = Decimal(str(body.get('amount') if body.get('amount') is not None else body.get('value') or 0))
    except (InvalidOperation, TypeError, ValueError):
        return fail('validation_error', 'amount 无效', status=400)
    if amount == 0:
        return fail('validation_error', 'amount 不能为 0', status=400)

    User = get_user_model()
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if user.is_unlimited():
            return ok(user_payload(user))
        if kind in ('money', 'balance'):
            user.balance = (user.balance or Decimal('0')) + amount
            if user.balance < 0:
                return fail('validation_error', '余额不足', status=400)
            BizRecord.objects.create(
                owner=user,
                module='user_money_log',
                title=memo,
                status=1,
                data={'money': float(amount), 'memo': memo, 'balance': float(user.balance)},
            )
        else:
            delta = int(amount)
            user.score = int(user.score or 0) + delta
            if user.score < 0:
                return fail('validation_error', '点数不足', status=400)
            BizRecord.objects.create(
                owner=user,
                module='user_score_log',
                title=memo,
                status=1,
                data={'score': delta, 'memo': memo, 'balance_score': user.score},
            )
        user.save()
    return ok(user_payload(user))
