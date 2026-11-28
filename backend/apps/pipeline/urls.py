from django.urls import path

from . import studio_views, views, workflow

urlpatterns = [
    path('knowledge/', workflow.knowledge, name='pipeline-knowledge'),
    path('knowledge/<int:record_id>/keywords', workflow.knowledge_keywords, name='pipeline-knowledge-keywords'),
    path('observations/', workflow.observations, name='pipeline-observations'),
    path('tasks/<int:task_id>/run', views.run_task, name='pipeline-run-task'),
    path('site-tasks/<int:task_id>/publish', views.publish_task, name='pipeline-publish-task'),
    path('knowledge/<int:record_id>/import', studio_views.knowledge_import, name='pipeline-knowledge-import'),
    path('prompts/test', studio_views.prompt_test, name='pipeline-prompt-test'),
    path('topics/', studio_views.topics, name='pipeline-topics'),
    path('links/', studio_views.links, name='pipeline-links'),
    path('links/<int:link_id>/check', studio_views.link_check, name='pipeline-link-check'),
    path('orders/', studio_views.orders, name='pipeline-orders'),
    path('visibility/', studio_views.visibility, name='pipeline-visibility'),
    path('articles/export.md', studio_views.article_export, name='pipeline-article-export'),
    path('articles/<int:article_id>/optimize', studio_views.article_optimize, name='pipeline-article-optimize'),
]
