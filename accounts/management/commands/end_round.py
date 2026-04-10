# -*- coding: utf-8 -*-
"""
结束本轮：将模拟轮次+1。在用户们结束阅读并退出后由管理员或脚本调用，进入下一轮（用户端列表只查当前轮次，等效清空列表）。
用法: python manage.py end_round
"""
from django.core.management.base import BaseCommand
from django.db.models import F

from accounts.models import SimulationRound


class Command(BaseCommand):
    help = '将当前模拟轮次+1，不删任何数据'

    def handle(self, *args, **options):
        obj, _ = SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
        SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
        new_round = SimulationRound.objects.get(pk=1).当前轮次
        self.stdout.write(self.style.SUCCESS(f'当前轮次已更新为: {new_round}'))
