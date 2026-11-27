from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

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
