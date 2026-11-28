from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.content.models import CompanyKeyword
from apps.modules.models import BizRecord

from .models import KnowledgeChunk
from .retrieve import retrieve


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('workflow')
        self.client.force_login(self.user)

    def test_knowledge_create_and_append_are_available_to_writing(self):
        url = '/api/pipeline/knowledge/'
        document = SimpleUploadedFile('参数.txt', '远程水泵适配高山灌溉。'.encode())
        response = self.client.post(url, {'name': '水泵资料', 'text': '公司生产灌溉设备。', 'file': document})
        self.assertEqual(response.status_code, 201, response.content)
        library = response.json()['data']
        options = self.client.get('/api/modules/user_huaxiang/options').json()['data']['items']
        self.assertIn({'id': library['id'], 'label': '水泵资料'}, options)

        response = self.client.post(url, {'record_id': library['id'], 'text': '客户案例：山区果园防旱。'})
        self.assertEqual(response.status_code, 200, response.content)
        chunks = retrieve(self.user, '高山灌溉和山区果园', source_ids=[library['id']])
        self.assertTrue(any('高山灌溉' in chunk.text for chunk in chunks))
        self.assertTrue(any('山区果园' in chunk.text for chunk in chunks))

    def test_invalid_upload_does_not_leave_empty_library(self):
        response = self.client.post('/api/pipeline/knowledge/', {
            'name': '失败的导入',
            'file': SimpleUploadedFile('invalid.docx', b'fake'),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BizRecord.objects.filter(owner=self.user, module='user_huaxiang').exists())
        self.assertFalse(KnowledgeChunk.objects.filter(owner=self.user).exists())

    def test_document_above_old_limit_imports_in_both_knowledge_entries(self):
        content = BytesIO()
        with ZipFile(content, 'w') as archive:
            archive.writestr('word/document.xml', '<document><p>设备支持远程调速。</p></document>')
            archive.writestr('word/media/attachment.bin', b'\x01' * 1_200_000)

        response = self.client.post('/api/pipeline/knowledge/', {
            'name': '大文件资料',
            'file': SimpleUploadedFile('设备手册.docx', content.getvalue()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        record_id = response.json()['data']['id']
        response = self.client.post(f'/api/pipeline/knowledge/{record_id}/import', {
            'file': SimpleUploadedFile('设备补充.docx', content.getvalue()),
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(KnowledgeChunk.objects.filter(source_id=record_id, text__contains='远程调速').exists())

    def test_knowledge_upload_accepts_20_mb_and_rejects_larger_files(self):
        url = '/api/pipeline/knowledge/'
        for size, expected in ((20_000_000, 201), (20_000_001, 400)):
            with self.subTest(size=size):
                response = self.client.post(url, {
                    'name': f'测试边界 {size}',
                    'text': '同时保存粘贴资料',
                    'file': SimpleUploadedFile('details.txt', b'Equipment details'.ljust(size)),
                })
                self.assertEqual(response.status_code, expected, response.content)
                if expected == 400:
                    self.assertIn('文件超过 20 MB', response.json()['error']['message'])

    @override_settings(AI_MODE='stub')
    def test_suggest_and_save_business_keywords_from_imported_knowledge(self):
        response = self.client.post('/api/pipeline/knowledge/', {
            'name': '工业水泵知识库',
            'company_name': '青山设备',
            'text': '主营业务：工业水泵、变频控制柜。青山设备面向工厂客户。',
        })
        self.assertEqual(response.status_code, 201, response.content)
        record_id = response.json()['data']['id']
        CompanyKeyword.objects.create(owner=self.user, keyword='工业水泵')
        url = f'/api/pipeline/knowledge/{record_id}/keywords'
        result = self.client.post(url)
        self.assertEqual(result.status_code, 200, result.content)
        data = result.json()['data']
        self.assertEqual(data['method'], 'local')
        self.assertEqual([(item['keyword'], item['existing']) for item in data['items']],
                         [('工业水泵', True), ('变频控制柜', False)])
        self.assertIn('主营业务', data['items'][1]['evidence'])
        self.assertEqual(CompanyKeyword.objects.filter(owner=self.user).count(), 1)

        payload = {'keywords': ['变频控制柜', '工业水泵', ' 变频控制柜 ']}
        saved = self.client.put(url, payload, content_type='application/json')
        self.assertEqual(saved.json()['data'], {'created': 1, 'skipped': 2})
        saved = self.client.put(url, payload, content_type='application/json')
        self.assertEqual(saved.json()['data'], {'created': 0, 'skipped': 3})
        keyword = CompanyKeyword.objects.get(owner=self.user, keyword='变频控制柜')
        self.assertEqual(keyword.hit_word, '青山设备')
        options = self.client.get('/api/keywords/options').json()['data']['items']
        self.assertIn(keyword.pk, [item['id'] for item in options])

    @override_settings(AI_MODE='proxy')
    def test_model_only_suggests_terms_present_in_selected_library(self):
        knowledge = BizRecord.objects.create(owner=self.user, module='user_huaxiang', title='提取',
                                             data={'product': '工业水泵', 'company_name': '青山设备'})
        url = f'/api/pipeline/knowledge/{knowledge.pk}/keywords'
        with patch('apps.pipeline.keywords.complete_text',
                   return_value='```json\n{"keywords":["工业水泵","太阳能电池","青山设备"]}\n```'):
            data = self.client.post(url).json()['data']
        self.assertEqual(data['method'], 'model')
        self.assertEqual([item['keyword'] for item in data['items']], ['工业水泵'])
        with patch('apps.pipeline.keywords.complete_text', side_effect=RuntimeError('unavailable')):
            data = self.client.post(url).json()['data']
        self.assertEqual(data['method'], 'local')
        self.assertEqual([item['keyword'] for item in data['items']], ['工业水泵'])

    @override_settings(AI_MODE='stub')
    def test_keyword_extraction_requires_ownership_and_valid_selection(self):
        knowledge = BizRecord.objects.create(owner=self.user, module='user_huaxiang', title='私有',
                                             data={'summary': '公司成立于 2021 年。'})
        url = f'/api/pipeline/knowledge/{knowledge.pk}/keywords'
        self.assertEqual(self.client.post(url).json()['data']['items'], [])
        self.assertEqual(self.client.put(url, {'keywords': []}, content_type='application/json').status_code, 400)
        self.client.force_login(get_user_model().objects.create_user('external-keywords'))
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.put(url, {'keywords': ['工业水泵']},
                                         content_type='application/json').status_code, 404)

    def _observation(self, **changes):
        return {
            'brand': '青山水泵', 'platform': '豆包', 'surface': '网页端 · 联网搜索',
            'phase': 'baseline', 'intent': 'category', 'question': '果园用什么水泵？',
            'outcome': 'answer', 'answer': '推荐青山水泵做山区灌溉。',
            'citation_status': 'yes', 'owned_site': 'example.com',
            'citations': 'https://guide.example.com/pumps\nhttps://other.example.net/pumps',
            'recommended': True, **changes,
        }

    def test_observations_split_reports_and_preserve_originals(self):
        url = '/api/pipeline/observations/'
        for changes in ({}, {'outcome': 'failed', 'answer': '超时'},
                        {'phase': 'retest', 'citation_status': 'unknown', 'citations': ''},
                        {'phase': 'retest', 'citations': 'https://notexample.com/pumps'}):
            response = self.client.post(url, self._observation(**changes), content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)
        data = self.client.get(url, {'page_size': 1}).json()['data']
        baseline, retest = data['summary']
        self.assertEqual(data['total'], 4)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['answer'], '推荐青山水泵做山区灌溉。')
        self.assertEqual(data['items'][0]['citations'], ['https://notexample.com/pumps'])
        self.assertEqual((baseline['valid'], baseline['failed'], baseline['mentioned'], baseline['own_cited']),
                         (1, 1, 1, 1))
        self.assertEqual((retest['valid'], retest['citation_samples'], retest['own_cited']), (2, 1, 0))

    def test_observation_requires_citation_status_to_match_links(self):
        response = self.client.post('/api/pipeline/observations/',
                                    self._observation(citation_status='unknown'),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_trial_report_matches_original_questions_and_counts_repeat_signals(self):
        url = '/api/pipeline/observations/'
        trial = {'trial': '水泵首轮', 'cohort': 'target'}
        baseline = dict(trial, phase='baseline', recommended=False,
                        citations='https://journal.example.net/selection')
        for day in (1, 2, 3):
            response = self.client.post(url, self._observation(
                **baseline, observed_at=f'2026-11-{day:02}T09:00:00+08:00',
            ), content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)

        retest = dict(trial, phase='retest', recommended=True, citations='https://example.com/selection')
        for day, hour in ((21, 9), (21, 11), (23, 9)):
            response = self.client.post(url, self._observation(
                **retest, observed_at=f'2026-11-{day:02}T{hour:02}:00:00+08:00',
            ), content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)

        for extra in ({'surface': 'App · 搜索'}, {'question': '果园用什么泵？'}, {'cohort': 'holdout'},
                      {'trial': '水泵第二轮'}):
            response = self.client.post(url, self._observation(**{**retest, **extra}), content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)

        rows = self.client.get(url, {'trial': '水泵首轮'}).json()['data']['questions']
        paired = [row for row in rows if row['baseline']['valid']]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]['signals'], ['recommendation', 'citation'])
        self.assertEqual(paired[0]['sources'], [{'url': 'https://journal.example.net/selection', 'answers': 3}])
        self.assertEqual(paired[0]['retest']['valid'], 3)
        self.assertEqual(paired[0]['retest']['dates'], 2)

    def test_same_day_hits_do_not_count_as_repeat_signals(self):
        url = '/api/pipeline/observations/'
        for phase, day, hour, hit in (
            ('baseline', 1, 9, False), ('baseline', 2, 9, False), ('baseline', 3, 9, False),
            ('retest', 21, 9, True), ('retest', 21, 11, True), ('retest', 23, 9, False),
        ):
            response = self.client.post(url, self._observation(
                trial='水泵首轮', cohort='target', phase=phase, recommended=hit,
                observed_at=f'2026-11-{day:02}T{hour:02}:00:00+08:00',
                citations='https://example.com/selection' if hit else 'https://journal.example.net/selection',
            ), content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)
        row, = self.client.get(url).json()['data']['questions']
        self.assertEqual(row['retest']['recommended'], 2)
        self.assertEqual(row['retest']['own_cited'], 2)
        self.assertEqual(row['signals'], [])

    def test_account_cannot_read_or_update_another_accounts_workflow(self):
        knowledge = self.client.post('/api/pipeline/knowledge/', {'name': '私有库', 'text': '原有资料'})
        observation = self.client.post('/api/pipeline/observations/', self._observation(), content_type='application/json')
        self.client.force_login(get_user_model().objects.create_user('other-workflow'))
        self.assertEqual(self.client.get('/api/pipeline/knowledge/').json()['data']['items'], [])
        self.assertEqual(self.client.get('/api/pipeline/observations/').json()['data']['items'], [])
        response = self.client.post('/api/pipeline/knowledge/', {
            'record_id': knowledge.json()['data']['id'], 'text': '外部追加',
        })
        self.assertEqual(response.status_code, 404)
        response = self.client.put('/api/pipeline/observations/',
                                   self._observation(id=observation.json()['data']['id']),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 404)
