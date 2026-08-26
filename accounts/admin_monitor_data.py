# -*- coding: utf-8 -*-
"""Admin 模拟看板数据组装。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from accounts.models import (
    Article,
    PlatformGovernanceMeasure,
    PlatformPatrolApplication,
    PlatformPatrolResult,
    PlatformSelfPatrolApplication,
    PlatformSelfPatrolResult,
    RegulationAction,
    RegulationActionApplication,
    RegulatorFineApplication,
    RegulatorFineRecord,
    SimulationRound,
    UserAccount,
    WriterAccount,
)
from accounts.platform_scope import platform_names_dict, valid_platform_ids

MEASURE_TYPE_LABELS: Dict[str, str] = {
    'account_health_rule': '账号健康分',
    'clickbait_detection': '标题党检测',
    'user_report': '用户举报',
    'traffic_penalty': '流量惩罚',
    'revenue_penalty': '收益惩罚',
    'performance_rule': '绩效规则',
}

MEASURE_TYPE_COLORS: Dict[str, str] = {
    'account_health_rule': '#7b1fa2',
    'clickbait_detection': '#c62828',
    'user_report': '#ef6c00',
    'traffic_penalty': '#1565c0',
    'revenue_penalty': '#f9a825',
    'performance_rule': '#2e7d32',
}

PLATFORM_DOT_COLORS: Dict[int, str] = {
    0: '#1976d2',
    1: '#d32f2f',
    2: '#ed6c02',
    3: '#7b1fa2',
}


def get_current_round() -> int:
    obj, _ = SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
    return int(obj.当前轮次)


def parse_round_param(raw: Optional[str], *, fallback: Optional[int] = None) -> int:
    fb = int(fallback if fallback is not None else get_current_round())
    if raw is None or str(raw).strip() == '':
        return fb
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return fb
    return n if n >= 1 else fb


def _writers_published_in_round(round_num: int) -> Set[str]:
    published: Set[str] = set()
    for art in Article.objects.filter(轮次=round_num, is_published=True).only('写手账号'):
        published.add(art.写手账号)
    return published


def build_writers_payload(round_num: int) -> Dict[str, Any]:
    published_set = _writers_published_in_round(round_num)
    names = platform_names_dict()
    platforms_out: List[Dict[str, Any]] = []
    total_writers = 0
    published_writers = 0

    for pid in sorted(valid_platform_ids()):
        writers = list(
            WriterAccount.objects.filter(所属平台=pid).order_by('账号').values('账号', '粉丝数')
        )
        writer_rows = []
        plat_published = 0
        for w in writers:
            account = w['账号']
            pub = account in published_set
            if pub:
                plat_published += 1
                published_writers += 1
            total_writers += 1
            writer_rows.append({
                'account': account,
                'published': pub,
                'fan_count': int(w.get('粉丝数') or 0),
            })
        platforms_out.append({
            'platform_id': pid,
            'platform_name': names.get(pid, f'平台{pid}'),
            'writer_count': len(writer_rows),
            'published_count': plat_published,
            'writers': writer_rows,
        })

    return {
        'round': round_num,
        'writers': {'platforms': platforms_out},
        'summary': {
            'total_writers': total_writers,
            'published_writers': published_writers,
            'all_published': total_writers > 0 and published_writers == total_writers,
        },
    }


def _measure_round_label(measure) -> str:
    parts = [f'生效第 {measure.生效轮次} 轮起']
    if measure.取消轮次 is not None:
        parts.append(f'至第 {measure.取消轮次} 轮前')
    return ' · '.join(parts)


def build_governance_payload(round_num: int) -> Dict[str, Any]:
    from accounts.views import _get_effective_governance_measure

    names = platform_names_dict()
    platforms_out: List[Dict[str, Any]] = []

    for pid in sorted(valid_platform_ids()):
        measures_out: List[Dict[str, Any]] = []
        for m_type, m_label in PlatformGovernanceMeasure.MEASURE_TYPE_CHOICES:
            measure = _get_effective_governance_measure(pid, m_type, round_num)
            if not measure:
                continue
            measures_out.append({
                'type': m_type,
                'name': MEASURE_TYPE_LABELS.get(m_type, m_label),
                'color': MEASURE_TYPE_COLORS.get(m_type, '#666'),
                'effective_round': int(measure.生效轮次),
                'cancel_round': int(measure.取消轮次) if measure.取消轮次 is not None else None,
                'label': _measure_round_label(measure),
            })
        platforms_out.append({
            'platform_id': pid,
            'platform_name': names.get(pid, f'平台{pid}'),
            'measures': measures_out,
        })

    return {
        'round': round_num,
        'governance': {'platforms': platforms_out},
        'regulator_round': _regulator_round_stats(round_num),
        'active_regulation_actions': _active_regulation_actions(round_num),
    }


def _users_by_platform() -> List[Dict[str, Any]]:
    names = platform_names_dict()
    out: List[Dict[str, Any]] = []
    for pid in sorted(valid_platform_ids()):
        accounts = list(
            UserAccount.objects.filter(所属平台=pid).order_by('账号').values_list('账号', flat=True)
        )
        out.append({
            'platform_id': pid,
            'platform_name': names.get(pid, f'平台{pid}'),
            'user_count': len(accounts),
            'color': PLATFORM_DOT_COLORS.get(pid, '#666'),
            'users': [{'account': a} for a in accounts],
        })
    return out


def _pending_counts() -> Dict[str, int]:
    return {
        'regulation': RegulationActionApplication.objects.filter(申请状态='pending').count(),
        'patrol': PlatformPatrolApplication.objects.filter(申请状态='pending').count(),
        'self_patrol': PlatformSelfPatrolApplication.objects.filter(申请状态='pending').count(),
        'fine': RegulatorFineApplication.objects.filter(申请状态='pending').count(),
    }


def _active_regulation_actions(round_num: int) -> List[Dict[str, Any]]:
    rows = []
    for ra in RegulationAction.objects.filter(
        状态='active',
        开始轮次__lte=round_num,
        结束轮次__gte=round_num,
    ).order_by('整治平台编号', '行动编号'):
        rows.append({
            'action_id': ra.行动编号,
            'platform_id': int(ra.整治平台编号),
            'platform_name': ra.整治平台名称,
            'start_round': int(ra.开始轮次),
            'end_round': int(ra.结束轮次),
            'reason': ra.整治原因,
        })
    return rows


def _regulator_round_stats(round_num: int) -> Dict[str, Any]:
    patrol_by_platform: Dict[int, int] = {}
    self_patrol_by_platform: Dict[int, int] = {}
    for pid in valid_platform_ids():
        patrol_by_platform[pid] = PlatformPatrolResult.objects.filter(
            平台编号=pid, 执行轮次=round_num,
        ).count()
        self_patrol_by_platform[pid] = PlatformSelfPatrolResult.objects.filter(
            平台编号=pid, 执行轮次=round_num,
        ).count()
    return {
        'patrol_by_platform': patrol_by_platform,
        'self_patrol_by_platform': self_patrol_by_platform,
    }


def _latest_fines_by_platform(round_num: int) -> List[Dict[str, Any]]:
    names = platform_names_dict()
    tier_labels = dict(RegulatorFineApplication.FINE_TIER_CHOICES)
    out: List[Dict[str, Any]] = []
    for pid in sorted(valid_platform_ids()):
        rec = (
            RegulatorFineRecord.objects.filter(平台编号=pid, 执行轮次__lte=round_num)
            .order_by('-执行轮次', '-id')
            .first()
        )
        if not rec:
            out.append({
                'platform_id': pid,
                'platform_name': names.get(pid, f'平台{pid}'),
                'has_fine': False,
            })
            continue
        out.append({
            'platform_id': pid,
            'platform_name': names.get(pid, f'平台{pid}'),
            'has_fine': True,
            'exec_round': int(rec.执行轮次),
            'tier': tier_labels.get(rec.罚款档次, rec.罚款档次),
            'supervision_cost': str(rec.监管成本数值),
        })
    return out


def build_page_context(round_num: Optional[int] = None) -> Dict[str, Any]:
    current = get_current_round()
    display_round = int(round_num if round_num is not None else current)
    return {
        'current_round': current,
        'display_round': display_round,
        'round_choices': list(range(1, current + 1)),
        'platform_names': platform_names_dict(),
        'users': {'platforms': _users_by_platform()},
        'governance': build_governance_payload(display_round)['governance'],
        'regulator': {
            'pending': _pending_counts(),
            'active_actions': _active_regulation_actions(display_round),
            'fines': _latest_fines_by_platform(display_round),
            'round_stats': _regulator_round_stats(display_round),
        },
        'measure_type_labels': MEASURE_TYPE_LABELS,
        'measure_type_colors': MEASURE_TYPE_COLORS,
        'platform_dot_colors': PLATFORM_DOT_COLORS,
    }
