from django.contrib import admin

from .models import Article, ArticleType, CompanyKeyword, CompanyQuestion


@admin.register(CompanyKeyword)
class CompanyKeywordAdmin(admin.ModelAdmin):
    list_display = ('id', 'keyword', 'hit_word', 'tuozhan_status', 'owner', 'created_at')
    search_fields = ('keyword', 'hit_word')


@admin.register(CompanyQuestion)
class CompanyQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'company_keyword', 'owner', 'created_at')
    search_fields = ('question',)


@admin.register(ArticleType)
class ArticleTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'type_name', 'owner', 'created_at')
    search_fields = ('type_name',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'article_type', 'status', 'owner', 'created_at')
    search_fields = ('title',)
    list_filter = ('status',)
