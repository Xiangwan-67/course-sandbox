# -*- coding: utf-8 -*-
"""标题党判定口径：与「标题党检测」治理包发布解耦，供巡查/举报等审计场景共用。"""
from __future__ import annotations

from accounts.models import ClickbaitDetectionConfig

DEFAULT_X_THRESHOLD = 4
DEFAULT_Y_THRESHOLD = 3


def _thresholds_from_config(cfg) -> tuple[int, int]:
    if not cfg:
        return DEFAULT_X_THRESHOLD, DEFAULT_Y_THRESHOLD
    try:
        x_th = int(getattr(cfg, '标题夸张度阈值X', DEFAULT_X_THRESHOLD) or DEFAULT_X_THRESHOLD)
    except Exception:
        x_th = DEFAULT_X_THRESHOLD
    try:
        y_th = int(getattr(cfg, '内容相关度阈值Y', DEFAULT_Y_THRESHOLD) or DEFAULT_Y_THRESHOLD)
    except Exception:
        y_th = DEFAULT_Y_THRESHOLD
    return x_th, y_th


def judge_clickbait_by_config(article, platform_id: int) -> bool:
    """按平台 active 的 ClickbaitDetectionConfig 判定；无配置时用默认 X/Y。

    不检查 PlatformGovernanceMeasure（标题党检测治理包）是否发布。
    规则：标题夸张度 >= X 且 内容相关度 < Y → 标题党。
    """
    cfg = (
        ClickbaitDetectionConfig.objects
        .filter(platform_id=platform_id, status='active')
        .order_by('-id')
        .first()
    )
    x_th, y_th = _thresholds_from_config(cfg)
    x_val = int(article.标题夸张度_校准值 or article.标题夸张度_初始值 or 0)
    y_val = int(article.内容相关度_校准值 or article.内容相关度_初始值 or 0)
    return (x_val >= x_th) and (y_val < y_th)
