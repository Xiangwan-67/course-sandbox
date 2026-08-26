# -*- coding: utf-8 -*-
"""平台/监管巡查标题党率：不依赖「标题党检测」治理包是否发布。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.clickbait_judge import judge_clickbait_by_config
from accounts.models import Article, SimulationRound
from accounts.views import _compute_platform_patrol_metrics, is_clickbait


@pytest.mark.django_db
def test_judge_clickbait_by_config_without_governance_measure(active_clickbait_config, writer_accounts):
    """有 active 配置、无治理包时，审计口径仍可判定标题党。"""
    writer = writer_accounts[0]
    art = Article.objects.create(
        写手账号=writer.账号,
        轮次=1,
        标题="t",
        标题夸张度_校准值=5,
        内容相关度_校准值=2,
        is_clickbait=None,
        is_published=True,
    )
    assert judge_clickbait_by_config(art, writer.所属平台) is True
    assert is_clickbait(art, writer.所属平台, 1) is False


@pytest.mark.django_db
def test_patrol_metrics_counts_clickbait_without_measure(active_clickbait_config, writer_accounts):
    """未发布 clickbait_detection 治理包时，巡查抽样仍可按配置统计标题党率。"""
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)
    writer = writer_accounts[0]
    pid = writer.所属平台

    Article.objects.create(
        写手账号=writer.账号,
        轮次=2,
        标题="hit",
        标题夸张度_校准值=5,
        内容相关度_校准值=1,
        is_clickbait=None,
        is_published=True,
    )
    Article.objects.create(
        写手账号=writer.账号,
        轮次=2,
        标题="miss",
        标题夸张度_校准值=2,
        内容相关度_校准值=4,
        is_clickbait=None,
        is_published=True,
    )

    metrics, err = _compute_platform_patrol_metrics(
        pid, Decimal("1"), 2, 2, exec_round=3, rng_seed=42
    )
    assert err is None
    assert metrics["n"] == 2
    assert metrics["rate"] == Decimal("0.5")
