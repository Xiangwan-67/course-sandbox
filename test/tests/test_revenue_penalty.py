from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    Article,
    ArticleRevenueSettlement,
    PlatformGovernanceMeasure,
    RevenuePenaltyConfig,
    SimulationRound,
)
from accounts.views import _get_current_round


def _read_log(action_log_path) -> str:
    return action_log_path.read_text(encoding="utf-8", errors="replace")


def _create_article(*, writer_account: str, round_num: int, clicks: int, is_clickbait: bool) -> Article:
    return Article.objects.create(
        写手账号=writer_account,
        轮次=round_num,
        标题="pytest_revenue_title",
        正文="pytest_revenue_body",
        点击量=clicks,
        is_clickbait=is_clickbait,
        is_published=True,
    )


def _activate_revenue_penalty_measure(*, platform_id: int, round_num: int, beta: str = "0.50"):
    cfg = RevenuePenaltyConfig.objects.create(
        platform_id=platform_id,
        惩罚系数beta=Decimal(beta),
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    measure = PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="revenue_penalty",
        措施内容={"惩罚系数beta": str(cfg.惩罚系数beta)},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )
    return cfg, measure


@pytest.mark.django_db
def test_revenue_penalty_config_page_and_save_success(client_platform_logged_in, platform_account, action_log_path):
    client, _ = client_platform_logged_in

    r = client.get("/platform/governance/revenue-penalty/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "收益惩罚配置" in html
    assert "提交配置（待管理员审核）" in html

    r = client.post("/platform/governance/revenue-penalty/save/", {"beta": "0.40"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("config_id")

    cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_account.所属平台).order_by("-id").first()
    assert cfg is not None
    assert cfg.status == "pending"
    assert cfg.惩罚系数beta == Decimal("0.40")
    assert cfg.提交人账号 == "pytest_platform_0"

    log_text = _read_log(action_log_path)
    assert "提交收益惩罚配置待审" in log_text
    assert "beta=0.40" in log_text


@pytest.mark.django_db
def test_revenue_penalty_save_duplicate_rejected(client_platform_logged_in, platform_account, action_log_path):
    client, _ = client_platform_logged_in
    RevenuePenaltyConfig.objects.create(
        platform_id=platform_account.所属平台,
        惩罚系数beta=Decimal("0.60"),
        status="pending",
        提交人账号="pytest_platform_0",
    )
    before = RevenuePenaltyConfig.objects.filter(platform_id=platform_account.所属平台).count()

    r = client.post("/platform/governance/revenue-penalty/save/", {"beta": "0.20"})
    assert r.status_code == 400
    assert "不能再次修改" in (r.json().get("error") or "")

    after = RevenuePenaltyConfig.objects.filter(platform_id=platform_account.所属平台).count()
    assert after == before

    log_text = _read_log(action_log_path)
    assert "提交收益惩罚配置待审" not in log_text


@pytest.mark.django_db
def test_revenue_penalty_publish_requires_approved_config(client_platform_logged_in, platform_account, action_log_path):
    client, _ = client_platform_logged_in
    RevenuePenaltyConfig.objects.filter(platform_id=platform_account.所属平台).delete()

    r = client.post("/platform/governance/publish/", {"measure_type": "revenue_penalty"})
    assert r.status_code == 400
    assert "请先提交收益惩罚配置" in (r.json().get("error") or "")

    assert PlatformGovernanceMeasure.objects.filter(
        平台=platform_account.所属平台, 措施类型="revenue_penalty"
    ).count() == 0

    log_text = _read_log(action_log_path)
    assert "type=revenue_penalty" not in log_text


@pytest.mark.django_db
def test_revenue_penalty_publish_next_round_effective(client_platform_logged_in, platform_account, writer_accounts, action_log_path):
    client, _ = client_platform_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})

    cfg = RevenuePenaltyConfig.objects.create(
        platform_id=platform_account.所属平台,
        惩罚系数beta=Decimal("0.50"),
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    r = client.post("/platform/governance/publish/", {"measure_type": "revenue_penalty"})
    assert r.status_code == 200

    rec = (
        PlatformGovernanceMeasure.objects.filter(平台=platform_account.所属平台, 措施类型="revenue_penalty")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec is not None
    assert rec.status == "pending"
    assert rec.生效轮次 == 2
    assert rec.config_id == cfg.pk

    rec.status = "active"
    rec.管理员确认账号 = "admin"
    rec.save(update_fields=["status", "管理员确认账号"])

    art1 = _create_article(writer_account=writer_accounts[0].账号, round_num=1, clicks=10, is_clickbait=True)
    r = client.post("/end-round/")
    assert r.status_code == 200
    s1 = ArticleRevenueSettlement.objects.filter(文章=art1, 轮次=1).order_by("-id").first()
    assert s1 is not None
    assert s1.penalty_applied is False
    assert s1.penalty_coefficient == Decimal("1.0000")

    art2 = _create_article(writer_account=writer_accounts[1].账号, round_num=2, clicks=10, is_clickbait=True)
    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 3

    s2 = ArticleRevenueSettlement.objects.filter(文章=art2, 轮次=2).order_by("-id").first()
    assert s2 is not None
    assert s2.penalty_applied is True
    assert s2.penalty_coefficient == Decimal("0.5000")

    log_text = _read_log(action_log_path)
    assert "提交治理措施待审 type=revenue_penalty" in log_text
    assert "文章收益结算" in log_text
    assert "beta=0.50" in log_text or "beta=0.5" in log_text


@pytest.mark.django_db
def test_revenue_penalty_not_applied_for_non_clickbait(platform_account, writer_accounts, action_log_path):
    current = _get_current_round()
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=current, beta="0.30")
    art = _create_article(writer_account=writer_accounts[0].账号, round_num=current, clicks=10, is_clickbait=False)

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    s = ArticleRevenueSettlement.objects.filter(文章=art, 轮次=current).order_by("-id").first()
    assert s is not None
    assert s.penalty_applied is False
    assert s.penalty_coefficient == Decimal("1.0000")

    log_text = _read_log(action_log_path)
    assert "文章收益结算" in log_text
    assert "penalty=0" in log_text


@pytest.mark.django_db
def test_revenue_penalty_cancel_next_round_disabled(client_platform_logged_in, platform_account, writer_accounts, action_log_path):
    client, _ = client_platform_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=1, beta="0.40")

    r = client.post("/platform/governance/cancel/", {"measure_type": "revenue_penalty"})
    assert r.status_code == 200
    assert r.json().get("cancel_round") == 2

    art1 = _create_article(writer_account=writer_accounts[0].账号, round_num=1, clicks=10, is_clickbait=True)
    r = client.post("/end-round/")
    assert r.status_code == 200
    s1 = ArticleRevenueSettlement.objects.filter(文章=art1, 轮次=1).order_by("-id").first()
    assert s1 is not None
    assert s1.penalty_applied is True
    assert s1.penalty_coefficient == Decimal("0.4000")

    art2 = _create_article(writer_account=writer_accounts[1].账号, round_num=2, clicks=10, is_clickbait=True)
    r = client.post("/end-round/")
    assert r.status_code == 200
    s2 = ArticleRevenueSettlement.objects.filter(文章=art2, 轮次=2).order_by("-id").first()
    assert s2 is not None
    assert s2.penalty_applied is False
    assert s2.penalty_coefficient == Decimal("1.0000")

    log_text = _read_log(action_log_path)
    assert "取消治理措施 type=revenue_penalty" in log_text


@pytest.mark.django_db
def test_revenue_penalty_beta_zero_boundary(platform_account, writer_accounts):
    current = _get_current_round()
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=current, beta="0.00")
    art = _create_article(writer_account=writer_accounts[0].账号, round_num=current, clicks=10, is_clickbait=True)

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    s = ArticleRevenueSettlement.objects.filter(文章=art, 轮次=current).order_by("-id").first()
    assert s is not None
    assert s.penalty_applied is True
    assert s.penalty_coefficient == Decimal("0.0000")
    assert s.最终收益 == Decimal("0")


@pytest.mark.django_db
def test_revenue_penalty_beta_one_boundary(platform_account, writer_accounts):
    current = _get_current_round()
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=current, beta="1.00")
    art = _create_article(writer_account=writer_accounts[0].账号, round_num=current, clicks=10, is_clickbait=True)

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    s = ArticleRevenueSettlement.objects.filter(文章=art, 轮次=current).order_by("-id").first()
    assert s is not None
    assert s.penalty_applied is True
    assert s.penalty_coefficient == Decimal("1.0000")
    assert s.最终收益 == s.原始收益


@pytest.mark.django_db
def test_revenue_penalty_invalid_beta_and_permission(client_platform_logged_in, platform_account, action_log_path):
    from django.test import Client

    client, _ = client_platform_logged_in
    r = client.post("/platform/governance/revenue-penalty/save/", {"beta": "invalid-beta"})
    assert r.status_code == 200
    cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_account.所属平台).order_by("-id").first()
    assert cfg is not None
    assert cfg.惩罚系数beta == Decimal("0.50")

    anon = Client()
    r = anon.post("/platform/governance/revenue-penalty/save/", {"beta": "0.20"})
    assert r.status_code == 403

    log_text = _read_log(action_log_path)
    assert "提交收益惩罚配置待审" in log_text
    assert "beta=0.50" in log_text


@pytest.mark.django_db
def test_revenue_penalty_round_result_matches_database(client_platform_logged_in, platform_account, writer_accounts):
    current = _get_current_round()
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=current, beta="0.30")
    _create_article(writer_account=writer_accounts[0].账号, round_num=current, clicks=10, is_clickbait=True)
    _create_article(writer_account=writer_accounts[1].账号, round_num=current, clicks=10, is_clickbait=False)

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    db_count = (
        ArticleRevenueSettlement.objects.filter(platform_id=platform_account.所属平台, 轮次=current, penalty_applied=True)
        .values("文章_id")
        .distinct()
        .count()
    )
    assert db_count == 1

    client, _ = client_platform_logged_in
    r = client.get(f"/platform/round-result/?round={current}")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert f"受到收益惩罚文章数：<strong>{db_count}</strong>" in html


@pytest.mark.django_db
def test_revenue_penalty_settlement_log_contains_required_fields(
    platform_account, writer_accounts, action_log_path
):
    current = _get_current_round()
    _activate_revenue_penalty_measure(platform_id=platform_account.所属平台, round_num=current, beta="0.35")
    art = _create_article(writer_account=writer_accounts[0].账号, round_num=current, clicks=12, is_clickbait=True)

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    s = ArticleRevenueSettlement.objects.filter(文章=art, 轮次=current).order_by("-id").first()
    assert s is not None
    assert s.penalty_applied is True
    assert s.penalty_coefficient == Decimal("0.3500")

    log_text = _read_log(action_log_path)
    assert f"article_id={art.pk}" in log_text
    assert "文章收益结算" in log_text
    assert "raw=" in log_text
    assert "is_clickbait=True" in log_text
    assert "penalty=1" in log_text
    assert "beta=0.35" in log_text
    assert "final=" in log_text
