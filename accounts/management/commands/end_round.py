# -*- coding: utf-8 -*-
"""
结束本轮：先按平台结算本轮文章收益；若命中周期末则结算周期利润；再将模拟轮次+1。
用法: python manage.py end_round
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '结算本轮文章收益；周期末结算周期利润；然后将当前模拟轮次+1'

    def handle(self, *args, **options):
        from accounts.round_ops import perform_end_round

        result = perform_end_round()
        round_to_settle = result['round_to_settle']
        new_round = result['new_round']
        settled = result['settled']
        settled_cycle_profit = result['settled_cycle_profit']
        self.stdout.write(
            self.style.SUCCESS(
                f'本轮 {round_to_settle} 已结算文章收益，周期利润结算={settled_cycle_profit}，当前轮次已更新为: {new_round}'
            )
        )
