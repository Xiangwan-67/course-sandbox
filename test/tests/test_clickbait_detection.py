from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from accounts.models import Article, ClickbaitDetectionResult, PlatformGovernanceMeasure, SimulationRound
from accounts.views import _get_current_round


def _publish_and_detect(client, *, title_pos: int, body_pos: int, title_init: int, body_init: int) -> int:
    r = client.post("/writer/start-article/")
    assert r.status_code == 200
    article_id = r.json()["article_id"]

    r = client.post(
        "/writer/select-title/",
        {"title_text": "t", "position": title_pos, "title_exaggeration_level": title_init},
    )
    assert r.status_code == 200
    r = client.post(
        "/writer/select-body/",
        {"body_text": "b", "position": body_pos, "content_relevance_level": body_init},
    )
    assert r.status_code == 200
    return int(article_id)


def _read_log(action_log_path: Path) -> str:
    return action_log_path.read_text(encoding="utf-8", errors="replace")


@pytest.mark.django_db
def test_clickbait_detection_disabled_no_result_recorded(client_writer_logged_in, action_log_path):
    from accounts.models import ClickbaitDetectionResult

    client, _w = client_writer_logged_in

    article_id = _publish_and_detect(client, title_pos=1, body_pos=1, title_init=5, body_init=1)

    assert ClickbaitDetectionResult.objects.filter(文章_id=article_id).count() == 0
    art = Article.objects.get(pk=article_id)
    assert art.is_clickbait is None
    assert art.clickbait_auto_executed is False

    log_text = _read_log(action_log_path)
    assert "进入标题党检测功能" not in log_text


@pytest.mark.django_db
def test_clickbait_detection_enabled_records_and_updates(enable_clickbait_measure, client_writer_logged_in, action_log_path):
    from accounts.models import ClickbaitDetectionResult

    client, w = client_writer_logged_in

    article_id = _publish_and_detect(client, title_pos=1, body_pos=1, title_init=5, body_init=1)

    res = ClickbaitDetectionResult.objects.filter(文章_id=article_id).order_by("-id").first()
    assert res is not None
    assert res.自动检测是否执行 is True
    assert res.检测结果 is True
    assert res.判定来源 == 'auto'

    art = Article.objects.get(pk=article_id)
    assert art.is_clickbait is True
    assert art.clickbait_source == 'auto'
    assert art.clickbait_auto_executed is True

    log_text = _read_log(action_log_path)
    assert f"文章{article_id}" in log_text
    assert f"写手{w.账号}" in log_text
    assert "进入标题党检测功能" in log_text


@pytest.mark.django_db
def test_clickbait_detection_boundary_conditions(enable_clickbait_measure, client_writer_logged_in):
    """
    覆盖边界：
    - X==阈值, Y==阈值 => 非标题党（Y 需严格小于）
    - X==阈值, Y==阈值-1 => 标题党
    - X==阈值-1, Y==阈值-1 => 非标题党
    """
    from accounts.models import ClickbaitDetectionResult

    client, _w = client_writer_logged_in

    # case1: X==4, Y==3 => 非标题党
    a1 = _publish_and_detect(client, title_pos=0, body_pos=1, title_init=5, body_init=3)
    res1 = ClickbaitDetectionResult.objects.filter(文章_id=a1).order_by("-id").first()
    assert res1 is not None
    assert res1.检测结果 is False
    assert res1.判定来源 == 'auto'
    art1 = Article.objects.get(pk=a1)
    assert art1.is_clickbait is False
    assert art1.clickbait_source == 'auto'
    assert art1.clickbait_auto_executed is True

    # case2: X==4, Y==2 => 标题党
    a2 = _publish_and_detect(client, title_pos=0, body_pos=0, title_init=5, body_init=3)
    res2 = ClickbaitDetectionResult.objects.filter(文章_id=a2).order_by("-id").first()
    assert res2 is not None
    assert res2.检测结果 is True

    # case3: X==3, Y==2 => 非标题党
    a3 = _publish_and_detect(client, title_pos=1, body_pos=0, title_init=3, body_init=3)
    res3 = ClickbaitDetectionResult.objects.filter(文章_id=a3).order_by("-id").first()
    assert res3 is not None
    assert res3.检测结果 is False


@pytest.mark.django_db
def test_clickbait_detection_extremes(enable_clickbait_measure, client_writer_logged_in):
    from accounts.models import ClickbaitDetectionResult

    client, _w = client_writer_logged_in

    # X=1,Y=5 => 非标题党（Y 不满足 <3）
    # 五档映射：校准值 = initial + (position-1)，需在 [1,5]
    # body: initial=5, position=1 => Y=5（右侧不存在 sixth 档，因此不能用 position=2）
    a1 = _publish_and_detect(client, title_pos=1, body_pos=1, title_init=1, body_init=5)
    r1 = ClickbaitDetectionResult.objects.filter(文章_id=a1).order_by("-id").first()
    assert r1.检测结果 is False

    # X=5,Y=1 => 标题党
    # title: initial=5, position=1 => X=5（不能用 position=2，会越界到 6）
    a2 = _publish_and_detect(client, title_pos=1, body_pos=1, title_init=5, body_init=1)
    r2 = ClickbaitDetectionResult.objects.filter(文章_id=a2).order_by("-id").first()
    assert r2.检测结果 is True


@pytest.mark.django_db
def test_publish_requires_admin_active_config(client_platform_logged_in, db, platform_account):
    from accounts.models import ClickbaitDetectionConfig

    ClickbaitDetectionConfig.objects.filter(platform_id=platform_account.所属平台).delete()

    client, _p = client_platform_logged_in
    r = client.post("/platform/governance/publish/", {"measure_type": "clickbait_detection"})
    assert r.status_code == 400
    payload = r.json()
    assert "管理员尚未配置标题党检测默认参数" in (payload.get("error") or "")


@pytest.mark.django_db
def test_governance_toggle_flow(client_platform_logged_in, db, platform_account, active_clickbait_config, action_log_path):
    """
    覆盖“发布 -> 审核生效 -> 下一轮执行；取消 -> 下一轮不执行；再次发布 -> 下一轮重新生效”的主干字段与日志。

    说明：严格对齐系统实现：平台在轮次 R 发布，默认生效轮次=R+1。
    """
    client, p = client_platform_logged_in

    # 固定从 round=1 开始
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})

    # 1) publish @ round=1 => pending, effective_round=2
    r = client.post("/platform/governance/publish/", {"measure_type": "clickbait_detection"})
    assert r.status_code == 200
    rec1 = (
        PlatformGovernanceMeasure.objects.filter(平台=p.所属平台, 措施类型="clickbait_detection")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec1 is not None
    assert rec1.status == "pending"
    assert rec1.轮次 == 1
    assert rec1.生效轮次 == 2
    assert rec1.config_id == active_clickbait_config.pk

    # 2) approve => active，但当前仍在 round=1，不会执行检测
    rec1.status = "active"
    rec1.管理员确认账号 = "admin"
    rec1.save(update_fields=["status", "管理员确认账号"])

    # 3) end round => round becomes 2, measure effective
    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 2

    # 以平台账号发一篇“不会命中标题党”的文章：用于日志/字段断言（避免健康分副作用）
    from django.test import Client

    wc = Client()
    assert wc.post("/", {"account": "pytest_writer_1", "password": "pytest"}).status_code in (200, 302)
    aid = _publish_and_detect(wc, title_pos=1, body_pos=1, title_init=3, body_init=3)
    res = (
        ClickbaitDetectionResult.objects.filter(文章_id=aid).order_by("-id").first()
    )
    assert res is not None
    assert res.自动检测是否执行 is True
    assert res.检测结果 is False

    log_text = _read_log(action_log_path)
    assert "提交治理措施待审" in log_text
    assert "进入标题党检测功能" in log_text

    # 4) cancel @ round=2 => cancel_round=3
    r = client.post("/platform/governance/cancel/", {"measure_type": "clickbait_detection"})
    assert r.status_code == 200
    rec1.refresh_from_db()
    assert rec1.取消轮次 == 3

    # 5) round=3 => cancelled measure not effective => no detection records
    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 3

    wc2 = Client()
    assert wc2.post("/", {"account": "pytest_writer_2", "password": "pytest"}).status_code in (200, 302)
    r = wc2.post("/writer/start-article/")
    aid2 = r.json()["article_id"]
    wc2.post("/writer/select-title/", {"title_text": "t", "position": 1, "title_exaggeration_level": 5})
    wc2.post("/writer/select-body/", {"body_text": "b", "position": 1, "content_relevance_level": 1})
    assert ClickbaitDetectionResult.objects.filter(文章_id=aid2).count() == 0

    # 6) publish again @ round=3 => new pending record for effective_round=4
    r = client.post("/platform/governance/publish/", {"measure_type": "clickbait_detection"})
    assert r.status_code == 200
    rec2 = (
        PlatformGovernanceMeasure.objects.filter(平台=p.所属平台, 措施类型="clickbait_detection")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec2.pk != rec1.pk
    assert rec2.status == "pending"
    assert rec2.生效轮次 == 4

    rec2.status = "active"
    rec2.save(update_fields=["status"])

    r = client.post("/end-round/")
    assert r.status_code == 200
    assert _get_current_round() == 4

    wc3 = Client()
    assert wc3.post("/", {"account": "pytest_writer_3", "password": "pytest"}).status_code in (200, 302)
    aid3 = _publish_and_detect(wc3, title_pos=1, body_pos=1, title_init=5, body_init=1)
    assert ClickbaitDetectionResult.objects.filter(文章_id=aid3).count() == 1


@pytest.mark.django_db(transaction=True)
def test_clickbait_detection_concurrency(enable_clickbait_measure, writer_accounts):
    """
    并发场景：多个写手同时发布文章，检测应稳定落库且不丢失。

    注意：每个线程必须使用独立 Client + 独立写手账号，避免 Django test client 非线程安全。
    """
    from django.test import Client
    from accounts.models import ClickbaitDetectionResult

    def _publish_one(writer):
        c = Client()
        r = c.post("/", {"account": writer.账号, "password": writer.密码})
        assert r.status_code in (200, 302)
        aid = _publish_and_detect(c, title_pos=1, body_pos=1, title_init=5, body_init=1)
        return aid

    writers = writer_accounts[1:4]
    with ThreadPoolExecutor(max_workers=len(writers)) as ex:
        futs = [ex.submit(_publish_one, w) for w in writers]
        article_ids = [f.result(timeout=60) for f in as_completed(futs)]

    for aid in article_ids:
        assert ClickbaitDetectionResult.objects.filter(文章_id=aid).count() == 1
