from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    AccountHealthConfig,
    AccountHealthLevelConfig,
    ArticleTraffic,
    PlatformGovernanceMeasure,
    SimulationRound,
    TrafficPenaltyConfig,
)
from accounts.views import _get_current_round


def _read_log(action_log_path) -> str:
    return action_log_path.read_text(encoding="utf-8", errors="replace")


def _publish_article(client, *, title_init: int, body_init: int, title_pos: int = 1, body_pos: int = 1) -> int:
    r = client.post("/writer/start-article/")
    assert r.status_code == 200
    article_id = int(r.json()["article_id"])

    r = client.post(
        "/writer/select-title/",
        {
            "title_text": f"title-{article_id}",
            "position": title_pos,
            "title_exaggeration_level": title_init,
        },
    )
    assert r.status_code == 200

    r = client.post(
        "/writer/select-body/",
        {
            "body_text": f"body-{article_id}",
            "position": body_pos,
            "content_relevance_level": body_init,
        },
    )
    assert r.status_code == 200
    return article_id


def _activate_traffic_penalty_measure(*, platform_id: int, round_num: int, alpha: str = "0.50"):
    cfg = TrafficPenaltyConfig.objects.create(
        platform_id=platform_id,
        降权系数alpha=Decimal(alpha),
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    measure = PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="traffic_penalty",
        措施内容={"降权系数alpha": str(cfg.降权系数alpha)},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )
    return cfg, measure


@pytest.mark.django_db
def test_traffic_penalty_config_page_and_save_success(client_platform_logged_in, action_log_path, platform_account):
    client, _ = client_platform_logged_in

    r = client.get("/platform/governance/traffic-penalty/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "流量惩罚配置" in html
    assert "提交配置（待管理员审核）" in html

    r = client.post("/platform/governance/traffic-penalty/save/", {"alpha": "0.30"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("config_id")

    cfg = TrafficPenaltyConfig.objects.filter(platform_id=platform_account.所属平台).order_by("-id").first()
    assert cfg is not None
    assert cfg.status == "pending"
    assert cfg.降权系数alpha == Decimal("0.30")
    assert cfg.提交人账号 == "pytest_platform_0"

    log_text = _read_log(action_log_path)
    assert "提交流量惩罚配置待审" in log_text
    assert "alpha=0.30" in log_text


@pytest.mark.django_db
def test_traffic_penalty_save_duplicate_rejected(client_platform_logged_in, platform_account, action_log_path):
    client, _ = client_platform_logged_in
    TrafficPenaltyConfig.objects.create(
        platform_id=platform_account.所属平台,
        降权系数alpha=Decimal("0.60"),
        status="pending",
        提交人账号="pytest_platform_0",
    )
    before = TrafficPenaltyConfig.objects.filter(platform_id=platform_account.所属平台).count()

    r = client.post("/platform/governance/traffic-penalty/save/", {"alpha": "0.20"})
    assert r.status_code == 400
    assert "不能再次修改" in (r.json().get("error") or "")

    after = TrafficPenaltyConfig.objects.filter(platform_id=platform_account.所属平台).count()
    assert after == before

    log_text = _read_log(action_log_path)
    assert "提交流量惩罚配置待审" not in log_text


@pytest.mark.django_db
def test_traffic_penalty_publish_requires_approved_config(client_platform_logged_in, platform_account, action_log_path):
    client, _ = client_platform_logged_in
    TrafficPenaltyConfig.objects.filter(platform_id=platform_account.所属平台).delete()

    r = client.post("/platform/governance/publish/", {"measure_type": "traffic_penalty"})
    assert r.status_code == 400
    assert "请先提交流量惩罚配置" in (r.json().get("error") or "")

    assert PlatformGovernanceMeasure.objects.filter(
        平台=platform_account.所属平台, 措施类型="traffic_penalty"
    ).count() == 0

    log_text = _read_log(action_log_path)
    assert "type=traffic_penalty" not in log_text


@pytest.mark.django_db
def test_traffic_penalty_publish_next_round_effective(
    client_platform_logged_in,
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
    action_log_path,
):
    from django.test import Client

    client, _ = client_platform_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})

    cfg = TrafficPenaltyConfig.objects.create(
        platform_id=platform_account.所属平台,
        降权系数alpha=Decimal("0.30"),
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )

    r = client.post("/platform/governance/publish/", {"measure_type": "traffic_penalty"})
    assert r.status_code == 200
    rec = (
        PlatformGovernanceMeasure.objects.filter(平台=platform_account.所属平台, 措施类型="traffic_penalty")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec is not None
    assert rec.status == "pending"
    assert rec.轮次 == 1
    assert rec.生效轮次 == 2
    assert rec.config_id == cfg.pk

    rec.status = "active"
    rec.管理员确认账号 = "admin"
    rec.save(update_fields=["status", "管理员确认账号"])

    c1 = Client()
    assert c1.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid1 = _publish_article(c1, title_init=5, body_init=1)
    t1 = ArticleTraffic.objects.filter(文章_id=aid1).order_by("-id").first()
    assert t1 is not None
    assert t1.penalty_applied is False
    assert t1.penalty_coefficient == Decimal("1.0000")

    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 2

    c2 = Client()
    assert c2.post("/", {"account": writer_accounts[1].账号, "password": writer_accounts[1].密码}).status_code in (200, 302)
    aid2 = _publish_article(c2, title_init=5, body_init=1)
    t2 = ArticleTraffic.objects.filter(文章_id=aid2).order_by("-id").first()
    assert t2 is not None
    assert t2.penalty_applied is True
    assert t2.penalty_coefficient == Decimal("0.3000")

    log_text = _read_log(action_log_path)
    assert "提交治理措施待审 type=traffic_penalty" in log_text
    assert "文章推送完成" in log_text
    assert "penalty_coeff=0.30" in log_text


@pytest.mark.django_db
def test_traffic_penalty_not_applied_for_non_clickbait(
    platform_account, enable_clickbait_measure, writer_accounts, action_log_path
):
    from django.test import Client

    current = _get_current_round()
    _activate_traffic_penalty_measure(platform_id=platform_account.所属平台, round_num=current, alpha="0.25")

    c = Client()
    assert c.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid = _publish_article(c, title_init=3, body_init=3)

    traffic = ArticleTraffic.objects.filter(文章_id=aid).order_by("-id").first()
    assert traffic is not None
    assert traffic.penalty_applied is False
    assert traffic.penalty_coefficient == Decimal("1.0000")

    log_text = _read_log(action_log_path)
    assert "文章推送完成" in log_text
    assert "penalty_coeff=1.0" in log_text or "penalty_coeff=1.00" in log_text


@pytest.mark.django_db
def test_traffic_penalty_cancel_next_round_disabled(
    client_platform_logged_in,
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
    action_log_path,
):
    from django.test import Client

    client, _ = client_platform_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})
    _cfg, _measure = _activate_traffic_penalty_measure(
        platform_id=platform_account.所属平台, round_num=1, alpha="0.40"
    )

    r = client.post("/platform/governance/cancel/", {"measure_type": "traffic_penalty"})
    assert r.status_code == 200
    cancel_round = r.json().get("cancel_round")
    assert cancel_round == 2

    c1 = Client()
    assert c1.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid1 = _publish_article(c1, title_init=5, body_init=1)
    t1 = ArticleTraffic.objects.filter(文章_id=aid1).order_by("-id").first()
    assert t1 is not None
    assert t1.penalty_applied is True
    assert t1.penalty_coefficient == Decimal("0.4000")

    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 2

    c2 = Client()
    assert c2.post("/", {"account": writer_accounts[1].账号, "password": writer_accounts[1].密码}).status_code in (200, 302)
    aid2 = _publish_article(c2, title_init=5, body_init=1)
    t2 = ArticleTraffic.objects.filter(文章_id=aid2).order_by("-id").first()
    assert t2 is not None
    assert t2.penalty_applied is False
    assert t2.penalty_coefficient == Decimal("1.0000")

    log_text = _read_log(action_log_path)
    assert "取消治理措施 type=traffic_penalty" in log_text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("alpha", "expected_penalty", "expected_final_traffic"),
    [
        ("0.00", Decimal("0.0000"), 0),
        ("1.00", Decimal("1.0000"), None),
    ],
)
def test_traffic_penalty_alpha_boundaries(
    alpha,
    expected_penalty,
    expected_final_traffic,
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
):
    from django.test import Client

    current = _get_current_round()
    _activate_traffic_penalty_measure(platform_id=platform_account.所属平台, round_num=current, alpha=alpha)

    c = Client()
    assert c.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid = _publish_article(c, title_init=5, body_init=1)

    traffic = ArticleTraffic.objects.filter(文章_id=aid).order_by("-id").first()
    assert traffic is not None
    assert traffic.penalty_applied is True
    assert traffic.penalty_coefficient == expected_penalty
    if expected_final_traffic is not None:
        assert traffic.最终流量 == expected_final_traffic
    else:
        assert traffic.最终流量 >= 1


@pytest.mark.django_db
def test_traffic_penalty_invalid_alpha_and_permission(client_platform_logged_in, action_log_path, platform_account):
    from django.test import Client

    client, _ = client_platform_logged_in
    r = client.post("/platform/governance/traffic-penalty/save/", {"alpha": "not-a-number"})
    assert r.status_code == 200
    cfg = TrafficPenaltyConfig.objects.filter(platform_id=platform_account.所属平台).order_by("-id").first()
    assert cfg is not None
    assert cfg.降权系数alpha == Decimal("0.50")

    anon = Client()
    r = anon.post("/platform/governance/traffic-penalty/save/", {"alpha": "0.20"})
    assert r.status_code == 403

    log_text = _read_log(action_log_path)
    assert "提交流量惩罚配置待审" in log_text
    assert "alpha=0.50" in log_text


@pytest.mark.django_db
def test_traffic_penalty_with_health_rule_records_gamma(
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
    action_log_path,
):
    from django.test import Client

    current = _get_current_round()
    _activate_traffic_penalty_measure(platform_id=platform_account.所属平台, round_num=current, alpha="0.50")

    health_cfg = AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=10,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    AccountHealthLevelConfig.objects.create(
        平台=platform_account.所属平台,
        config=health_cfg,
        档位标签="观察",
        生效轮次起=current,
        下界开=0,
        上界闭=100,
        可推流比例=Decimal("0.4000"),
        排序=1,
    )
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, current - 1),
        生效轮次=current,
        措施类型="account_health_rule",
        措施内容={},
        config_id=health_cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    c = Client()
    assert c.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid = _publish_article(c, title_init=5, body_init=1)

    traffic = ArticleTraffic.objects.filter(文章_id=aid).order_by("-id").first()
    assert traffic is not None
    assert traffic.penalty_applied is True
    assert traffic.penalty_coefficient == Decimal("0.5000")
    assert traffic.health_tier_coefficient == Decimal("0.4000")

    log_text = _read_log(action_log_path)
    assert "健康分扣减" in log_text
    assert "gamma=0.4000" in log_text


@pytest.mark.django_db
def test_traffic_penalty_round_result_matches_database(
    client_platform_logged_in,
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
):
    from django.test import Client

    current = _get_current_round()
    _activate_traffic_penalty_measure(platform_id=platform_account.所属平台, round_num=current, alpha="0.35")

    c1 = Client()
    assert c1.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    _publish_article(c1, title_init=5, body_init=1)

    c2 = Client()
    assert c2.post("/", {"account": writer_accounts[1].账号, "password": writer_accounts[1].密码}).status_code in (200, 302)
    _publish_article(c2, title_init=3, body_init=3)

    db_count = (
        ArticleTraffic.objects.filter(platform_id=platform_account.所属平台, 轮次=current, penalty_applied=True)
        .values("文章_id")
        .distinct()
        .count()
    )
    assert db_count == 1

    client, _ = client_platform_logged_in
    r = client.get(f"/platform/round-result/?round={current}")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert f"受到流量惩罚文章数：<strong>{db_count}</strong>" in html


@pytest.mark.django_db
def test_traffic_penalty_push_log_contains_required_fields(
    platform_account,
    enable_clickbait_measure,
    writer_accounts,
    action_log_path,
):
    from django.test import Client

    current = _get_current_round()
    _activate_traffic_penalty_measure(platform_id=platform_account.所属平台, round_num=current, alpha="0.35")

    c = Client()
    assert c.post("/", {"account": writer_accounts[0].账号, "password": writer_accounts[0].密码}).status_code in (200, 302)
    aid = _publish_article(c, title_init=5, body_init=1)

    traffic = ArticleTraffic.objects.filter(文章_id=aid).order_by("-id").first()
    assert traffic is not None
    assert traffic.penalty_applied is True

    log_text = _read_log(action_log_path)
    assert f"article_id={aid}" in log_text
    assert "文章推送完成" in log_text
    assert "push_coef=" in log_text
    assert "penalty_coeff=0.35" in log_text
    assert "final_ratio=" in log_text
    assert "discover_chosen=" in log_text
    assert "total_pushed=" in log_text
