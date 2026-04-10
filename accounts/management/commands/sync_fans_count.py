# -*- coding: utf-8 -*-
"""
根据「用户关注写手」表重新计算并更新写手、用户的粉丝数。
在后台直接增删关注记录后运行此命令即可同步粉丝数。
用法: python manage.py sync_fans_count
"""
from django.core.management.base import BaseCommand
from accounts.models import WriterAccount, UserAccount, UserFollowWriter


class Command(BaseCommand):
    help = '根据用户关注写手表重新计算写手与用户的粉丝数'

    def handle(self, *args, **options):
        # 写手粉丝数 = 关注该写手的用户数
        for w in WriterAccount.objects.all():
            cnt = UserFollowWriter.objects.filter(写手账号=w.账号).count()
            if w.粉丝数 != cnt:
                w.粉丝数 = cnt
                w.save(update_fields=['粉丝数'])
                self.stdout.write(f'写手 {w.账号}: 粉丝数 -> {cnt}')
        # 用户关注数 = 该用户关注的写手数
        for u in UserAccount.objects.all():
            cnt = u.关注列表.count()
            if u.关注数 != cnt:
                u.关注数 = cnt
                u.save(update_fields=['关注数'])
                self.stdout.write(f'用户 {u.账号}: 关注数 -> {cnt}')
        self.stdout.write(self.style.SUCCESS('粉丝数同步完成。'))
