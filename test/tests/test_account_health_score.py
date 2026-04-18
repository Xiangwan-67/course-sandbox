from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    AccountHealthConfig,
    AccountHealthLevelConfig,
    PlatformGovernanceMeasure,
    WriterAccount,
    WriterHealthScoreLog,
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


def _activate_clickbait_measure(platform_id: int, round_num: int):
    from accounts.models import ClickbaitDetectionConfig

    cfg = ClickbaitDetectionConfig.objects.create(
        platform_id=platform_id,
        标题夸张度阈值X=4,
        内容相关度阈值Y=3,
        status="active",
        提交人账号="admin",
        管理员确认账号="admin",
    )
    PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="clickbait_detection",
        措施内容={"标题夸张度阈值X": 4, "内容相关度阈值Y": 3},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )
    return cfg


def _create_global_default_levels(round_num: int):
    AccountHealthLevelConfig.objects.create(
        平台=None,
        config=None,
        档位标签="正常",
        生效轮次起=round_num,
        下界开=80,
        上界闭=100,
        可推流比例=Decimal("1.0000"),
        排序=1,
    )
    AccountHealthLevelConfig.objects.create(
        平台=None,
        config=None,
        档位标签="观察",
        生效轮次起=round_num,
        下界开=0,
        上界闭=80,
        可推流比例=Decimal("0.6000"),
        排序=2,
    )


@pytest.mark.django_db
def test_health_levels_render_from_global_default_table(client_platform_logged_in, platform_account):
    current = _get_current_round()
    AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=30,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    _create_global_default_levels(current)

    client, _ = client_platform_logged_in
    r = client.get("/platform/governance/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "档位配置" in html
    assert "正常" in html
    assert "观察" in html
    assert "1.0000" in html
    assert "0.6000" in html


@pytest.mark.django_db
def test_account_health_publish_requires_submitted_config(client_platform_logged_in, platform_account):
    client, _ = client_platform_logged_in
    AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=10,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="draft",
        提交人账号="pytest_platform_0",
    )

    r = client.post("/platform/governance/publish/", {"measure_type": "account_health_rule"})
    assert r.status_code == 400
    assert "请先提交账号健康分配置" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_account_health_publish_next_round_effective_and_deducts(
    client_platform_logged_in,
    writer_accounts,
    platform_account,
    action_log_path,
):
    from django.test import Client

    current = _get_current_round()
    _activate_clickbait_measure(platform_account.所属平台, current)
    cfg = AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=30,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    _create_global_default_levels(current)

    client, _ = client_platform_logged_in
    r = client.post("/platform/governance/publish/", {"measure_type": "account_health_rule"})
    assert r.status_code == 200
    rec = (
        PlatformGovernanceMeasure.objects.filter(平台=platform_account.所属平台, 措施类型="account_health_rule")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec is not None
    assert rec.status == "pending"
    assert rec.config_id == cfg.pk
    assert rec.生效轮次 == current + 1
    rec.status = "active"
    rec.管理员确认账号 = "admin"
    rec.save(update_fields=["status", "管理员确认账号"])

    writer = writer_accounts[0]
    writer_client = Client()
    assert writer_client.post("/", {"account": writer.账号, "password": writer.密码}).status_code in (200, 302)
    _publish_article(writer_client, title_init=5, body_init=1)
    writer_obj = WriterAccount.objects.get(账号=writer.账号)
    assert writer_obj.健康分 == 100

    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == current + 1

    wc = Client()
    assert wc.post("/", {"account": writer.账号, "password": writer.密码}).status_code in (200, 302)
    _publish_article(wc, title_init=5, body_init=1)

    writer_obj.refresh_from_db()
    assert writer_obj.健康分 == 70
    assert writer_obj.health_tier == "观察"
    assert writer_obj.推流系数 == Decimal("0.6000")

    violation = WriterHealthScoreLog.objects.filter(写手账号=writer.账号, event_type="violation", 轮次=current + 1).first()
    assert violation is not None
    assert violation.变更值 == -30

    log_text = _read_log(action_log_path)
    assert "健康分扣减" in log_text
    assert "gamma=0.6000" in log_text


@pytest.mark.django_db
def test_non_clickbait_does_not_change_health_score(
    client_writer_logged_in,
    platform_account,
):
    current = _get_current_round()
    _activate_clickbait_measure(platform_account.所属平台, current)
    cfg = AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=20,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    _create_global_default_levels(current)
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, current - 1),
        生效轮次=current,
        措施类型="account_health_rule",
        措施内容={},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    writer_client, writer = client_writer_logged_in
    _publish_article(writer_client, title_init=3, body_init=3)
    writer.refresh_from_db()
    assert writer.健康分 == 100
    assert WriterHealthScoreLog.objects.filter(写手账号=writer.账号, event_type="violation").count() == 0


@pytest.mark.django_db
def test_account_health_cancel_next_round_disabled(
    client_platform_logged_in,
    writer_accounts,
    platform_account,
):
    from django.test import Client

    current = _get_current_round()
    _activate_clickbait_measure(platform_account.所属平台, current)
    cfg = AccountHealthConfig.objects.create(
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
    _create_global_default_levels(current)
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, current - 1),
        生效轮次=current,
        措施类型="account_health_rule",
        措施内容={},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    client, _ = client_platform_logged_in
    r = client.post("/platform/governance/cancel/", {"measure_type": "account_health_rule"})
    assert r.status_code == 200
    assert r.json().get("cancel_round") == current + 1

    writer = writer_accounts[0]
    writer_client = Client()
    assert writer_client.post("/", {"account": writer.账号, "password": writer.密码}).status_code in (200, 302)
    _publish_article(writer_client, title_init=5, body_init=1)
    writer_obj = WriterAccount.objects.get(账号=writer.账号)
    assert writer_obj.健康分 == 90

    r = client.post("/end-round/")
    assert r.status_code == 200

    wc = Client()
    assert wc.post("/", {"account": writer.账号, "password": writer.密码}).status_code in (200, 302)
    _publish_article(wc, title_init=5, body_init=1)
    writer_obj.refresh_from_db()
    assert writer_obj.健康分 == 90


@pytest.mark.django_db
def test_health_recovery_updates_score_and_log(platform_account, writer_accounts, action_log_path, client):
    current = _get_current_round()
    cfg = AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=10,
        是否启用恢复机制=True,
        恢复所需连续无违规轮次=1,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    AccountHealthLevelConfig.objects.create(
        平台=None,
        config=None,
        档位标签="恢复后档位",
        生效轮次起=current,
        下界开=60,
        上界闭=100,
        可推流比例=Decimal("0.9000"),
        排序=1,
    )
    AccountHealthLevelConfig.objects.create(
        平台=None,
        config=None,
        档位标签="恢复前档位",
        生效轮次起=current,
        下界开=0,
        上界闭=60,
        可推流比例=Decimal("0.5000"),
        排序=2,
    )
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, current - 1),
        生效轮次=current,
        措施类型="account_health_rule",
        措施内容={},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    writer = WriterAccount.objects.get(账号=writer_accounts[0].账号)
    writer.健康分 = 60
    writer.health_tier = "恢复前档位"
    writer.推流系数 = Decimal("0.5000")
    writer.save(update_fields=["健康分", "health_tier", "推流系数"])

    r = client.post("/end-round/")
    assert r.status_code == 200

    writer.refresh_from_db()
    assert writer.健康分 == 65
    assert writer.health_tier == "恢复后档位"
    assert writer.推流系数 == Decimal("0.9000")
    assert WriterHealthScoreLog.objects.filter(写手账号=writer.账号, event_type="recovery").exists()

    log_text = _read_log(action_log_path)
    assert "健康分恢复" in log_text


@pytest.mark.django_db
def test_health_recovery_not_run_when_measure_not_effective(platform_account, writer_accounts, client):
    current = _get_current_round()
    AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=10,
        是否启用恢复机制=True,
        恢复所需连续无违规轮次=1,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    # 故意不创建 account_health_rule 生效措施，验证“未生效不恢复”。
    writer = WriterAccount.objects.get(账号=writer_accounts[0].账号)
    writer.健康分 = 60
    writer.health_tier = "恢复前档位"
    writer.推流系数 = Decimal("0.5000")
    writer.save(update_fields=["健康分", "health_tier", "推流系数"])

    r = client.post("/end-round/")
    assert r.status_code == 200

    writer.refresh_from_db()
    assert writer.健康分 == 60
    assert writer.health_tier == "恢复前档位"
    assert writer.推流系数 == Decimal("0.5000")
    assert not WriterHealthScoreLog.objects.filter(写手账号=writer.账号, event_type="recovery", 轮次=current).exists()


@pytest.mark.django_db
def test_health_deduction_floor_at_zero(client_writer_logged_in, platform_account):
    current = _get_current_round()
    _activate_clickbait_measure(platform_account.所属平台, current)
    cfg = AccountHealthConfig.objects.create(
        platform_id=platform_account.所属平台,
        初始健康分=100,
        每次违规扣减分值=200,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="pytest_platform_0",
        管理员确认账号="admin",
    )
    _create_global_default_levels(current)
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, current - 1),
        生效轮次=current,
        措施类型="account_health_rule",
        措施内容={},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    writer_client, writer = client_writer_logged_in
    writer.健康分 = 50
    writer.save(update_fields=["健康分"])

    _publish_article(writer_client, title_init=5, body_init=1)
    writer.refresh_from_db()
    assert writer.健康分 == 0


@pytest.mark.django_db
def test_account_health_publish_permission_denied(platform_account):
    from django.test import Client

    AccountHealthConfig.objects.create(
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
    c = Client()
    r = c.post("/platform/governance/publish/", {"measure_type": "account_health_rule"})
    assert r.status_code == 403
