"""Business module keys exposed by the static admin pages."""

MODULES = {
    'analyze': '诊断报告',
    'images_type': '图库分类',
    'user_huaxiang': '企业知识库',
    'zhiling': '写作指令',
    'ai_task': 'AI写作任务',
    'weixin_baowen': '全网爆文复刻',
    'piliang_baowen': '批量爆文复刻',
    'ai_image': 'AI生图',
    'b2b': 'B2B行业网站',
    'b2b_task': 'B2B自动发布任务',
    'user_contact': '联系方式管理',
    'b2b_order': 'B2B发布记录',
    'webmedia': '单条发布媒体',
    'webmedia_task': '媒体自动发布任务',
    'webmedia_order': '媒体发布记录',
    'media_collection': '媒体收藏',
    'zimedia': '自媒体',
    'zimedia_order': '自媒体发布记录',
    'weixinapp2': '微信小程序',
    'draft': '草稿',
    'weixin_article': '微信文章',
    'user_site': '站点',
    'user_site_task': '站点任务',
    'user_site_record': '站点记录',
    'user_tdk': 'TDK',
    'user_jianji': '剪辑',
    'video_task': '视频任务',
    'video_record': '视频记录',
    'tongji': '统计',
    'shoulu_tuozhan': '收录拓展',
    'shoulu_record': '收录记录',
    'agent_skill': 'Agent技能',
    'zhishu': '指数',
    'zhengliu': '蒸馏',
    'tuozhan': '拓展',
    'user_score_log': '点数明细',
    'user_money_log': '资金明细',
    'realname': '实名认证',
    'quanyi': '权益',
}

PAGE_ALIASES = {
    'images_type-index-type-1': ('images_type', '1'),
    'images_type-index-type-2': ('images_type', '2'),
    'images_type-add': ('images_type', None),
    'media_collection-index-type-1': ('media_collection', '1'),
    'media_collection-index-type-2': ('media_collection', '2'),
    'media_collection-add': ('media_collection', None),
    'analyze_v2-add': ('analyze', 'v2'),
    'analyze-add': ('analyze', None),
    'b2b-tougao-type-1': ('b2b', 'tougao-1'),
    'b2b-tougao-type-3': ('b2b', 'tougao-3'),
    'b2b-tougao-type-4': ('b2b', 'tougao-4'),
    'b2b-tougao-type-5': ('b2b', 'tougao-5'),
    'b2b-tougao-type-6': ('b2b', 'tougao-6'),
    'b2b-settle-type-2': ('b2b', 'settle-2'),
    'b2b-settle-type-8': ('b2b', 'settle-8'),
    'b2b-configure-type-2': ('b2b', 'configure-2'),
    'webmedia-tougao-media_id-21471': ('webmedia', 'tougao'),
    'zimedia-tougao-media_id-53781': ('zimedia', 'tougao'),
}

DEDICATED = {
    'company_keyword',
    'company_question',
    'article',
    'article_type',
    'general-profile',
    'dashboard',
    'shell',
}


def resolve_page(page_key: str):
    """Return (module, subtype) or (None, None)."""
    if not page_key:
        return None, None
    if page_key in PAGE_ALIASES:
        return PAGE_ALIASES[page_key]

    base = page_key
    if base.endswith('-add'):
        base = base[:-4]
    if '-edit' in base:
        base = base.split('-edit', 1)[0]
    if '-index-type-' in base:
        left, right = base.split('-index-type-', 1)
        if left in MODULES:
            return left, right

    if base in DEDICATED:
        return None, None
    if base in MODULES:
        return base, None
    return None, None


def module_exists(module: str) -> bool:
    return module in MODULES
