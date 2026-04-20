from __future__ import annotations

import json

import pytest

from accounts.models import PlatformSelfPatrolApplication, SimulationRound


@pytest.mark.django_db
def test_platform_self_patrol_submit_success(client_platform_logged_in):
    client, platform_account = client_platform_logged_in
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)

    r = client.post(
        "/platform/platform-patrol/submit/",
        data=json.dumps(
            {
                "platform_id": platform_account.所属平台,
                "patrol_ratio": "1",
                "start_round": 2,
                "end_round": 2,
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True
    app = PlatformSelfPatrolApplication.objects.order_by("-id").first()
    assert app is not None
    assert app.平台编号 == platform_account.所属平台
    assert app.申请状态 == "pending"
    assert app.巡查比例 == 1
    assert app.起始轮次 == 2
    assert app.终止轮次 == 2


@pytest.mark.django_db
def test_platform_self_patrol_submit_duplicate_pending_rejected(client_platform_logged_in):
    client, platform_account = client_platform_logged_in
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)

    body = {
        "platform_id": platform_account.所属平台,
        "patrol_ratio": "1",
        "start_round": 1,
        "end_round": 1,
    }
    r1 = client.post(
        "/platform/platform-patrol/submit/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/platform/platform-patrol/submit/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r2.status_code == 400
    assert "待审核" in (r2.json().get("error") or "")


@pytest.mark.django_db
def test_platform_self_patrol_submit_end_round_must_be_before_current(client_platform_logged_in):
    client, platform_account = client_platform_logged_in
    SimulationRound.objects.filter(pk=1).update(当前轮次=2)

    r = client.post(
        "/platform/platform-patrol/submit/",
        data=json.dumps(
            {
                "platform_id": platform_account.所属平台,
                "patrol_ratio": "0.5",
                "start_round": 1,
                "end_round": 2,
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "终止轮次" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_self_patrol_submit_wrong_platform_rejected(client_platform_logged_in):
    client, platform_account = client_platform_logged_in
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)

    r = client.post(
        "/platform/platform-patrol/submit/",
        data=json.dumps(
            {
                "platform_id": 99,
                "patrol_ratio": "1",
                "start_round": 1,
                "end_round": 1,
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "本平台" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_platform_home_renders_monitoring_section(client_platform_logged_in):
    client, _platform = client_platform_logged_in

    r = client.get("/platform/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "平台监测系统" in html
    assert "启动巡查" in html
