# -*- coding: utf-8 -*-
"""结束本轮：与 HTTP end_round、管理命令共用同一套逻辑。"""
from __future__ import annotations

from typing import Any, Dict, List

from django.db.models import F


def perform_end_round() -> Dict[str, Any]:
    """结算本轮收益、周期利润（若命中），再将模拟轮次 +1。

    与 accounts.views.end_round 行为一致（含用户举报处理）。
    返回 dict：round_to_settle, new_round, settled, settled_cycle_profit
    """
    # 延迟导入，避免 accounts.views 与 round_ops 循环依赖
    from accounts.action_logger import action_log
    from accounts.models import ProfitWeightConfig, SimulationRound
    from accounts.platform_scope import valid_platform_ids
    from accounts.views import (
        _get_current_round,
        _get_effective_profit_config,
        _process_article_reports,
        _recover_writer_health_for_platform,
        _run_regulation_auto_patrols_for_round_transition,
        _settle_article_revenue,
        _settle_cycle_profit,
    )

    SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
    round_to_settle = _get_current_round()
    settled: List[Dict[str, Any]] = []
    settled_cycle_profit: List[Dict[str, Any]] = []
    for pid in sorted(valid_platform_ids()):
        _recover_writer_health_for_platform(pid, round_to_settle)
        _process_article_reports(pid, round_to_settle)
        _settle_article_revenue(pid, round_to_settle)
        cfg = _get_effective_profit_config(round_to_settle, pid) or ProfitWeightConfig.objects.order_by('-id').first()
        period = int(getattr(cfg, '利润展示窗口轮数', 4) or 4)
        period = max(1, period)
        if round_to_settle % period == 0:
            cycle_index = round_to_settle // period
            start_round = round_to_settle - period + 1
            rec = _settle_cycle_profit(pid, cycle_index, start_round, round_to_settle)
            if rec:
                settled_cycle_profit.append({'platform_id': pid, 'cycle_index': cycle_index})
        settled.append({'platform_id': pid})

    from accounts.round_snapshot import capture_round_snapshot

    capture_round_snapshot(round_to_settle)

    SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
    new_round = _get_current_round()
    from accounts.governance_notices import dispatch_governance_notices_for_round

    dispatch_governance_notices_for_round(new_round)
    _run_regulation_auto_patrols_for_round_transition(round_to_settle, new_round)
    action_log(
        f"结束本轮 round={round_to_settle} -> {new_round} | 已文章收益结算={settled} "
        f"| 周期利润结算={settled_cycle_profit}"
    )
    return {
        'round_to_settle': round_to_settle,
        'new_round': new_round,
        'settled': settled,
        'settled_cycle_profit': settled_cycle_profit,
    }
