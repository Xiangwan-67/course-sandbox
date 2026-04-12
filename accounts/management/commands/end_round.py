# -*- coding: utf-8 -*-
"""
结束本轮：先按平台结算本轮文章收益，再将模拟轮次+1。
用法: python manage.py end_round
"""
from django.core.management.base import BaseCommand
from django.db.models import F

from accounts.models import SimulationRound
from accounts.action_logger import action_log


class Command(BaseCommand):
    help = '结算本轮文章收益后，将当前模拟轮次+1，不删任何数据'

    def handle(self, *args, **options):
        from accounts.views import _get_current_round, _settle_article_revenue, _settle_platform_profit

        SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
        round_to_settle = _get_current_round()
        settled = []
        for pid in (0, 1):
            _settle_article_revenue(pid, round_to_settle)
            _settle_platform_profit(pid, round_to_settle)
            settled.append({'platform_id': pid})
        SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
        new_round = SimulationRound.objects.get(pk=1).当前轮次
        action_log(
            f"结束本轮(管理命令) round={round_to_settle} -> {new_round} | 已文章收益结算+平台利润占位={settled}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'本轮 {round_to_settle} 已结算文章收益，当前轮次已更新为: {new_round}'
            )
        )
