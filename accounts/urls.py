# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('end-round/', views.end_round, name='end_round'),
    path('platform/', views.platform_home, name='platform_home'),
    path('platform/governance/', views.platform_governance, name='platform_governance'),
    path('platform/governance/publish/', views.platform_governance_publish, name='platform_governance_publish'),
    path('platform/governance/cancel/', views.platform_governance_cancel, name='platform_governance_cancel'),
    path('platform/performance/', views.platform_performance, name='platform_performance'),
    path('platform/performance/apply/', views.platform_performance_apply, name='platform_performance_apply'),
    path('writer/', views.writer_home, name='writer_home'),
    path('writer/start-article/', views.writer_start_article, name='writer_start_article'),
    path('writer/generate-titles/', views.writer_generate_titles, name='writer_generate_titles'),
    path('writer/select-title/', views.writer_select_title, name='writer_select_title'),
    path('writer/generate-bodies/', views.writer_generate_bodies, name='writer_generate_bodies'),
    path('writer/select-body/', views.writer_select_body, name='writer_select_body'),
    path('writer/article/<int:article_id>/', views.article_detail, name='article_detail'),
    path('writer/history/', views.writer_article_history, name='writer_article_history'),
    path('writer/notices/', views.writer_notices, name='writer_notices'),
    path('writer/notices/<int:notice_id>/read/', views.writer_notice_read, name='writer_notice_read'),
    path('user/', views.user_home, name='user_home'),
    path('user/platform-check/', views.user_platform_check, name='user_platform_check'),
    path('user/switch-platform/', views.user_switch_platform, name='user_switch_platform'),
    path('user/browse/<int:platform_id>/', views.user_browse, name='user_browse'),
    path('user/article/<int:article_id>/', views.user_article_view, name='user_article_view'),
    path('user/article/<int:article_id>/like/', views.user_article_like, name='user_article_like'),
    path('user/article/<int:article_id>/collect/', views.user_article_collect, name='user_article_collect'),
    path('user/article/<int:article_id>/read-complete/', views.user_article_read_complete, name='user_article_read_complete'),
    path('user/article/<int:article_id>/follow/', views.user_article_follow, name='user_article_follow'),
    path('user/article/<int:article_id>/unfollow/', views.user_article_unfollow, name='user_article_unfollow'),
    path('user/article/<int:article_id>/comment/', views.user_article_add_comment, name='user_article_add_comment'),
]
