import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.content.models import Article, CompanyKeyword
from apps.modules.models import BizRecord
from apps.pipeline.models import KnowledgeChunk, PublishOrder, Topic


@override_settings(AI_MODE='demo')
class StudioTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('studio', password='secret123')
        self.client.force_login(self.user)

    def test_text_import_becomes_searchable_chunks(self):
        record = BizRecord.objects.create(
            owner=self.user,
            module='user_huaxiang',
            title='导入库',
            data={'name': '导入库', 'product': '原有产品'},
        )
        upload = SimpleUploadedFile('notes.md', '液体钙每片含钙300毫克。'.encode('utf-8'))
        response = self.client.post(f'/api/pipeline/knowledge/{record.id}/import', {'file': upload})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(KnowledgeChunk.objects.filter(source=record, text__contains='300毫克').exists())

    def test_prompt_trial_does_not_save_an_article(self):
        keyword = CompanyKeyword.objects.create(owner=self.user, keyword='液体钙')
        response = self.client.post(
            '/api/pipeline/prompts/test',
            data=json.dumps({'title': '液体钙适合日常补充', 'company_keyword_id': keyword.id, 'zhiling': '介绍钙含量'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()['data']['saved'])
        self.assertEqual(Article.objects.count(), 0)

    def test_topic_publish_requires_approved_articles(self):
        pending = Article.objects.create(owner=self.user, title='草稿文章', content='正文', status=0)
        denied = self.client.post(
            '/api/pipeline/topics/',
            data=json.dumps({'title': '钙专题', 'status': 1, 'article_ids': str(pending.id), 'layout': 'guide'}),
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400)
        pending.status = Article.STATUS_NORMAL
        pending.save(update_fields=['status'])
        allowed = self.client.post(
            '/api/pipeline/topics/',
            data=json.dumps({'title': '钙专题', 'summary': '阅读指南', 'status': 1, 'article_ids': [pending.id], 'layout': 'guide'}),
            content_type='application/json',
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)
        topic_id = allowed.json()['data']['id']
        page = self.client.get(f'/t/{topic_id}')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '阅读指南')
        self.assertContains(page, 'og:title')
        sitemap = self.client.get('/sitemap.xml')
        self.assertContains(sitemap, f'/t/{topic_id}')
        self.assertContains(self.client.get('/robots.txt'), 'Sitemap:')
        self.assertContains(self.client.get('/llms.txt'), '钙专题')
        self.assertEqual(self.client.get(f'/t/{Topic.objects.get(id=topic_id).id + 9}').status_code, 404)

    def test_private_link_is_rejected_and_public_check_records_status(self):
        denied = self.client.post(
            '/api/pipeline/links/',
            data=json.dumps({'title': '内网', 'url': 'http://127.0.0.1/secret'}),
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400)

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class Opener:
            def open(self, *args, **kwargs):
                return Response()

        with patch('apps.pipeline.studio._is_public_http'), patch('apps.pipeline.studio.urllib.request.build_opener', return_value=Opener()):
            created = self.client.post(
                '/api/pipeline/links/',
                data=json.dumps({'title': '公开资料', 'url': 'https://example.com/calcium', 'category': '健康'}),
                content_type='application/json',
            )
            self.assertEqual(created.status_code, 201, created.content)
            checked = self.client.post(f"/api/pipeline/links/{created.json()['data']['id']}/check", data='{}', content_type='application/json')
        self.assertEqual(checked.status_code, 200, checked.content)
        self.assertEqual(checked.json()['data']['status_label'], '可访问')

    def test_manual_order_follows_the_work_queue(self):
        article = Article.objects.create(owner=self.user, title='可发布', content='正文', status=0)
        early = self.client.post(
            '/api/pipeline/orders/',
            data=json.dumps({'article_id': article.id, 'platform': 'toutiao'}),
            content_type='application/json',
        )
        self.assertEqual(early.status_code, 400)
        article.status = Article.STATUS_NORMAL
        article.save(update_fields=['status'])
        created = self.client.post(
            '/api/pipeline/orders/',
            data=json.dumps({'article_id': article.id, 'platform': 'sohu', 'note': '人工确认后发布'}),
            content_type='application/json',
        )
        self.assertEqual(created.status_code, 201, created.content)
        order_id = created.json()['data']['id']
        skipped = self.client.put(
            '/api/pipeline/orders/',
            data=json.dumps({'id': order_id, 'status': 'confirmed'}),
            content_type='application/json',
        )
        self.assertEqual(skipped.status_code, 400)
        self.client.put('/api/pipeline/orders/', data=json.dumps({'id': order_id, 'status': 'claimed'}), content_type='application/json')
        self.client.put('/api/pipeline/orders/', data=json.dumps({'id': order_id, 'status': 'submitted', 'receipt': '已在后台提交'}), content_type='application/json')
        done = self.client.put('/api/pipeline/orders/', data=json.dumps({'id': order_id, 'status': 'confirmed'}), content_type='application/json')
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(PublishOrder.objects.get(id=order_id).status, 'confirmed')

    def test_optimize_removes_blocked_phrase_and_visibility_lists_keyword(self):
        knowledge = BizRecord.objects.create(
            owner=self.user,
            module='user_huaxiang',
            title='钙',
            data={'product': '液体钙适合日常补充，每片含钙300毫克。'},
        )
        from apps.pipeline.knowledge import sync_knowledge
        sync_knowledge(knowledge)
        keyword = CompanyKeyword.objects.create(owner=self.user, keyword='液体钙')
        task = BizRecord.objects.create(
            owner=self.user,
            module='ai_task',
            title='任务',
            data={'keyword': keyword.keyword, 'huaxiang_ids': [knowledge.id], 'article_status': 1},
        )
        article = Article.objects.create(
            owner=self.user,
            title='液体钙适合日常补充',
            content='<p>液体钙适合日常补充，每片含钙300毫克。</p><p>最强</p>',
            status=0,
            task_id=task.id,
        )
        response = self.client.post(f'/api/pipeline/articles/{article.id}/optimize', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        article.refresh_from_db()
        self.assertNotIn('最强', article.content)
        self.assertEqual(article.status, Article.STATUS_NORMAL)
        report = self.client.get('/api/pipeline/visibility/')
        self.assertEqual(report.status_code, 200)
        self.assertTrue(any(item['keyword'] == '液体钙' for item in report.json()['data']['keywords']))
        exported = self.client.get('/api/pipeline/articles/export.md')
        self.assertContains(exported, '液体钙适合日常补充')
