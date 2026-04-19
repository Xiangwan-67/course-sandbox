# -*- coding: utf-8 -*-
"""内容相关度档位 → 写作成本数值（全局映射，见 AdminBaseConfig.写作成本映射）。

写手通过选题/正文档位决定「内容相关度」，映射得到成本数值；结算时按固定系数（默认 −1）
从绩效收益中扣除，与平台绩效权重无关。
"""
from __future__ import annotations

from decimal import Decimal

from accounts.models import AdminBaseConfig

# 写作成本项：因子金额 = 写作成本系数 × 写作成本数值（默认 −1×数值，即全额扣除映射成本）
WRITING_COST_COEFFICIENT_DEFAULT = Decimal('-1')


def default_writing_cost_map():
    return {'1': 1, '2': 2, '3': 3, '4': 4, '5': 5}


def get_writing_cost_value_for_relevance(relevance_calibrated) -> Decimal:
    """由文章「内容相关度_校准值」（1～5）查全局映射，得到写作成本数值。"""
    rel = relevance_calibrated
    if rel is None:
        rel = 3
    try:
        rel = int(rel)
    except (TypeError, ValueError):
        rel = 3
    rel = max(1, min(5, rel))
    key_str = str(rel)
    cfg = AdminBaseConfig.objects.filter(pk=1).first()
    mapping = None
    if cfg and getattr(cfg, '写作成本映射', None):
        mapping = cfg.写作成本映射
    if not mapping:
        mapping = default_writing_cost_map()
    raw = mapping.get(key_str)
    if raw is None:
        raw = mapping.get(rel)
    if raw is None:
        raw = rel
    return Decimal(str(raw))
