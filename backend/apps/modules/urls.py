from django.urls import path

from . import views

urlpatterns = [
    path('modules/', views.module_list, name='module-list'),
    path('modules/resolve', views.resolve, name='module-resolve'),
    path('modules/<slug:module>/options', views.module_options, name='module-options'),
    path('modules/<slug:module>/', views.module_records, name='module-records'),
]
