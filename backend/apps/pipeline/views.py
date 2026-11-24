from django.views.decorators.http import require_GET, require_POST

from apps.core.responses import fail, ok
from apps.modules.models import BizRecord

from .publish import PublishError, publish_site_task
from .worker import PipelineError, execute_task


def _user_or_401(request):
    if not request.user.is_authenticated:
        return None, fail('unauthenticated', '未登录', status=401)
    return request.user, None


@require_POST
def run_task(request, task_id: int):
    from django.conf import settings

    user, err = _user_or_401(request)
    if err:
        return err
    task = BizRecord.objects.filter(owner=user, module='ai_task', id=task_id).first()
    if not task:
        return fail('not_found', '写作任务不存在', status=404)
    data = dict(task.data or {})
    try:
        count = int(data.get('max_count') or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(int(getattr(settings, 'PIPELINE_MAX_ARTICLES', 20)), count))
    data['max_count'] = count
    data['pipeline_status'] = 'queued'
    data['error'] = ''
    task.data = data
    task.status = 0
    task.save(update_fields=['data', 'status', 'updated_at'])
    inline_limit = int(getattr(settings, 'PIPELINE_INLINE_LIMIT', 3))
    if count > inline_limit:
        return ok({
            'id': task.id,
            'pipeline_status': 'queued',
            'success_count': 0,
            'error': '',
            'message': '任务已排队，请运行 python manage.py run_pipeline',
        })
    try:
        return ok(execute_task(task.id))
    except PipelineError as exc:
        return fail('pipeline_error', str(exc), status=400)


@require_POST
def publish_task(request, task_id: int):
    user, err = _user_or_401(request)
    if err:
        return err
    try:
        return ok(publish_site_task(task_id, user))
    except PublishError as exc:
        return fail('publish_error', str(exc), status=400)


@require_GET
def public_article(request, article_id: int):
    from .seo import article_page
    return article_page(request, article_id)
