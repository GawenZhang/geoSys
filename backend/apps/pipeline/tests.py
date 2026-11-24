import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.content.models import Article, CompanyKeyword, CompanyQuestion
from apps.modules.models import BizRecord
from apps.pipeline.models import KnowledgeChunk
from apps.pipeline.publish import PublishError, _is_public_http


@override_settings(AI_MODE='demo')
class PipelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('pipe', password='secret123')
        self.client.force_login(self.user)

    def _knowledge(self, product='液体钙适合日常补充，每片含钙300毫克。'):
        response = self.client.post(
            '/api/modules/user_huaxiang/',
            data=json.dumps({
                'name': '钙片知识库',
                'company_name': '示例健康',
                'product': product,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['data']

    def _keyword(self, question='液体钙哪个好'):
        keyword = CompanyKeyword.objects.create(owner=self.user, keyword='钙片', hit_word='示例健康')
        CompanyQuestion.objects.create(owner=self.user, company_keyword=keyword, question=question)
        return keyword

    def _prompt(self, text='根据知识库介绍产品', create_type='1'):
        return BizRecord.objects.create(
            owner=self.user,
            module='zhiling',
            title='正文指令',
            data={'name': '正文指令', 'zhiling': text, 'create_type': create_type},
        )

    def _task(self, keyword, **extra):
        payload = {
            'name': '钙片写作',
            'company_keyword_id': keyword.id,
            'max_count': 1,
            'article_status': 1,
            'image_count': 0,
        }
        payload.update(extra)
        return BizRecord.objects.create(
            owner=self.user,
            module='ai_task',
            title=payload['name'],
            data=payload,
        )

    def test_knowledge_save_creates_searchable_chunks(self):
        record = self._knowledge()
        chunks = list(KnowledgeChunk.objects.filter(source_id=record['id']))
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any('液体钙' in chunk.text for chunk in chunks))

        response = self.client.put(
            '/api/modules/user_huaxiang/',
            data=json.dumps({'id': record['id'], 'product': '更换后的产品说明完全不同。'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        texts = list(KnowledgeChunk.objects.filter(source_id=record['id']).values_list('text', flat=True))
        self.assertTrue(any('更换后的产品说明' in text for text in texts))
        self.assertFalse(any('液体钙' in text for text in texts))

    def test_low_score_stays_pending_and_cannot_be_released(self):
        keyword = self._keyword()
        task = self._task(keyword, huaxiang_ids=[])
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()['data']
        self.assertEqual(body['success_count'], 1)
        article = Article.objects.get(id=body['article_ids'][0])
        self.assertEqual(article.status, Article.STATUS_PENDING)
        self.assertLess(article.quality_score, 70)

        denied = self.client.put(
            '/api/articles/',
            data=json.dumps({'id': article.id, 'status': 1}),
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400, denied.content)
        self.assertIn('未达到放行分数', denied.json()['error']['message'])
        article.refresh_from_db()
        self.assertEqual(article.status, Article.STATUS_PENDING)

    def test_high_score_article_is_published_locally_and_by_webhook(self):
        knowledge = self._knowledge()
        prompt = self._prompt()
        gallery = BizRecord.objects.create(
            owner=self.user,
            module='images_type',
            title='钙片图',
            data={'images': ['/media/uploads/calcium.png']},
        )
        keyword = self._keyword()
        task = self._task(
            keyword,
            huaxiang_ids=[knowledge['id']],
            zhiling_id=prompt.id,
            image_type_id=gallery.id,
            image_count=1,
        )
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        article = Article.objects.get(id=response.json()['data']['article_ids'][0])
        self.assertEqual(article.status, Article.STATUS_NORMAL)
        self.assertGreaterEqual(article.quality_score, 70)
        self.assertIn('液体钙适合日常补充', article.content)
        self.assertIn('/media/uploads/calcium.png', article.content)
        self.assertTrue(article.content_hash)

        page = self.client.get(f'/p/{article.id}')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '液体钙哪个好')

        site = BizRecord.objects.create(
            owner=self.user,
            module='user_site',
            title='https://cms.example.com/hook',
            data={'site_type': 10, 'site_url': 'https://cms.example.com/hook', 'api_key': 'secret'},
        )
        site_task = BizRecord.objects.create(
            owner=self.user,
            module='user_site_task',
            title='推送',
            data={'user_site_id': site.id, 'article_type_id': article.article_type_id, 'day_send_count': 1},
        )
        with patch('apps.pipeline.publish._is_public_http'), patch(
            'apps.pipeline.publish.http_post', return_value=(200, '{"ok":true}')
        ) as posted:
            published = self.client.post(
                f'/api/pipeline/site-tasks/{site_task.id}/publish',
                data='{}',
                content_type='application/json',
            )
        self.assertEqual(published.status_code, 200, published.content)
        self.assertEqual(published.json()['data']['published'], 1)
        self.assertEqual(posted.call_count, 1)
        self.assertEqual(
            BizRecord.objects.filter(owner=self.user, module='user_site_record', status=1).count(),
            1,
        )
        with patch('apps.pipeline.publish._is_public_http'), patch(
            'apps.pipeline.publish.http_post', return_value=(200, '{"ok":true}')
        ) as posted_again:
            again = self.client.post(
                f'/api/pipeline/site-tasks/{site_task.id}/publish',
                data='{}',
                content_type='application/json',
            )
        self.assertEqual(again.json()['data']['published'], 0)
        self.assertEqual(posted_again.call_count, 0)

    def test_blocked_phrase_cannot_be_released(self):
        knowledge = self._knowledge()
        prompt = self._prompt('这款产品绝对有效')
        keyword = self._keyword()
        task = self._task(keyword, huaxiang_ids=[knowledge['id']], zhiling_id=prompt.id)
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        article = Article.objects.get(id=response.json()['data']['article_ids'][0])
        self.assertEqual(article.status, Article.STATUS_PENDING)
        self.assertTrue(article.quality_report.get('blocked'))
        denied = self.client.put(
            '/api/articles/',
            data=json.dumps({'id': article.id, 'status': 1}),
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400)

    def test_task_respects_count_and_queue(self):
        keyword = self._keyword()
        CompanyQuestion.objects.create(owner=self.user, company_keyword=keyword, question='钙片怎么吃')
        task = self._task(keyword, max_count=1, article_status=0)
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        self.assertEqual(response.json()['data']['success_count'], 1)
        self.assertEqual(Article.objects.filter(owner=self.user, task_id=task.id).count(), 1)

        queued = self._task(keyword, max_count=4, name='排队任务')
        queued_response = self.client.post(
            f'/api/pipeline/tasks/{queued.id}/run',
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(queued_response.json()['data']['pipeline_status'], 'queued')
        self.assertEqual(Article.objects.filter(task_id=queued.id).count(), 0)
        from django.core.management import call_command
        call_command('run_pipeline')
        self.assertEqual(Article.objects.filter(task_id=queued.id).count(), 2)

    def test_visibility_report_includes_knowledge(self):
        self._knowledge()
        response = self.client.post(
            '/api/ai',
            data=json.dumps({
                'operation': 'detect',
                'input': {'page': 'analyze-add', 'fields': {'brand_name': '示例健康', 'industry': '液体钙'}},
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        text = response.json()['data']['text']
        self.assertIn('知识库依据', text)
        self.assertIn('液体钙适合日常补充', text)

    def test_private_site_is_rejected(self):
        with self.assertRaises(PublishError):
            _is_public_http('http://127.0.0.1/hook')
        site = BizRecord.objects.create(
            owner=self.user,
            module='user_site',
            title='local',
            data={'site_type': 1, 'site_url': 'https://cms.example.com'},
        )
        task = BizRecord.objects.create(
            owner=self.user,
            module='user_site_task',
            title='站点',
            data={'user_site_id': site.id},
        )
        response = self.client.post(
            f'/api/pipeline/site-tasks/{task.id}/publish',
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('WordPress', response.json()['error']['message'])

    @override_settings(AI_MODE='stub')
    def test_stub_mode_does_not_write_articles(self):
        keyword = self._keyword()
        task = self._task(keyword)
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Article.objects.filter(task_id=task.id).count(), 0)

    def test_pending_article_has_no_public_page(self):
        keyword = self._keyword()
        task = self._task(keyword, article_status=0)
        response = self.client.post(f'/api/pipeline/tasks/{task.id}/run', data='{}', content_type='application/json')
        article_id = response.json()['data']['article_ids'][0]
        missing = self.client.get(f'/p/{article_id}')
        self.assertEqual(missing.status_code, 404)
