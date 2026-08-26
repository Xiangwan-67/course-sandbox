from __future__ import annotations

import pytest

from accounts.models import Article, PlatformGovernanceMeasure, SimulationRound, WriterAccount, WriterHealthScoreLog


@pytest.mark.django_db
def test_writer_health_popup_shows_once_and_can_confirm(client, writer_accounts):
    w = writer_accounts[0]
    WriterAccount.objects.filter(pk=w.pk).update(健康分=90)

    # 健康分规则在第1轮已生效
    PlatformGovernanceMeasure.objects.create(
        平台=w.所属平台,
        轮次=1,
        生效轮次=1,
        措施类型="account_health_rule",
        措施内容={},
        config_id=None,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    a = Article.objects.create(
        写手账号=w.账号,
        轮次=1,
        标题="测试标题党文章",
        正文="x",
        is_published=True,
    )
    log = WriterHealthScoreLog.objects.create(
        写手账号=w.账号,
        轮次=1,
        event_type="violation",
        文章编号=a.pk,
        变更值=-10,
        原因="pytest",
        已确认=False,
    )

    # 进入第2轮初：应弹出上一轮审计记录
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 2})

    r = client.post("/", {"account": w.账号, "password": w.密码})
    assert r.status_code in (200, 302)

    r = client.get("/writer/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert 'id="hs_modal"' in html
    assert "测试标题党文章" in html
    assert str(log.pk) in html

    # 确认后：不再弹
    r = client.post(f"/writer/health-log/{log.pk}/confirm/")
    assert r.status_code == 200
    assert r.json().get("ok") is True

    log.refresh_from_db()
    assert log.已确认 is True

    r = client.get("/writer/")
    html2 = r.content.decode("utf-8", errors="replace")
    assert 'id="hs_modal"' not in html2

