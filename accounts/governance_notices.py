# -*- coding: utf-8 -*-
"""平台治理措施 → 写手收件箱：在生效轮次（结束本轮后）投递一次；管理员晚批准时补投递。"""
from __future__ import annotations


def create_inbox_rows_for_measure(measure) -> None:
    """为该平台全体写手创建收件箱行（每名写手每条措施至多一行）。"""
    from accounts.models import WriterAccount, WriterGovernanceNotice

    # 写手端「平台通知」仅通知账号健康分治理措施
    if getattr(measure, '措施类型', None) != 'account_health_rule':
        return

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
    from accounts.views import _sync_writer_push_ratios_for_account_health_platform

    measures = PlatformGovernanceMeasure.objects.filter(
        status='active',
        生效轮次=new_round,
        措施类型='account_health_rule',
    )
    for m in measures:
        create_inbox_rows_for_measure(m)
        _sync_writer_push_ratios_for_account_health_platform(m.平台, new_round)


def maybe_dispatch_governance_notice_after_approval(measure) -> None:
    """管理员批准后：若当前轮次已达生效轮次（含晚于生效轮次才批准），立即补投递。"""
    from accounts.views import _get_current_round, _sync_writer_push_ratios_for_account_health_platform

    if measure.status != 'active':
        return
    # 写手端「平台通知」仅通知账号健康分治理措施
    if getattr(measure, '措施类型', None) != 'account_health_rule':
        return
    if int(measure.生效轮次) <= _get_current_round():
        create_inbox_rows_for_measure(measure)
        _sync_writer_push_ratios_for_account_health_platform(measure.平台, _get_current_round())
