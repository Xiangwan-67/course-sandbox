# -*- coding: utf-8 -*-
"""
结束本轮：先按平台结算本轮文章收益；若命中周期末则结算周期利润；再将模拟轮次+1。
用法: python manage.py end_round
"""
from django.core.management.base import BaseCommand
from django.db.models import F

from accounts.models import SimulationRound
from accounts.action_logger import action_log


class Command(BaseCommand):
    help = '结算本轮文章收益；周期末结算周期利润；然后将当前模拟轮次+1'

    def handle(self, *args, **options):
        from accounts.views import (
            _get_current_round,
            _recover_writer_health_for_platform,
            _settle_article_revenue,
            _settle_cycle_profit,
            _get_effective_profit_config,
            _run_regulation_auto_patrols_for_round_transition,
        )
        from accounts.models import ProfitWeightConfig

        SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
        round_to_settle = _get_current_round()
        settled = []
        settled_cycle_profit = []
        for pid in (0, 1):
            _recover_writer_health_for_platform(pid, round_to_settle)
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
        SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
        new_round = SimulationRound.objects.get(pk=1).当前轮次
        _run_regulation_auto_patrols_for_round_transition(round_to_settle, new_round)
        action_log(
            f"结束本轮(管理命令) round={round_to_settle} -> {new_round} | 已文章收益结算={settled} "
            f"| 周期利润结算={settled_cycle_profit}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'本轮 {round_to_settle} 已结算文章收益，周期利润结算={settled_cycle_profit}，当前轮次已更新为: {new_round}'
            )
        )
