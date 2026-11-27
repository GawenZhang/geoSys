"""Knowledge intake and manually observed AI answers for the GEO workflow."""
from django import forms
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.responses import fail, ok, paginate
from apps.modules.models import BizRecord

from .documents import MAX_BYTES, MAX_CHARS, extract_upload
from .measurement import hostname, is_owned, matched_questions
from .studio import append_knowledge_sources
from .studio_views import _body, _user_or_401

OBSERVATION_MODULE = 'geo_observation'


class KnowledgeForm(forms.Form):
    record_id = forms.IntegerField(required=False, min_value=1)
    name = forms.CharField(required=False, max_length=255, label='知识库名称')
    company_name = forms.CharField(required=False, max_length=255, label='企业名称')
    text = forms.CharField(required=False, max_length=MAX_CHARS, label='资料正文')
    file = forms.FileField(required=False, label='资料文件')


class ObservationForm(forms.Form):
    id = forms.IntegerField(required=False, min_value=1)
    trial = forms.CharField(required=False, max_length=120, label='试点名称')
    brand = forms.CharField(max_length=120, label='品牌')
    platform = forms.CharField(max_length=80, label='平台')
    surface = forms.CharField(max_length=80, label='入口和模式')
    phase = forms.ChoiceField(choices=[('baseline', '基线'), ('retest', '复测')], label='阶段')
    intent = forms.ChoiceField(choices=[('category', '品类问题'), ('brand', '品牌问题')], label='问题类型')
    cohort = forms.ChoiceField(
        required=False, choices=[('target', '优化组'), ('holdout', '观察组')], label='试点分组',
    )
    question = forms.CharField(max_length=1000, label='原始问题')
    observed_at = forms.DateTimeField(required=False, label='采样时间')
    outcome = forms.ChoiceField(choices=[('answer', '有效回答'), ('failed', '采集失败')], label='采集结果')
    answer = forms.CharField(required=False, max_length=30000, label='完整回答或失败说明')
    citations = forms.CharField(required=False, max_length=10000, label='引用网址')
    citation_status = forms.ChoiceField(
        choices=[('yes', '引用已知'), ('no', '确认无引用'), ('unknown', '无法判定')], label='引用状态',
    )
    owned_site = forms.CharField(required=False, max_length=255, label='品牌官网域名')
    mentioned = forms.BooleanField(required=False)
    recommended = forms.BooleanField(required=False)

    def clean(self):
        values = super().clean()
        if self.errors:
            return values
        if values['cohort'] and not values['trial']:
            self.add_error('trial', '设置试点分组时，请填写试点名称。')
            return values
        values['observed_at'] = (values['observed_at'] or timezone.now()).isoformat()
        if not values['answer']:
            raise forms.ValidationError('请填写完整回答或失败说明。')
        if values['outcome'] == 'failed':
            values.update(citations=[], citation_status='unknown', owned_site='', mentioned=False,
                          recommended=False, own_cited=False)
            return values

        citation_status = values['citation_status']
        urls = list(dict.fromkeys(line.strip() for line in values['citations'].splitlines() if line.strip()))
        if citation_status == 'yes' and not urls:
            self.add_error('citations', '请填写回答里实际显示的引用网址。')
        if urls and citation_status != 'yes':
            self.add_error('citation_status', '填写了引用网址时请选择「已取得引用链接」。')
        validate_url = URLValidator(schemes=['http', 'https'])
        hosts = []
        for url in urls:
            if not url.lower().startswith(('http://', 'https://')):
                self.add_error('citations', '每行填写一个以 http:// 或 https:// 开头的完整网址。')
                break
            try:
                validate_url(url)
                hosts.append(hostname(url))
            except forms.ValidationError:
                self.add_error('citations', '引用网址格式不正确。')
                break
        domain = values['owned_site']
        if citation_status != 'unknown':
            try:
                url = domain if '://' in domain else f'https://{domain}'
                validate_url(url)
                domain = hostname(url)
            except forms.ValidationError:
                self.add_error('owned_site', '引用状态可判定时，请填写有效的品牌官网域名。')
        values['owned_site'] = domain
        values['citations'] = urls
        values['own_cited'] = any(is_owned(host, domain) for host in hosts)
        values['mentioned'] = values['mentioned'] or values['recommended']
        return values


def _invalid_form(form):
    field, errors = next(iter(form.errors.items()))
    label = form.fields[field].label if field in form.fields else None
    return fail('validation_error', f'{label}：{errors[0]}' if label else str(errors[0]))


@require_http_methods(['GET', 'POST'])
def knowledge(request):
    user, error = _user_or_401(request)
    if error:
        return error
    records = BizRecord.objects.filter(owner=user, module='user_huaxiang')
    if request.method == 'GET':
        rows = records.annotate(chunks=Count('knowledge_chunks')).order_by('-id')[:200]
        return ok({'items': [{'id': row.id, 'name': row.title, 'chunks': row.chunks} for row in rows]})

    form = KnowledgeForm(request.POST, request.FILES)
    if not form.is_valid():
        return _invalid_form(form)
    data = form.cleaned_data
    if not data['record_id'] and not data['name']:
        return fail('validation_error', '请填写知识库名称。')
    sources = []
    if data['text']:
        sources.append(('粘贴资料', data['text']))
    if upload := data['file']:
        try:
            sources.append((upload.name, extract_upload(upload.name, upload.read(MAX_BYTES + 1))))
        except ValueError as exc:
            return fail('validation_error', str(exc))
    if not sources:
        return fail('validation_error', '请粘贴资料或选择文件。')
    with transaction.atomic():
        if data['record_id']:
            record = records.select_for_update().filter(id=data['record_id']).first()
            if not record:
                return fail('not_found', '知识库不存在。', status=404)
        else:
            record = BizRecord.objects.create(owner=user, module='user_huaxiang', title=data['name'], data={
                'name': data['name'], 'company_name': data['company_name'],
            })
        count = append_knowledge_sources(record, sources)
    return ok({'id': record.id, 'name': record.title, 'chunks': count}, status=200 if data['record_id'] else 201)


def _observation_payload(record):
    return {'id': record.id, 'trial': '', 'cohort': '', **record.data}


def _observation_summary(records):
    fields = ('brand', 'platform', 'surface', 'phase', 'intent', 'outcome', 'mentioned',
              'recommended', 'citation_status', 'own_cited')
    counts = {}
    for row in records.order_by().values_list(*(f'data__{field}' for field in fields)).iterator():
        group = row[:5]
        outcome, mentioned, recommended, citation_status, own_cited = row[5:]
        summary = counts.setdefault(group, dict(zip(fields[:5], group), valid=0, failed=0,
                                                mentioned=0, recommended=0, citation_samples=0, own_cited=0))
        if outcome == 'failed':
            summary['failed'] += 1
            continue
        summary['valid'] += 1
        summary['mentioned'] += int(mentioned)
        summary['recommended'] += int(recommended)
        summary['citation_samples'] += int(citation_status != 'unknown')
        summary['own_cited'] += int(own_cited)
    return sorted(counts.values(), key=lambda group: tuple(group[field] for field in fields[:5]))


@require_http_methods(['GET', 'POST', 'PUT'])
def observations(request):
    user, error = _user_or_401(request)
    if error:
        return error
    records = BizRecord.objects.filter(owner=user, module=OBSERVATION_MODULE)
    if request.method == 'GET':
        if brand := request.GET.get('brand', '').strip():
            records = records.filter(data__brand__iexact=brand)
        if trial := request.GET.get('trial', '').strip():
            records = records.filter(data__trial__exact=trial)
        data = paginate(records, request, _observation_payload)
        data['summary'] = _observation_summary(records)
        data['questions'] = matched_questions(records)
        return ok(data)
    body, error = _body(request)
    if error:
        return error
    if not isinstance(body, dict):
        return fail('validation_error', '请求应为 JSON 对象。')
    form = ObservationForm(body)
    if not form.is_valid():
        return _invalid_form(form)
    values = form.cleaned_data
    record_id = values.pop('id')
    if request.method == 'PUT':
        updated = records.filter(id=record_id).update(
            title=values['question'][:255], data=values, updated_at=timezone.now(),
        )
        if not updated:
            return fail('not_found', '采样记录不存在。', status=404)
        return ok({'id': record_id, **values})
    record = BizRecord.objects.create(owner=user, module=OBSERVATION_MODULE, title=values['question'][:255], data=values)
    return ok(_observation_payload(record), status=201)
