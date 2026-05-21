# -*- coding: utf-8 -*-
"""账号 Excel 导入辅助：解析用户初始关注并校验同平台。"""
from __future__ import annotations

import ast
import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from accounts.models import UserAccount, UserFollowWriter, WriterAccount


def parse_follow_writer_accounts(cell) -> List[str]:
    """解析用户表「关注」列：如 \"['writer1', 'writer2']\" 或逗号分隔。"""
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    try:
        v = json.loads(s.replace("'", '"'))
    except (json.JSONDecodeError, TypeError, ValueError):
        try:
            v = ast.literal_eval(s)
        except (SyntaxError, ValueError):
            s2 = s.strip('[]').replace('，', ',')
            v = [p.strip().strip("'\"") for p in s2.split(',') if p.strip()]
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if not isinstance(v, (list, tuple)):
        return []
    out: List[str] = []
    seen = set()
    for item in v:
        acc = str(item).strip()
        if acc and acc not in seen:
            seen.add(acc)
            out.append(acc)
    return out


def validate_follow_same_platform(
    *,
    user_account: str,
    user_platform: int,
    writer_account: str,
    writer_platform_by_account: Dict[str, int],
) -> Optional[str]:
    """同平台校验；通过返回 None，失败返回错误说明。"""
    if writer_account not in writer_platform_by_account:
        return (
            f'用户「{user_account}」初始关注写手「{writer_account}」不存在，'
            f'请检查写手 Sheet 或关注列表'
        )
    writer_platform = writer_platform_by_account[writer_account]
    if writer_platform != user_platform:
        return (
            f'用户「{user_account}」所属平台为 {user_platform}，'
            f'不能关注平台 {writer_platform} 的写手「{writer_account}」'
        )
    return None


def apply_user_initial_follows(
    user: UserAccount,
    writer_accounts: Sequence[str],
    writer_platform_by_account: Dict[str, int],
    *,
    replace_existing: bool = True,
) -> int:
    """
    为用户写入初始关注；校验用户与写手同平台。
    返回新建关注条数。校验失败抛出 ValueError。
    """
    user_platform = int(getattr(user, '所属平台', 0) or 0)
    for writer_account in writer_accounts:
        err = validate_follow_same_platform(
            user_account=user.账号,
            user_platform=user_platform,
            writer_account=writer_account,
            writer_platform_by_account=writer_platform_by_account,
        )
        if err:
            raise ValueError(err)

    if replace_existing:
        UserFollowWriter.objects.filter(用户=user).delete()

    created = 0
    for writer_account in writer_accounts:
        _, was_created = UserFollowWriter.objects.get_or_create(
            用户=user,
            写手账号=writer_account,
        )
        if was_created:
            created += 1

    user.关注数 = UserFollowWriter.objects.filter(用户=user).count()
    user.save(update_fields=['关注数'])
    return created


def sync_follow_fan_counts(
    *,
    writer_accounts: Optional[Iterable[str]] = None,
    user_accounts: Optional[Iterable[str]] = None,
) -> None:
    """按关注关系回写写手粉丝数、用户关注数。"""
    if writer_accounts is not None:
        for account in writer_accounts:
            w = WriterAccount.objects.filter(账号=account).first()
            if not w:
                continue
            cnt = UserFollowWriter.objects.filter(写手账号=account).count()
            if w.粉丝数 != cnt:
                w.粉丝数 = cnt
                w.save(update_fields=['粉丝数'])
    else:
        for w in WriterAccount.objects.all():
            cnt = UserFollowWriter.objects.filter(写手账号=w.账号).count()
            if w.粉丝数 != cnt:
                w.粉丝数 = cnt
                w.save(update_fields=['粉丝数'])

    if user_accounts is not None:
        for account in user_accounts:
            u = UserAccount.objects.filter(账号=account).first()
            if not u:
                continue
            cnt = u.关注列表.count()
            if u.关注数 != cnt:
                u.关注数 = cnt
                u.save(update_fields=['关注数'])
    else:
        for u in UserAccount.objects.all():
            cnt = u.关注列表.count()
            if u.关注数 != cnt:
                u.关注数 = cnt
                u.save(update_fields=['关注数'])


def import_user_follows_from_sheet(
    ws,
    *,
    writer_platform_by_account: Optional[Dict[str, int]] = None,
) -> Tuple[int, int]:
    """
    从用户 Sheet 读取「关注」列并落库。
    返回 (处理用户数, 关注关系条数)。
    """
    if writer_platform_by_account is None:
        writer_platform_by_account = dict(
            WriterAccount.objects.values_list('账号', '所属平台')
        )

    header = [
        str(x).strip() if x is not None else ''
        for x in (next(ws.iter_rows(min_row=1, max_row=1, values_only=True)) or [])
    ]
    col_map = {name: idx for idx, name in enumerate(header) if name}
    idx_account = col_map.get('账号', 0)
    idx_follow = col_map.get('关注')
    if idx_follow is None:
        return 0, 0

    users_processed = 0
    follow_rows = 0
    touched_writers: set[str] = set()
    touched_users: List[str] = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        account = str(row[idx_account] or '').strip() if idx_account < len(row) else ''
        if not account:
            continue
        user = UserAccount.objects.filter(账号=account).first()
        if not user:
            raise ValueError(f'用户「{account}」未导入，无法写入初始关注')

        cell = row[idx_follow] if idx_follow < len(row) else None
        writers = parse_follow_writer_accounts(cell)
        apply_user_initial_follows(
            user,
            writers,
            writer_platform_by_account,
            replace_existing=True,
        )
        users_processed += 1
        follow_rows += len(writers)
        touched_users.append(account)
        touched_writers.update(writers)

    sync_follow_fan_counts(
        writer_accounts=touched_writers if touched_writers else None,
        user_accounts=touched_users if touched_users else None,
    )
    return users_processed, follow_rows
