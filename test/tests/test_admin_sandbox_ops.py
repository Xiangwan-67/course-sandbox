from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from accounts.models import PlatformPerformanceScheme, SimulationRound


@pytest.mark.django_db
def test_sandbox_ops_requires_staff(client):
    r = client.get("/admin/sandbox-ops/", follow=False)
    assert r.status_code == 302
    assert "/admin/login" in r.url or r.url.endswith("login/")


@pytest.mark.django_db
def test_sandbox_ops_get_ok_for_staff(client, db):
    User.objects.create_user("ops_staff", password="secret", is_staff=True)
    assert client.login(username="ops_staff", password="secret") is True
    r = client.get("/admin/sandbox-ops/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "沙盘运营台" in html


@pytest.mark.django_db
def test_sandbox_ops_end_round_advances_round(client, db):
    User.objects.create_user("ops_staff2", password="secret2", is_staff=True)
    assert client.login(username="ops_staff2", password="secret2") is True
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 3})
    r = client.post(
        "/admin/sandbox-ops/",
        {"op": "end_round", "tab": "regulator"},
    )
    assert r.status_code == 302
    assert SimulationRound.objects.get(pk=1).当前轮次 == 4


@pytest.mark.django_db
def test_sandbox_ops_approve_performance_scheme(client, db):
    User.objects.create_user("ops_staff3", password="secret3", is_staff=True)
    assert client.login(username="ops_staff3", password="secret3") is True
    rec = PlatformPerformanceScheme.objects.create(
        平台=0,
        生效轮次=2,
        方案编号="S1_balanced",
        status="pending",
        发布人账号="pytest_platform_0",
    )
    r = client.post(
        "/admin/sandbox-ops/",
        {
            "op": "approve",
            "tab": "performance",
            "model": "platform_performance_scheme",
            "pk": str(rec.pk),
        },
    )
    assert r.status_code == 302
    rec.refresh_from_db()
    assert rec.status == "active"
