# -*- coding: utf-8 -*-
"""标题党判定来源与事件追溯。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    Article,
    ArticleReport,
    ClickbaitDetectionResult,
    SimulationRound,
    UserReportConfig,
)
from accounts.views import _compute_platform_patrol_metrics, _process_article_reports


@pytest.mark.django_db
def test_patrol_judgment_does_not_set_clickbait_source(active_clickbait_config, writer_accounts):
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)
    writer = writer_accounts[0]
    pid = writer.所属平台

    art = Article.objects.create(
        写手账号=writer.账号,
        轮次=2,
        标题="patrol",
        标题夸张度_校准值=5,
        内容相关度_校准值=1,
        is_clickbait=None,
        clickbait_source='',
        is_published=True,
    )

    metrics, err = _compute_platform_patrol_metrics(
        pid, Decimal('1'), 2, 2, exec_round=3, rng_seed=99
    )
    assert err is None
    assert metrics['rate'] == Decimal('1')

    art.refresh_from_db()
    assert art.clickbait_source == ''
    assert art.is_clickbait is None

    assert ClickbaitDetectionResult.objects.filter(文章=art, 判定来源='patrol').count() == 1


@pytest.mark.django_db
def test_patrol_records_all_sampled_articles(active_clickbait_config, writer_accounts):
    """抽中文章无论已有 is_clickbait 与否，均写 patrol 审计行。"""
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)
    writer = writer_accounts[0]
    pid = writer.所属平台

    Article.objects.create(
        写手账号=writer.账号, 轮次=2, 标题='already_true',
        标题夸张度_校准值=5, 内容相关度_校准值=1, is_clickbait=True, clickbait_source='auto',
        is_published=True,
    )
    Article.objects.create(
        写手账号=writer.账号, 轮次=2, 标题='already_false',
        标题夸张度_校准值=1, 内容相关度_校准值=5, is_clickbait=False, clickbait_source='auto',
        is_published=True,
    )

    metrics, err = _compute_platform_patrol_metrics(
        pid, Decimal('1'), 2, 2, exec_round=3, rng_seed=7
    )
    assert err is None
    assert metrics['n'] == 2
    assert ClickbaitDetectionResult.objects.filter(平台=pid, 判定来源='patrol').count() == 2


@pytest.mark.django_db
def test_user_report_sets_clickbait_source(
    db, platform_account, active_clickbait_config, writer_accounts
):
    from accounts.models import PlatformGovernanceMeasure

    round_num = 2
    SimulationRound.objects.filter(pk=1).update(当前轮次=round_num + 1)

    cfg = UserReportConfig.objects.create(
        platform_id=platform_account.所属平台,
        举报触发阈值=Decimal('0.01'),
        审核方式='auto',
        status='active',
        提交人账号='admin',
        管理员确认账号='admin',
    )
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        措施类型='user_report',
        轮次=1,
        生效轮次=round_num,
        措施内容={},
        config_id=cfg.pk,
        发布人账号=platform_account.账号,
        status='active',
        管理员确认账号='admin',
    )

    writer = writer_accounts[0]
    art = Article.objects.create(
        写手账号=writer.账号,
        轮次=round_num,
        标题='reported',
        标题夸张度_校准值=5,
        内容相关度_校准值=1,
        点击量=10,
        is_clickbait=None,
        is_published=True,
    )
    ArticleReport.objects.create(
        platform_id=platform_account.所属平台,
        文章=art,
        举报人='pytest_user_1',
        举报轮次=round_num,
        审核状态='pending',
    )
    art.report_count_current_round = 1
    art.save(update_fields=['report_count_current_round'])

    _process_article_reports(platform_account.所属平台, round_num)

    art.refresh_from_db()
    assert art.clickbait_source == 'user_report'
    assert art.is_clickbait is True
    assert art.clickbait_auto_executed is False

    ev = ClickbaitDetectionResult.objects.filter(文章=art, 判定来源='user_report').first()
    assert ev is not None
    assert ev.检测结果 is True
