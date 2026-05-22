# -*- coding: utf-8 -*-
"""每轮结束本轮后写入轮次快照（平台/写手/粉丝汇总）。"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Count, Sum

from accounts.clickbait_judge import (
    _thresholds_from_config,
    get_active_clickbait_config,
    judge_clickbait_by_config,
)
from accounts.models import (
    Article,
    ArticleRevenueSettlement,
    ArticleTraffic,
    PlatformCycleProfitRecord,
    RoundSnapshotBatch,
    RoundSnapshotPlatform,
    RoundSnapshotWriter,
    RoundSnapshotWriterFan,
    UserAccount,
    UserFollowWriter,
    WriterAccount,
)
from accounts.platform_scope import valid_platform_ids


def _decimal(v) -> Decimal:
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except Exception:
        return Decimal('0')


def _clickbait_counts_for_platform(
    platform_id: int,
    round_num: int,
    writer_accounts: List[str],
) -> Tuple[int, int, int, int, int]:
    """返回 article_field_true, by_rule, unjudged, threshold_x, threshold_y。"""
    cfg = get_active_clickbait_config(platform_id)
    x_th, y_th = _thresholds_from_config(cfg)

    articles = list(
        Article.objects.filter(写手账号__in=writer_accounts, 轮次=round_num).only(
            'id',
            'is_clickbait',
            '标题夸张度_校准值',
            '标题夸张度_初始值',
            '内容相关度_校准值',
            '内容相关度_初始值',
        )
    )
    article_field_true = 0
    by_rule = 0
    unjudged = 0
    for art in articles:
        if art.is_clickbait is None:
            unjudged += 1
        elif art.is_clickbait is True:
            article_field_true += 1
        if judge_clickbait_by_config(art, platform_id):
            by_rule += 1
    return article_field_true, by_rule, unjudged, x_th, y_th


def _cycle_profit_for_round(platform_id: int, round_num: int) -> Optional[PlatformCycleProfitRecord]:
    return (
        PlatformCycleProfitRecord.objects.filter(
            platform_id=platform_id,
            cycle_end_round=round_num,
        )
        .order_by('-id')
        .first()
    )


def _writer_revenue_aggregates(round_num: int) -> Dict[str, Dict[str, Decimal | int]]:
    """按写手账号聚合本轮收益结算。"""
    from django.db.models import Q

    qs = (
        ArticleRevenueSettlement.objects.filter(轮次=round_num)
        .values('写手账号')
        .annotate(
            round_revenue_total=Sum('最终收益'),
            round_revenue_raw=Sum('原始收益'),
            revenue_penalty_article_count=Count('id', filter=Q(penalty_applied=True)),
        )
    )
    out: Dict[str, Dict[str, Decimal | int]] = {}
    for row in qs:
        account = row['写手账号']
        raw = _decimal(row.get('round_revenue_raw') or 0)
        final = _decimal(row.get('round_revenue_total') or 0)
        penalty_count = int(row.get('revenue_penalty_article_count') or 0)
        deduction = Decimal('0')
        if penalty_count:
            for s in ArticleRevenueSettlement.objects.filter(
                轮次=round_num,
                写手账号=account,
                penalty_applied=True,
            ).only('原始收益', '最终收益'):
                deduction += _decimal(s.原始收益) - _decimal(s.最终收益)
        out[account] = {
            'round_revenue_total': final,
            'round_revenue_raw': raw,
            'revenue_penalty_deduction': deduction,
            'revenue_penalty_article_count': penalty_count,
        }
    return out


def _traffic_penalty_counts(round_num: int) -> Dict[str, int]:
    """写手账号 -> 本轮流量惩罚文章数（经文章关联写手）。"""
    rows = (
        ArticleTraffic.objects.filter(轮次=round_num, penalty_applied=True)
        .values('文章__写手账号')
        .annotate(cnt=Count('id'))
    )
    return {r['文章__写手账号']: int(r['cnt']) for r in rows if r.get('文章__写手账号')}


@transaction.atomic
def capture_round_snapshot(round_num: int, *, trigger: str = 'end_round') -> None:
    """
    写入 round_num 对应轮次的快照。同轮先删后写（幂等）。
    须在 _settle_article_revenue / 周期利润结算之后、SimulationRound+1 之前调用。
    """
    RoundSnapshotWriterFan.objects.filter(round_num=round_num).delete()
    RoundSnapshotWriter.objects.filter(round_num=round_num).delete()
    RoundSnapshotPlatform.objects.filter(round_num=round_num).delete()
    RoundSnapshotBatch.objects.filter(round_num=round_num).delete()

    RoundSnapshotBatch.objects.create(round_num=round_num, trigger=trigger)

    revenue_by_writer = _writer_revenue_aggregates(round_num)
    traffic_penalty_by_writer = _traffic_penalty_counts(round_num)

    platform_rows: List[RoundSnapshotPlatform] = []
    for pid in sorted(valid_platform_ids()):
        writer_accounts = list(
            WriterAccount.objects.filter(所属平台=pid).values_list('账号', flat=True)
        )
        user_count = UserAccount.objects.filter(所属平台=pid).count()
        cb_article, cb_rule, cb_unjudged, x_th, y_th = _clickbait_counts_for_platform(
            pid, round_num, writer_accounts
        )
        cycle_rec = _cycle_profit_for_round(pid, round_num)
        platform_rows.append(
            RoundSnapshotPlatform(
                round_num=round_num,
                platform_id=pid,
                user_count=user_count,
                clickbait_count_article_field=cb_article,
                clickbait_count_by_rule=cb_rule,
                clickbait_count_unjudged=cb_unjudged,
                rule_threshold_x=x_th,
                rule_threshold_y=y_th,
                cycle_profit_record=cycle_rec,
                cycle_index=cycle_rec.cycle_index if cycle_rec else None,
                cycle_profit_total=cycle_rec.profit_total if cycle_rec else None,
            )
        )
    RoundSnapshotPlatform.objects.bulk_create(platform_rows)

    writer_rows: List[RoundSnapshotWriter] = []
    for w in WriterAccount.objects.all().iterator():
        rev = revenue_by_writer.get(w.账号, {})
        writer_rows.append(
            RoundSnapshotWriter(
                round_num=round_num,
                writer_account=w.账号,
                platform_id=int(getattr(w, '所属平台', 0) or 0),
                fan_count=int(w.粉丝数 or 0),
                round_revenue_total=_decimal(rev.get('round_revenue_total', 0)),
                round_revenue_raw=_decimal(rev.get('round_revenue_raw', 0)),
                revenue_penalty_deduction=_decimal(rev.get('revenue_penalty_deduction', 0)),
                revenue_penalty_article_count=int(rev.get('revenue_penalty_article_count', 0)),
                traffic_penalty_article_count=traffic_penalty_by_writer.get(w.账号, 0),
                health_score=int(getattr(w, '健康分', 100) or 100),
                health_tier=str(getattr(w, 'health_tier', '') or ''),
                push_coefficient=_decimal(getattr(w, '推流系数', Decimal('1'))),
            )
        )
    RoundSnapshotWriter.objects.bulk_create(writer_rows)

    fan_rows: List[RoundSnapshotWriterFan] = []
    for rel in UserFollowWriter.objects.select_related('用户').iterator():
        fan_rows.append(
            RoundSnapshotWriterFan(
                round_num=round_num,
                writer_account=rel.写手账号,
                user_account=rel.用户.账号,
                user_platform_id=int(getattr(rel.用户, '所属平台', 0) or 0),
            )
        )
    if fan_rows:
        RoundSnapshotWriterFan.objects.bulk_create(fan_rows, batch_size=500)
