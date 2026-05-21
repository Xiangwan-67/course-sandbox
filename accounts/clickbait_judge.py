# -*- coding: utf-8 -*-
"""标题党判定口径与审计事件落库。"""
from __future__ import annotations

from typing import Tuple

from accounts.models import Article, ClickbaitDetectionConfig, ClickbaitDetectionResult

DEFAULT_X_THRESHOLD = 4
DEFAULT_Y_THRESHOLD = 3

SOURCE_AUTO = 'auto'
SOURCE_USER_REPORT = 'user_report'
SOURCE_PATROL = 'patrol'

# 写入 Article.clickbait_source 的来源（巡查仅审计，不更新文章表）
ARTICLE_SOURCE_CHOICES = {SOURCE_AUTO, SOURCE_USER_REPORT}


def article_xy_values(article) -> Tuple[int, int]:
    x_val = int(article.标题夸张度_校准值 or article.标题夸张度_初始值 or 0)
    y_val = int(article.内容相关度_校准值 or article.内容相关度_初始值 or 0)
    return x_val, y_val


def get_active_clickbait_config(platform_id: int):
    return (
        ClickbaitDetectionConfig.objects
        .filter(platform_id=platform_id, status='active')
        .order_by('-id')
        .first()
    )


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
    """按 Config（或默认 X/Y）判定，不检查标题党检测治理包是否发布。"""
    cfg = get_active_clickbait_config(platform_id)
    x_th, y_th = _thresholds_from_config(cfg)
    x_val, y_val = article_xy_values(article)
    return (x_val >= x_th) and (y_val < y_th)


def record_clickbait_judgment(
    article: Article,
    platform_id: int,
    round_num: int,
    *,
    source: str,
    result: bool,
    update_article: bool = True,
) -> ClickbaitDetectionResult:
    """写入标题党检测结果表（审计）；auto/user_report 时覆盖 Article 当前结论。

    - 三种来源 auto / user_report / patrol 均落审计行（result 可为 True/False）
    - 仅 auto、user_report 更新 Article.is_clickbait 与 clickbait_source（后者为最新来源，覆盖）
    - auto 另将 clickbait_auto_executed=True（仅标记曾执行发文自动检测，举报不改动）
    - patrol 只记审计，不改 Article
    """
    cfg = get_active_clickbait_config(platform_id)
    x_th, y_th = _thresholds_from_config(cfg)
    x_val, y_val = article_xy_values(article)

    event = ClickbaitDetectionResult.objects.create(
        文章=article,
        轮次=round_num,
        平台=platform_id,
        标题夸张度X=x_val,
        内容相关度Y=y_val,
        判定阈值X=x_th,
        判定阈值Y=y_th,
        config_id=cfg.pk if cfg else None,
        判定来源=source,
        自动检测是否执行=(source == SOURCE_AUTO),
        检测结果=result,
    )

    if update_article and source in ARTICLE_SOURCE_CHOICES:
        article.is_clickbait = result
        article.clickbait_source = source
        update_fields = ['is_clickbait', 'clickbait_source']
        if source == SOURCE_AUTO:
            article.clickbait_auto_executed = True
            update_fields.append('clickbait_auto_executed')
        article.save(update_fields=update_fields)

    return event
