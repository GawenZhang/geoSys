from django.views.decorators.http import require_GET

from .responses import ok


@require_GET
def health(request):
    return ok({'status': 'up', 'service': 'geoSys'})
