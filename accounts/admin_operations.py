# -*- coding: utf-8 -*-
"""Django Admin 挂载的沙盘运营台页面。"""
from __future__ import annotations

from typing import Any, Dict

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts import approval_actions
from accounts.models import (
    AccountHealthConfig,
    ClickbaitDetectionConfig,
    PlatformGovernanceMeasure,
    PlatformPatrolApplication,
    PlatformPerformanceScheme,
    RegulationActionApplication,
    RegulatorFineApplication,
    RevenuePenaltyConfig,
    SimulationRound,
    TrafficPenaltyConfig,
    UserReportConfig,
)

TAB_KEYS = ('regulator', 'measure', 'params', 'performance')


def _current_round() -> int:
    obj, _ = SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
    return int(obj.当前轮次)


def _gather_pending() -> Dict[str, Any]:
    return {
        'regulation_applications': list(
            RegulationActionApplication.objects.filter(申请状态='pending').order_by('-创建时间', '-id')[:200]
        ),
        'patrol_applications': list(
            PlatformPatrolApplication.objects.filter(申请状态='pending').order_by('-创建时间', '-id')[:200]
        ),
        'fine_applications': list(
            RegulatorFineApplication.objects.filter(申请状态='pending').order_by('-创建时间', '-id')[:200]
        ),
        'measures': list(
            PlatformGovernanceMeasure.objects.filter(status='pending').order_by('-轮次', '-创建时间', '-id')[:200]
        ),
        'clickbait_configs': list(
            ClickbaitDetectionConfig.objects.filter(status='pending').order_by('-创建时间', '-id')[:200]
        ),
        'traffic_configs': list(
            TrafficPenaltyConfig.objects.filter(status='pending').order_by('-创建时间', '-id')[:200]
        ),
        'report_configs': list(
            UserReportConfig.objects.filter(status='pending').order_by('-创建时间', '-id')[:200]
        ),
        'revenue_configs': list(
            RevenuePenaltyConfig.objects.filter(status='pending').order_by('-创建时间', '-id')[:200]
        ),
        'health_configs': list(
            AccountHealthConfig.objects.filter(status='pending').order_by('-创建时间', '-id')[:200]
        ),
        'performance_schemes': list(
            PlatformPerformanceScheme.objects.filter(status='pending').order_by('-生效轮次', '-创建时间', '-id')[:200]
        ),
    }


def _redirect_with_tab(tab: str) -> HttpResponseRedirect:
    tab = tab if tab in TAB_KEYS else 'regulator'
    url = reverse('admin_sandbox_ops')
    return HttpResponseRedirect(f'{url}?tab={tab}')


@require_http_methods(['GET', 'POST'])
def sandbox_operations_dashboard(request: HttpRequest) -> HttpResponse:
    tab = (request.GET.get('tab') or request.POST.get('tab') or 'regulator').strip()
    if tab not in TAB_KEYS:
        tab = 'regulator'

    if request.method == 'POST':
        action = (request.POST.get('op') or '').strip()
        if action == 'end_round':
            from accounts.round_ops import perform_end_round

            perform_end_round()
            messages.success(request, '已结束本轮：已结算并推进模拟轮次。')
            return _redirect_with_tab('regulator')

        if action in ('approve', 'reject'):
            model_key = (request.POST.get('model') or '').strip()
            pk_raw = request.POST.get('pk')
            try:
                pk = int(pk_raw)
            except (TypeError, ValueError):
                messages.error(request, '无效的主键。')
                return _redirect_with_tab(tab)

            err = _dispatch_approval(request, model_key, pk, approve=(action == 'approve'))
            if err:
                messages.error(request, err)
            else:
                messages.success(request, '已通过' if action == 'approve' else '已驳回')
            return _redirect_with_tab(tab)

        messages.error(request, '未知操作。')
        return _redirect_with_tab(tab)

    pending = _gather_pending()
    ctx = {
        'title': '沙盘运营台',
        'current_round': _current_round(),
        'tab': tab,
        **pending,
    }
    return render(request, 'admin/sandbox_operations.html', ctx)


def _dispatch_approval(request: HttpRequest, model_key: str, pk: int, approve: bool) -> str:
    """返回错误信息，空字符串表示成功。"""

    def one(model, approve_fn, reject_fn) -> str:
        qs = model.objects.filter(pk=pk)
        if not qs.exists():
            return '记录不存在'
        if approve:
            approve_fn(request, qs)
        else:
            reject_fn(request, qs)
        return ''

    if model_key == 'regulation_action_application':
        return one(
            RegulationActionApplication,
            approval_actions.approve_regulation_action_queryset,
            approval_actions.reject_regulation_action_queryset,
        )

    if model_key == 'platform_patrol_application':
        if approve:
            ok, err = approval_actions.approve_single_platform_patrol(request, pk)
            return err if not ok else ''
        approval_actions.reject_platform_patrol_queryset(
            request, PlatformPatrolApplication.objects.filter(pk=pk)
        )
        return ''

    if model_key == 'regulator_fine_application':
        return one(
            RegulatorFineApplication,
            approval_actions.approve_regulator_fine_queryset,
            approval_actions.reject_regulator_fine_queryset,
        )

    if model_key == 'platform_governance_measure':
        return one(
            PlatformGovernanceMeasure,
            approval_actions.approve_platform_governance_measure_queryset,
            approval_actions.reject_platform_governance_measure_queryset,
        )

    if model_key == 'clickbait_detection_config':
        return one(
            ClickbaitDetectionConfig,
            approval_actions.approve_clickbait_config_queryset,
            approval_actions.reject_clickbait_config_queryset,
        )

    if model_key == 'traffic_penalty_config':
        return one(
            TrafficPenaltyConfig,
            approval_actions.approve_traffic_penalty_config_queryset,
            approval_actions.reject_traffic_penalty_config_queryset,
        )

    if model_key == 'user_report_config':
        return one(
            UserReportConfig,
            approval_actions.approve_user_report_config_queryset,
            approval_actions.reject_user_report_config_queryset,
        )

    if model_key == 'revenue_penalty_config':
        return one(
            RevenuePenaltyConfig,
            approval_actions.approve_revenue_penalty_config_queryset,
            approval_actions.reject_revenue_penalty_config_queryset,
        )

    if model_key == 'account_health_config':
        return one(
            AccountHealthConfig,
            approval_actions.approve_account_health_config_queryset,
            approval_actions.reject_account_health_config_queryset,
        )

    if model_key == 'platform_performance_scheme':
        if approve:
            approval_actions.approve_platform_performance_scheme_queryset(
                request, PlatformPerformanceScheme.objects.filter(pk=pk)
            )
        else:
            approval_actions.reject_platform_performance_scheme_queryset(
                request, PlatformPerformanceScheme.objects.filter(pk=pk)
            )
        return ''

    return '未知的审批类型'
