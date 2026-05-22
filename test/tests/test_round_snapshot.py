from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.clickbait_judge import judge_clickbait_by_config
from accounts.models import (
    Article,
    ArticleRevenueSettlement,
    RoundSnapshotBatch,
    RoundSnapshotPlatform,
    RoundSnapshotWriter,
    RoundSnapshotWriterFan,
    SimulationRound,
    UserFollowWriter,
    UserAccount,
    WriterAccount,
)
from accounts.platform_scope import valid_platform_ids
from accounts.views import _get_current_round


def _create_article(*, writer_account: str, round_num: int, clicks: int = 0, is_clickbait=None) -> Article:
    return Article.objects.create(
        写手账号=writer_account,
        轮次=round_num,
        标题="snap_title",
        标题夸张度_校准值=5,
        内容相关度_校准值=1,
        正文="snap_body",
        点击量=clicks,
        is_clickbait=is_clickbait,
    )


@pytest.mark.django_db
def test_end_round_creates_round_snapshot(
    client_platform_logged_in,
    platform_account,
    writer_accounts,
):
    client, _platform = client_platform_logged_in
    current_round = _get_current_round()
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": current_round})

    writer = writer_accounts[0]
    user = UserAccount.objects.filter(所属平台=writer.所属平台).first()
    assert user is not None
    UserFollowWriter.objects.get_or_create(用户=user, 写手账号=writer.账号)
    writer.粉丝数 = 1
    writer.save(update_fields=["粉丝数"])

    article = _create_article(
        writer_account=writer.账号,
        round_num=current_round,
        clicks=3,
        is_clickbait=True,
    )
    assert judge_clickbait_by_config(article, writer.所属平台) is True

    r = client.post("/end-round/")
    assert r.status_code == 200

    batch = RoundSnapshotBatch.objects.filter(round_num=current_round).first()
    assert batch is not None
    assert batch.trigger == "end_round"

    platform_ids = valid_platform_ids()
    assert RoundSnapshotPlatform.objects.filter(round_num=current_round).count() == len(platform_ids)

    plat_row = RoundSnapshotPlatform.objects.get(round_num=current_round, platform_id=writer.所属平台)
    assert plat_row.user_count == UserAccount.objects.filter(所属平台=writer.所属平台).count()
    assert plat_row.clickbait_count_article_field >= 1
    assert plat_row.clickbait_count_by_rule >= 1

    writer_row = RoundSnapshotWriter.objects.get(round_num=current_round, writer_account=writer.账号)
    assert writer_row.fan_count == 1
    settlement = ArticleRevenueSettlement.objects.get(文章=article, 轮次=current_round)
    assert writer_row.round_revenue_total == settlement.最终收益
    assert writer_row.round_revenue_raw == settlement.原始收益

    fan = RoundSnapshotWriterFan.objects.filter(
        round_num=current_round,
        writer_account=writer.账号,
        user_account=user.账号,
    ).first()
    assert fan is not None
    assert fan.user_platform_id == user.所属平台

    assert RoundSnapshotWriter.objects.filter(round_num=current_round).count() == WriterAccount.objects.count()


@pytest.mark.django_db
def test_capture_round_snapshot_is_idempotent(writer_accounts):
    from accounts.round_snapshot import capture_round_snapshot

    round_num = 3
    RoundSnapshotBatch.objects.create(round_num=round_num, trigger="manual")
    RoundSnapshotPlatform.objects.create(
        round_num=round_num,
        platform_id=0,
        user_count=999,
    )

    capture_round_snapshot(round_num, trigger="end_round")

    assert RoundSnapshotBatch.objects.filter(round_num=round_num).count() == 1
    assert RoundSnapshotBatch.objects.get(round_num=round_num).trigger == "end_round"
    plat = RoundSnapshotPlatform.objects.get(round_num=round_num, platform_id=0)
    assert plat.user_count != 999
