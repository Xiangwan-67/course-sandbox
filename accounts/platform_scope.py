# -*- coding: utf-8 -*-
"""沙盘平台目录：与 settings.SANDBOX_PLATFORMS 一致，供 views / 导入 / Admin 校验共用。"""
from __future__ import annotations

from typing import Dict, List, Set

from django.conf import settings


def _raw_platforms():
    return getattr(
        settings,
        'SANDBOX_PLATFORMS',
        ((0, '平台1'), (1, '平台2')),
    )


def valid_platform_ids() -> Set[int]:
    return {int(t[0]) for t in _raw_platforms()}


def platform_names_dict() -> Dict[int, str]:
    return {int(k): str(v) for k, v in _raw_platforms()}


def platform_name(platform_id: int) -> str:
    d = platform_names_dict()
    pid = int(platform_id)
    if pid in d:
        return d[pid]
    return f'平台{pid + 1}'


def all_platform_choices() -> List[dict]:
    return [{'id': int(k), 'name': str(v)} for k, v in _raw_platforms()]


def normalize_platform_id(platform_id, default: int | None = None) -> int:
    """若不在合法集合内，则返回 default（默认取目录中最小编号）。"""
    ids = valid_platform_ids()
    try:
        pid = int(platform_id)
    except (TypeError, ValueError):
        pid = 0
    if pid in ids:
        return pid
    if default is not None and default in ids:
        return default
    return min(ids)


def default_platform_id() -> int:
    return min(valid_platform_ids())


def jurisdiction_for_regulator_account(account: str):
    """返回该监管账号的负责平台编号集合；未配置或账号不存在返回空集。"""
    from accounts.models import RegulatorAccount

    if not account:
        return frozenset()
    row = RegulatorAccount.objects.filter(账号=account).first()
    if not row:
        return frozenset()
    raw = getattr(row, '负责平台编号列表', None) or []
    ids = valid_platform_ids()
    out = set()
    for x in raw:
        try:
            xi = int(x)
        except (TypeError, ValueError):
            continue
        if xi in ids:
            out.add(xi)
    return frozenset(out)


def validate_regulator_platform_list(platform_ids: List[int], exclude_pk: int | None = None) -> str | None:
    """校验列表非空、互斥、均在合法目录。返回错误文案或 None。"""
    from accounts.models import RegulatorAccount

    ids = valid_platform_ids()
    cleaned = sorted({int(x) for x in platform_ids if int(x) in ids})
    if not cleaned:
        return '负责平台编号列表不能为空，且须均在系统平台目录内。'
    qs = RegulatorAccount.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    for other in qs:
        other_raw = getattr(other, '负责平台编号列表', None) or []
        other_set = set()
        for x in other_raw:
            try:
                other_set.add(int(x))
            except (TypeError, ValueError):
                continue
        if set(cleaned) & other_set:
            return f'与账号「{other.账号}」的负责平台冲突：{sorted(other_set & set(cleaned))}'
    return None
