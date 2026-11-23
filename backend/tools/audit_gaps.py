import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.conf import settings
from django.test import Client

from apps.modules.registry import MODULES, resolve_page

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

manifest = json.loads((ROOT / 'app' / 'backend-page-manifest.json').read_text(encoding='utf-8'))
keys = sorted({item['key'] for item in manifest})

mapped = []
for key in keys:
    module, subtype = resolve_page(key)
    if key in ('dashboard', 'general-profile') or key.startswith(('company_keyword', 'company_question', 'article_type', 'article')):
        mapped.append((key, 'dedicated', '', ''))
    elif module:
        mapped.append((key, 'generic', module, subtype or ''))
    else:
        mapped.append((key, 'UNMAPPED', '', ''))

client = Client(enforce_csrf_checks=False)
login = client.post(
    '/api/auth/login',
    data=json.dumps({'username': 'demo', 'password': 'demo123'}),
    content_type='application/json',
)

endpoint_results = []
for path, method, payload in [
    ('/api/health', 'GET', None),
    ('/api/auth/me', 'GET', None),
    ('/api/keywords/', 'GET', None),
    ('/api/questions/', 'GET', None),
    ('/api/articles/', 'GET', None),
    ('/api/article-types/', 'GET', None),
    ('/api/modules/', 'GET', None),
    ('/api/modules/zhiling/', 'GET', None),
    ('/api/ai', 'POST', {'operation': 'generate', 'input': {'page': 'ai_image-add', 'fields': {'prompt': 'x'}}}),
]:
    if method == 'GET':
        response = client.get(path)
    else:
        response = client.post(path, data=json.dumps(payload), content_type='application/json')
    body = response.json()
    endpoint_results.append({
        'path': path,
        'status': response.status_code,
        'ok': body.get('ok'),
        'error': (body.get('error') or {}).get('code'),
        'ai_status_hint': (body.get('error') or {}).get('message') if path == '/api/ai' else None,
    })

module_fail = []
for module in MODULES:
    response = client.get(f'/api/modules/{module}/')
    body = response.json()
    if response.status_code != 200 or not body.get('ok'):
        module_fail.append(module)

pages = ROOT / 'app' / 'backend-pages'
no_table = []
has_file = []
has_ueditor = []
catalog_like = []
for path in sorted(pages.glob('*.html')):
    if path.name.endswith('.mobile.html'):
        continue
    key = path.stem
    html = path.read_text(encoding='utf-8', errors='ignore')
    if 'type="file"' in html or 'faupload' in html:
        has_file.append(key)
    if 'edui-editor' in html or 'ueditor' in html.lower():
        has_ueditor.append(key)
    if any(token in key for token in ('-add', '-edit', '-tougao', '-settle', '-configure')):
        continue
    if 'fixed-table-body' not in html and 'id="table"' not in html:
        no_table.append(key)
    if key in ('b2b', 'webmedia', 'zimedia', 'weixinapp2', 'quanyi', 'agent_skill'):
        catalog_like.append(key)

print(json.dumps({
    'login_ok': login.json().get('ok'),
    'pages_total': len(keys),
    'mapped_dedicated': sum(1 for row in mapped if row[1] == 'dedicated'),
    'mapped_generic': sum(1 for row in mapped if row[1] == 'generic'),
    'unmapped': [row[0] for row in mapped if row[1] == 'UNMAPPED'],
    'modules_total': len(MODULES),
    'modules_list_fail': module_fail,
    'endpoints': endpoint_results,
    'list_pages_without_table': no_table,
    'catalog_like_pages': catalog_like,
    'pages_with_file_upload': has_file,
    'pages_with_ueditor': has_ueditor,
    'known_frontend_gaps': [
        'third-party media publish / B2B real settlement still form-only (no external vendor APIs)',
        'wallet endpoint is demo ledger only (not WeChat/Alipay payment gateway)',
        'original-site PHP auth provider not replicated (session auth used instead)',
        'tougao/settle/configure pages save as module records but are not list views',
        'selectpage remote sources pointing at original /user/*/getList are not fully remapped',
    ],
    'recently_completed': [
        '/api/upload + /api/ueditor image upload',
        'edit form hydrate via ?id= / editId',
        'common search uses server q=',
        'btn-multi / btn-change persist status via API',
        '/api/dashboard live balance/score/chart',
        'AI_MODE=demo|proxy upstream',
        'keyword/article-type/images_type options auto-fill',
    ],
}, ensure_ascii=False, indent=2))
