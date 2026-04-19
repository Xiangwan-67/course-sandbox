# -*- coding: utf-8 -*-
"""平台治理措施 → 写手收件箱：在生效轮次（结束本轮后）投递一次；管理员晚批准时补投递。"""
from __future__ import annotations


def create_inbox_rows_for_measure(measure) -> None:
    """为该平台全体写手创建收件箱行（每名写手每条措施至多一行）。"""
    from accounts.models import WriterAccount, WriterGovernanceNotice

    eff = int(measure.生效轮次)
    accounts = list(
        WriterAccount.objects.filter(所属平台=measure.平台).values_list('账号', flat=True)
    )
    for a in accounts:
        WriterGovernanceNotice.objects.get_or_create(
            写手账号=a,
            measure=measure,
            defaults={'投递轮次': eff, '是否已读': False},
        )


def dispatch_governance_notices_for_round(new_round: int) -> None:
    """模拟轮次进入 new_round 时，对「本生效轮次 == new_round」且已生效的措施投递收件箱。"""
    from accounts.models import PlatformGovernanceMeasure

    measures = PlatformGovernanceMeasure.objects.filter(status='active', 生效轮次=new_round)
    for m in measures:
        create_inbox_rows_for_measure(m)


def maybe_dispatch_governance_notice_after_approval(measure) -> None:
    """管理员批准后：若当前轮次已达生效轮次（含晚于生效轮次才批准），立即补投递。"""
    from accounts.views import _get_current_round

    if measure.status != 'active':
        return
    if int(measure.生效轮次) <= _get_current_round():
        create_inbox_rows_for_measure(measure)
