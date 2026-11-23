from django.urls import path

from . import views

urlpatterns = [
    path('keywords/', views.keywords, name='keywords'),
    path('keywords/options', views.keyword_options, name='keyword-options'),
    path('questions/', views.questions, name='questions'),
    path('article-types/', views.article_types, name='article-types'),
    path('article-types/options', views.article_type_options, name='article-type-options'),
    path('articles/', views.articles, name='articles'),
]
