from django.conf import settings
from django.db import models


class TimeStampedOwnerModel(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        verbose_name='所属用户',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CompanyKeyword(TimeStampedOwnerModel):
    keyword = models.CharField('主关键词', max_length=255)
    hit_word = models.CharField('品牌名/简称', max_length=255, blank=True, default='')
    tuozhan_status = models.PositiveSmallIntegerField('拓词状态', default=0)
    zhengliu_question = models.TextField('拓展问题', blank=True, default='')

    class Meta:
        ordering = ['-id']
        verbose_name = '关键词'
        verbose_name_plural = '关键词'

    def __str__(self):
        return self.keyword


class CompanyQuestion(TimeStampedOwnerModel):
    company_keyword = models.ForeignKey(
        CompanyKeyword,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='questions',
        verbose_name='关联关键词',
    )
    question = models.TextField('拓展问题')

    class Meta:
        ordering = ['-id']
        verbose_name = '问答词'
        verbose_name_plural = '问答词'

    def __str__(self):
        return self.question[:40]


class ArticleType(TimeStampedOwnerModel):
    type_name = models.CharField('文章分类', max_length=128)

    class Meta:
        ordering = ['-id']
        verbose_name = '文章分类'
        verbose_name_plural = '文章分类'

    def __str__(self):
        return self.type_name


class Article(TimeStampedOwnerModel):
    STATUS_PENDING = 0
    STATUS_NORMAL = 1
    STATUS_DISABLED = 2
    STATUS_CHOICES = (
        (STATUS_PENDING, '待审核'),
        (STATUS_NORMAL, '正常'),
        (STATUS_DISABLED, '禁用'),
    )

    title = models.CharField('标题', max_length=255)
    article_type = models.ForeignKey(
        ArticleType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
        verbose_name='分类',
    )
    image_type_id = models.IntegerField('图库分类ID', null=True, blank=True)
    content = models.TextField('正文', blank=True, default='')
    status = models.PositiveSmallIntegerField('状态', choices=STATUS_CHOICES, default=STATUS_NORMAL)
    task_id = models.IntegerField('写作任务ID', null=True, blank=True, db_index=True)
    question_id = models.IntegerField('问答词ID', null=True, blank=True)
    quality_score = models.PositiveSmallIntegerField('质检分数', null=True, blank=True)
    quality_report = models.JSONField('质检报告', default=dict, blank=True)
    content_hash = models.CharField('正文摘要', max_length=64, blank=True, default='')

    class Meta:
        ordering = ['-id']
        verbose_name = '文章'
        verbose_name_plural = '文章'

    def __str__(self):
        return self.title
