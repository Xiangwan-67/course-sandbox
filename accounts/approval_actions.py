# -*- coding: utf-8 -*-
"""管理员审批操作：供 ModelAdmin.actions 与沙盘运营台共用。"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from django.utils import timezone

from accounts.action_logger import action_log, admin_action_log, regulator_action_log
from accounts.platform_scope import jurisdiction_for_regulator_account
from accounts.models import (
    PlatformAccount,
    PlatformPatrolApplication,
    PlatformSelfPatrolApplication,
    PlatformSpotCheckResult,
    RegulationAction,
    RegulatorFineApplication,
    RegulatorFineRecord,
)


def _admin_account(request) -> str:
    return getattr(request.user, 'username', str(request.user))


def _now():
    return timezone.now()


# ----- 监管罚款 -----

def approve_regulator_fine_queryset(request, queryset) -> None:
    from accounts.views import _get_current_round, _get_fine_tier_value

    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        j = jurisdiction_for_regulator_account((app.申请人账号 or '').strip())
        if not j or int(app.平台编号) not in j:
            admin_action_log(
                f"管理员批准罚款申请已跳过 申请编号={app.pk} 原因=申请人负责平台与平台编号不符 applicant={app.申请人账号!r}"
            )
            continue
        exec_r = _get_current_round()
        val = _get_fine_tier_value(app.罚款档次)
        RegulatorFineRecord.objects.create(
            执行轮次=exec_r,
            平台编号=app.平台编号,
            平台名称=app.平台名称,
            罚款档次=app.罚款档次,
            申请记录=app,
            监管成本数值=val,
        )
        app.申请状态 = 'approved'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
        tier_label = dict(RegulatorFineApplication.FINE_TIER_CHOICES).get(app.罚款档次, app.罚款档次)
        admin_action_log(
            f"管理员批准罚款申请 申请编号={app.pk} 平台编号={app.平台编号} 平台名称={app.平台名称} "
            f"罚款档次={tier_label} 执行轮次={exec_r}"
        )
        regulator_action_log(
            f"罚款申请 id={app.pk} 已通过 平台={app.平台名称} 平台编号={app.平台编号} "
            f"罚款档次={tier_label} 执行轮次={exec_r}"
        )


def reject_regulator_fine_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        app.申请状态 = 'rejected'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
        tier_label = dict(RegulatorFineApplication.FINE_TIER_CHOICES).get(app.罚款档次, app.罚款档次)
        admin_action_log(
            f"管理员驳回罚款申请 申请编号={app.pk} 平台编号={app.平台编号} 平台名称={app.平台名称} "
            f"罚款档次={tier_label}"
        )
        regulator_action_log(
            f"罚款申请 id={app.pk} 已驳回 平台={app.平台名称} 平台编号={app.平台编号} "
            f"罚款档次={tier_label}"
        )


# ----- 监管专项整治 -----

def approve_regulation_action_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        platform_ids = [int(pid) for pid in (app.整治平台编号列表 or [])]
        j = jurisdiction_for_regulator_account((app.申请人账号 or '').strip())
        if not j or not set(platform_ids).issubset(j):
            regulator_action_log(
                f"管理员审核专项整治已跳过 action_id={app.行动编号} 原因=与申请人负责平台不符 applicant={app.申请人账号!r}"
            )
            continue
        platform_names = list(app.整治平台名称列表 or [])
        start_round = int(app.当前轮次) + 1
        duration = int(app.整治持续轮次 or 8)
        end_round = start_round + duration - 1

        app.申请状态 = 'approved'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])

        for idx, pid in enumerate(platform_ids):
            pname = platform_names[idx] if idx < len(platform_names) else f'平台{pid + 1}'
            ra = RegulationAction.objects.create(
                行动编号=app.行动编号,
                当前轮次=app.当前轮次,
                整治平台编号=pid,
                整治平台名称=pname,
                整治持续轮次=duration,
                开始轮次=start_round,
                结束轮次=end_round,
                整治原因=app.整治原因,
                其他原因说明=app.其他原因说明,
                状态='active',
                申请记录=app,
            )
            PlatformSpotCheckResult.objects.create(
                专项行动=ra,
                行动编号=ra.行动编号,
                整治平台编号=ra.整治平台编号,
                整治平台名称=ra.整治平台名称,
                是否查看=False,
            )

        regulator_action_log(
            f"管理员审核通过监管专项整治 action_id={app.行动编号} "
            f"platforms={platform_names} round={app.当前轮次} "
            f"active_range={start_round}-{end_round} admin={admin_account}"
        )


def reject_regulation_action_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        app.申请状态 = 'rejected'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
        regulator_action_log(
            f"管理员驳回监管专项整治申请 action_id={app.行动编号} "
            f"platforms={app.整治平台名称列表 or []} round={app.当前轮次} admin={admin_account}"
        )


# ----- 平台巡查 -----

def approve_platform_patrol_queryset(request, queryset, message_user: Optional[Callable] = None) -> None:
    from accounts.views import _execute_platform_patrol

    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        j = jurisdiction_for_regulator_account((app.申请人账号 or '').strip())
        if not j or int(app.平台编号) not in j:
            if message_user:
                message_user(request, f'申请 id={app.pk} 与申请人负责平台不符，已跳过', level='ERROR')
            continue
        _, err = _execute_platform_patrol(app)
        if err:
            if message_user:
                message_user(request, f'申请 id={app.pk} 未通过：{err}', level='ERROR')
            continue

        app.申请状态 = 'approved'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])

        admin_action_log(
            f"管理员已批准监管机构-平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
        )


def reject_platform_patrol_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        app.申请状态 = 'rejected'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
        admin_action_log(
            f"管理员已驳回监管机构-平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
        )


# ----- 平台发起的平台巡查 -----

def approve_platform_self_patrol_queryset(request, queryset, message_user: Optional[Callable] = None) -> None:
    from accounts.views import _execute_platform_self_patrol

    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        if not PlatformAccount.objects.filter(
            账号=(app.申请人账号 or '').strip(),
            所属平台=int(app.平台编号),
        ).exists():
            if message_user:
                message_user(request, f'申请 id={app.pk} 与平台申请人账号不符，已跳过', level='ERROR')
            continue
        _, err = _execute_platform_self_patrol(app)
        if err:
            if message_user:
                message_user(request, f'申请 id={app.pk} 未通过：{err}', level='ERROR')
            continue

        app.申请状态 = 'approved'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])

        admin_action_log(
            f"管理员已批准平台发起的平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
        )


def reject_platform_self_patrol_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for app in queryset.filter(申请状态='pending'):
        app.申请状态 = 'rejected'
        app.管理员确认账号 = admin_account
        app.管理员确认时间 = now
        app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
        admin_action_log(
            f"管理员已驳回平台发起的平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
        )


# ----- 平台治理措施 -----

def approve_platform_governance_measure_queryset(request, queryset) -> None:
    from accounts.governance_notices import maybe_dispatch_governance_notice_after_approval

    admin_account = _admin_account(request)
    now = _now()
    for rec in queryset.filter(status='pending'):
        rec.status = 'active'
        rec.管理员确认账号 = admin_account
        rec.管理员确认时间 = now
        rec.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员确认治理措施生效 | 管理员={admin_account} measure_id={rec.pk} 平台={rec.平台} type={rec.措施类型} 生效轮次={rec.生效轮次} config_id={rec.config_id}"
        )
        maybe_dispatch_governance_notice_after_approval(rec)


def reject_platform_governance_measure_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for rec in queryset.filter(status='pending'):
        rec.status = 'rejected'
        rec.管理员确认账号 = admin_account
        rec.管理员确认时间 = now
        rec.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员驳回治理措施 | 管理员={admin_account} measure_id={rec.pk} 平台={rec.平台} type={rec.措施类型} config_id={rec.config_id}"
        )


# ----- 绩效方案 -----

def approve_platform_performance_scheme_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for scheme in queryset.filter(status='pending'):
        scheme.status = 'active'
        scheme.管理员确认账号 = admin_account
        scheme.管理员确认时间 = now
        scheme.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员确认绩效方案生效 | 管理员={admin_account} 方案ID={scheme.pk} "
            f"平台={scheme.平台} 生效轮次={scheme.生效轮次} "
            f"w1={scheme.w1_click} w2={scheme.w2_finish} w3={scheme.w3_collect}"
        )


def reject_platform_performance_scheme_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for scheme in queryset.filter(status='pending'):
        scheme.status = 'cancelled'
        scheme.管理员确认账号 = admin_account
        scheme.管理员确认时间 = now
        scheme.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员取消/驳回绩效方案 | 管理员={admin_account} 方案ID={scheme.pk} "
            f"平台={scheme.平台} 生效轮次={scheme.生效轮次}"
        )


# ----- 功能包配置（标题党 / 流量 / 举报 / 收益） -----

def approve_clickbait_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'active'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员确认标题党检测配置生效 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def reject_clickbait_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'rejected'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员驳回标题党检测配置 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def approve_traffic_penalty_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'active'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员确认流量惩罚配置生效 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def reject_traffic_penalty_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'rejected'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员驳回流量惩罚配置 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def approve_user_report_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'active'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员确认用户举报配置生效 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def reject_user_report_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'rejected'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员驳回用户举报配置 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def approve_revenue_penalty_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'active'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员确认收益惩罚配置生效 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


def reject_revenue_penalty_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'rejected'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(f"管理员驳回收益惩罚配置 | 管理员={admin_account} config_id={cfg.pk} 平台={cfg.platform_id}")


# ----- 账号健康分配置 -----

def approve_account_health_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'active'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员确认账号健康分配置生效 | 管理员={admin_account} config_id={cfg.pk} platform_id={cfg.platform_id}"
        )


def reject_account_health_config_queryset(request, queryset) -> None:
    admin_account = _admin_account(request)
    now = _now()
    for cfg in queryset.filter(status='pending'):
        cfg.status = 'rejected'
        cfg.管理员确认账号 = admin_account
        cfg.管理员确认时间 = now
        cfg.save(update_fields=['status', '管理员确认账号', '管理员确认时间'])
        action_log(
            f"管理员驳回账号健康分配置 | 管理员={admin_account} config_id={cfg.pk} platform_id={cfg.platform_id}"
        )


# ----- 单条审批（运营台）：巡查可能返回错误 -----

def approve_single_platform_patrol(request, pk: int) -> Tuple[bool, str]:
    app = PlatformPatrolApplication.objects.filter(pk=pk, 申请状态='pending').first()
    if not app:
        return False, '未找到待审核的巡查申请'
    j = jurisdiction_for_regulator_account((app.申请人账号 or '').strip())
    if not j or int(app.平台编号) not in j:
        return False, '申请人负责平台与申请平台不符，无法批准'
    from accounts.views import _execute_platform_patrol

    admin_account = _admin_account(request)
    now = _now()
    _, err = _execute_platform_patrol(app)
    if err:
        return False, err
    app.申请状态 = 'approved'
    app.管理员确认账号 = admin_account
    app.管理员确认时间 = now
    app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
    admin_action_log(
        f"管理员已批准监管机构-平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
    )
    return True, ''


def approve_single_platform_self_patrol(request, pk: int) -> Tuple[bool, str]:
    app = PlatformSelfPatrolApplication.objects.filter(pk=pk, 申请状态='pending').first()
    if not app:
        return False, '未找到待审核的巡查申请'
    if not PlatformAccount.objects.filter(
        账号=(app.申请人账号 or '').strip(),
        所属平台=int(app.平台编号),
    ).exists():
        return False, '申请人账号与平台不符，无法批准'
    from accounts.views import _execute_platform_self_patrol

    admin_account = _admin_account(request)
    now = _now()
    _, err = _execute_platform_self_patrol(app)
    if err:
        return False, err
    app.申请状态 = 'approved'
    app.管理员确认账号 = admin_account
    app.管理员确认时间 = now
    app.save(update_fields=['申请状态', '管理员确认账号', '管理员确认时间'])
    admin_action_log(
        f"管理员已批准平台发起的平台巡查申请 申请编号：{app.pk}、平台名称：{app.平台名称}、平台编号：{app.平台编号}"
    )
    return True, ''
