from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    Article,
    ArticleRevenueSettlement,
    PlatformPerformanceScheme,
    SimulationRound,
    UserAccount,
    UserArticleCollect,
    UserArticleReadComplete,
)
from accounts.views import _get_current_round


def _create_article(*, writer_account: str, round_num: int, clicks: int = 0, is_clickbait=None) -> Article:
    return Article.objects.create(
        写手账号=writer_account,
        轮次=round_num,
        标题="pytest_title",
        正文="pytest_body",
        点击量=clicks,
        is_clickbait=is_clickbait,
    )


@pytest.mark.django_db
def test_platform_performance_page_renders_sections(client_platform_logged_in):
    client, _platform = client_platform_logged_in

    r = client.get("/platform/performance/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "当前生效方案" in html
    assert "提交新方案" in html
    assert "w1 — 点击量权重" in html
    assert "w4 — 满意度权重" in html


@pytest.mark.django_db
def test_platform_performance_submit_creates_pending_record_and_log(client_platform_logged_in, action_log_path):
    client, platform_account = client_platform_logged_in
    current_round = _get_current_round()

    r = client.post(
        "/platform/performance/submit/",
        {"w1": "0.40", "w2": "0.30", "w3": "0.20", "w4": "0.10"},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True

    rec = PlatformPerformanceScheme.objects.order_by("-id").first()
    assert rec is not None
    assert rec.平台 == platform_account.所属平台
    assert rec.status == "pending"
    assert rec.生效轮次 == current_round + 1
    assert rec.w1_click == Decimal("0.40")
    assert rec.w2_finish == Decimal("0.30")
    assert rec.w3_collect == Decimal("0.20")
    assert rec.w4_satisfaction == Decimal("0.10")

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert "提交绩效方案" in log_text
    assert f"scheme_id={rec.pk}" in log_text
    assert "status=pending" in log_text


@pytest.mark.django_db
def test_platform_performance_submit_requires_platform_role(client_user_logged_in):
    client, _user = client_user_logged_in

    r = client.post(
        "/platform/performance/submit/",
        {"w1": "0.25", "w2": "0.25", "w3": "0.25", "w4": "0.25"},
    )
    assert r.status_code == 403
    assert "未登录或非平台角色" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_performance_submit_invalid_decimal_returns_400(client_platform_logged_in):
    client, _platform = client_platform_logged_in

    r = client.post(
        "/platform/performance/submit/",
        {"w1": "abc", "w2": "0.25", "w3": "0.25", "w4": "0.25"},
    )
    assert r.status_code == 400
    assert "权重参数格式错误" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_performance_submit_total_not_positive_returns_400(client_platform_logged_in):
    client, _platform = client_platform_logged_in

    r = client.post(
        "/platform/performance/submit/",
        {"w1": "0", "w2": "0", "w3": "0", "w4": "0"},
    )
    assert r.status_code == 400
    assert "权重之和必须大于 0" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_performance_apply_deprecated_returns_410(client_platform_logged_in):
    client, _platform = client_platform_logged_in

    r = client.post("/platform/performance/apply/", {"scheme_code": "S1_balanced"})
    assert r.status_code == 410
    assert "接口已废弃" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_performance_page_shows_active_and_pending_scheme(client_platform_logged_in, platform_account):
    client, _platform = client_platform_logged_in
    current_round = _get_current_round()

    active = PlatformPerformanceScheme.objects.create(
        平台=platform_account.所属平台,
        生效轮次=current_round,
        方案编号="S1_balanced",
        方案内容={"w1": "0.3", "w2": "0.3", "w3": "0.2", "w4": "0.2"},
        发布人账号=platform_account.账号,
        w1_click=Decimal("0.30"),
        w2_finish=Decimal("0.30"),
        w3_collect=Decimal("0.20"),
        w4_satisfaction=Decimal("0.20"),
        status="active",
        管理员确认账号="admin",
    )
    pending = PlatformPerformanceScheme.objects.create(
        平台=platform_account.所属平台,
        生效轮次=current_round + 1,
        方案编号="S1_balanced",
        方案内容={"w1": "0.4", "w2": "0.2", "w3": "0.2", "w4": "0.2"},
        发布人账号=platform_account.账号,
        w1_click=Decimal("0.40"),
        w2_finish=Decimal("0.20"),
        w3_collect=Decimal("0.20"),
        w4_satisfaction=Decimal("0.20"),
        status="pending",
    )

    r = client.get("/platform/performance/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "待审核方案" in html
    assert f"方案 ID：{active.pk}" in html
    assert f"方案 ID：{pending.pk}" in html


@pytest.mark.django_db
def test_end_round_uses_active_performance_weights_and_records_settlement(
    client_platform_logged_in,
    platform_account,
    writer_accounts,
    action_log_path,
):
    client, _platform = client_platform_logged_in
    current_round = _get_current_round()
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": current_round})

    PlatformPerformanceScheme.objects.create(
        平台=platform_account.所属平台,
        生效轮次=current_round,
        方案编号="S1_balanced",
        方案内容={"w1": "2", "w2": "3", "w3": "5", "w4": "0"},
        发布人账号=platform_account.账号,
        w1_click=Decimal("2.00"),
        w2_finish=Decimal("3.00"),
        w3_collect=Decimal("5.00"),
        w4_satisfaction=Decimal("0.00"),
        status="active",
        管理员确认账号="admin",
    )

    article = _create_article(
        writer_account=writer_accounts[0].账号,
        round_num=current_round,
        clicks=4,
        is_clickbait=False,
    )
    users = list(UserAccount.objects.filter(所属平台=platform_account.所属平台).order_by("id")[:2])
    UserArticleReadComplete.objects.create(用户=users[0], 文章=article)
    UserArticleReadComplete.objects.create(用户=users[1], 文章=article)
    UserArticleCollect.objects.create(用户=users[0], 文章=article)

    r = client.post("/end-round/")
    assert r.status_code == 200

    settlement = ArticleRevenueSettlement.objects.filter(文章=article, 轮次=current_round).first()
    assert settlement is not None
    assert settlement.w1 == Decimal("2.0000")
    assert settlement.w2 == Decimal("3.0000")
    assert settlement.w3 == Decimal("5.0000")
    assert settlement.w4 == Decimal("0.0000")
    assert settlement.原始收益 == Decimal("19")
    assert settlement.penalty_applied is False
    assert settlement.最终收益 == Decimal("19")

    article.refresh_from_db()
    assert article.报酬 == 19

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert f"文章收益结算 article_id={article.pk}" in log_text
    assert "w1=2.00 w2=3.00 w3=5.00 w4=0" in log_text
