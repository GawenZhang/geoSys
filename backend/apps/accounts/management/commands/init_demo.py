from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.content.models import Article, ArticleType, CompanyKeyword, CompanyQuestion
from apps.modules.models import BizRecord
from apps.modules.registry import MODULES


SAMPLE_BY_MODULE = {
    'analyze': {'title': '示例品牌诊断', 'brand': '示例品牌', 'keyword': 'GEO优化', 'status': 1, 'is_pro': 1},
    'images_type': {'title': '默认图库', 'type_name': '默认图库', 'status': 1},
    'user_huaxiang': {'title': '示例企业知识库', 'name': '示例企业知识库', 'status': 1},
    'zhiling': {'title': '默认写作指令', 'name': '默认写作指令', 'status': 1},
    'ai_task': {'title': '示例AI写作任务', 'name': '示例AI写作任务', 'max_count': 10, 'success_count': 0, 'status': 1},
    'weixin_baowen': {'title': '示例爆文复刻', 'name': '示例爆文复刻', 'status': 1},
    'piliang_baowen': {'title': '示例批量爆文', 'name': '示例批量爆文', 'status': 1},
    'ai_image': {'title': '示例生图', 'prompt': '示例产品图片', 'status': 1, 'cost': 0},
    'b2b': {'title': '示例B2B站点', 'name': '示例B2B站点', 'status': 1},
    'b2b_task': {'title': '示例B2B任务', 'task_name': '示例B2B任务', 'status': 1},
    'user_contact': {'title': '示例联系人', 'name': '示例联系人', 'phone': '13800000000', 'status': 1},
    'b2b_order': {'title': '示例B2B发布', 'media_name': '示例媒体', 'order_nid': 'DEMO-B2B-1', 'status': 1, 'price': 0},
    'webmedia': {'title': '示例网媒', 'media_name': '示例网媒', 'status': 1},
    'webmedia_task': {'title': '示例网媒任务', 'task_name': '示例网媒任务', 'status': 1},
    'webmedia_order': {'title': '示例网媒发布', 'media_name': '示例网媒', 'order_nid': 'DEMO-WM-1', 'status': 1},
    'media_collection': {'title': '示例收藏媒体', 'media_name': '示例收藏媒体', 'status': 1},
    'zimedia': {'title': '示例自媒体', 'media_name': '示例自媒体', 'status': 1},
    'zimedia_order': {'title': '示例自媒体发布', 'media_name': '示例自媒体', 'order_nid': 'DEMO-ZI-1', 'status': 1},
    'weixinapp2': {'title': '示例小程序', 'name': '示例小程序', 'status': 1},
    'draft': {'title': '示例草稿任务', 'name': '示例草稿任务', 'status': 1},
    'weixin_article': {'title': '示例微信文章', 'status': 1},
    'user_site': {'title': '示例站点', 'name': '示例站点', 'status': 1},
    'user_site_task': {'title': '示例站点任务', 'name': '示例站点任务', 'status': 1},
    'user_site_record': {'title': '示例站点记录', 'name': '示例站点记录', 'status': 1},
    'user_tdk': {'title': '示例TDK', 'type_name': '示例TDK', 'keywords': 'GEO,优化', 'status': 1},
    'user_jianji': {'title': '示例剪辑', 'name': '示例剪辑', 'status': 1},
    'video_task': {'title': '示例视频任务', 'name': '示例视频任务', 'status': 1},
    'video_record': {'title': '示例视频记录', 'name': '示例视频记录', 'status': 1},
    'tongji': {'title': '示例统计', 'name': '示例统计', 'status': 1},
    'shoulu_tuozhan': {'title': '示例收录拓展', 'keyword': 'GEO优化', 'status': 1},
    'shoulu_record': {'title': '示例收录记录', 'keyword': 'GEO优化', 'status': 1},
    'agent_skill': {'title': '示例Agent技能', 'name': '示例Agent技能', 'status': 1},
    'zhishu': {'title': '示例指数', 'keyword': 'GEO优化', 'status': 1},
    'zhengliu': {'title': '示例蒸馏', 'keyword': 'GEO优化', 'status': 1},
    'tuozhan': {'title': '示例拓展', 'keyword': 'GEO优化', 'status': 1},
    'user_score_log': {'title': '示例点数变动', 'score': 100, 'memo': '初始化赠送', 'status': 1},
    'user_money_log': {'title': '示例资金变动', 'money': 0, 'memo': '初始化', 'status': 1},
    'realname': {'title': '示例实名', 'name': '测试用户', 'status': 1},
    'quanyi': {'title': '示例权益', 'name': '基础套餐', 'status': 1},
}


class Command(BaseCommand):
    help = 'Create demo user (demo/demo123) and sample content for all modules'

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username='demo',
            defaults={
                'nickname': '测试号',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        from decimal import Decimal

        user.set_password('demo123')
        user.nickname = user.nickname or '测试号'
        user.is_staff = True
        user.is_superuser = True
        if int(getattr(user, 'score', 0) or 0) <= 0:
            user.score = 100
        if Decimal(str(getattr(user, 'balance', 0) or 0)) <= 0:
            user.balance = Decimal('88.00')
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} demo user demo/demo123"
        ))

        keyword, _ = CompanyKeyword.objects.get_or_create(
            owner=user,
            keyword='GEO优化',
            defaults={
                'hit_word': '宝邦GEO',
                'tuozhan_status': 0,
                'zhengliu_question': '什么是GEO优化\nGEO优化有什么好处',
            },
        )
        CompanyQuestion.objects.get_or_create(
            owner=user,
            company_keyword=keyword,
            question='什么是GEO优化',
        )
        article_type, _ = ArticleType.objects.get_or_create(
            owner=user,
            type_name='默认分类',
        )
        Article.objects.get_or_create(
            owner=user,
            title='欢迎使用 geoSys 本地后台',
            defaults={
                'article_type': article_type,
                'content': '<p>这是一篇由 init_demo 创建的示例文章。</p>',
                'status': Article.STATUS_NORMAL,
            },
        )

        created_modules = 0
        for module in MODULES:
            payload = dict(SAMPLE_BY_MODULE.get(module) or {'title': f'{MODULES[module]}示例', 'status': 1})
            title = str(payload.get('title') or payload.get('name') or payload.get('task_name') or MODULES[module])
            subtype = ''
            if module == 'images_type':
                subtype = '1'
            elif module == 'media_collection':
                subtype = '1'
            _, was_created = BizRecord.objects.get_or_create(
                owner=user,
                module=module,
                subtype=subtype,
                title=title,
                defaults={
                    'status': int(payload.get('status') or 1),
                    'data': payload,
                },
            )
            if was_created:
                created_modules += 1
            if module == 'images_type':
                BizRecord.objects.get_or_create(
                    owner=user,
                    module=module,
                    subtype='2',
                    title='内容图库',
                    defaults={'status': 1, 'data': {'title': '内容图库', 'type_name': '内容图库', 'status': 1}},
                )
            if module == 'media_collection':
                BizRecord.objects.get_or_create(
                    owner=user,
                    module=module,
                    subtype='2',
                    title='自媒体收藏',
                    defaults={'status': 1, 'data': {'title': '自媒体收藏', 'media_name': '自媒体收藏', 'status': 1}},
                )

        self.stdout.write(self.style.SUCCESS(
            f'Sample content ready; new module rows={created_modules}, modules={len(MODULES)}'
        ))
