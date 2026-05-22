from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from accounts.models import Article, PlatformGovernanceMeasure, SimulationRound, WriterAccount


@pytest.mark.django_db
def test_sandbox_monitor_requires_staff(client):
    r = client.get("/admin/sandbox-monitor/", follow=False)
    assert r.status_code == 302


@pytest.mark.django_db
def test_sandbox_monitor_page_has_users_section(client, db):
    User.objects.create_user("mon_staff", password="secret", is_staff=True)
    client.login(username="mon_staff", password="secret")
    r = client.get("/admin/sandbox-monitor/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "用户平台分布" in html
    assert "pytest_user_" in html


@pytest.mark.django_db
def test_api_writers_published_requires_title_and_body(client, db, writer_accounts):
    User.objects.create_user("mon_staff2", password="secret2", is_staff=True)
    client.login(username="mon_staff2", password="secret2")
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 2})
    w = writer_accounts[0]

    Article.objects.create(写手账号=w.账号, 轮次=2, 标题="", 正文="body")
    r = client.get("/admin/sandbox-monitor/api/writers/?round=2")
    assert r.status_code == 200
    data = r.json()
    assert "users" not in data
    row = next(
        x for x in data["writers"]["platforms"][0]["writers"] if x["account"] == w.账号
    )
    assert row["published"] is False

    Article.objects.filter(写手账号=w.账号, 轮次=2).delete()
    Article.objects.create(写手账号=w.账号, 轮次=2, 标题="t", 正文="b")
    r2 = client.get("/admin/sandbox-monitor/api/writers/?round=2")
    row2 = next(
        x for x in r2.json()["writers"]["platforms"][0]["writers"] if x["account"] == w.账号
    )
    assert row2["published"] is True


@pytest.mark.django_db
def test_api_writers_all_published_summary(client, db):
    User.objects.create_user("mon_staff3", password="secret3", is_staff=True)
    client.login(username="mon_staff3", password="secret3")
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})
    for w in WriterAccount.objects.all():
        Article.objects.create(写手账号=w.账号, 轮次=1, 标题="x", 正文="y")
    r = client.get("/admin/sandbox-monitor/api/writers/?round=1")
    data = r.json()
    assert data["summary"]["all_published"] is True
    assert data["summary"]["published_writers"] == data["summary"]["total_writers"]


@pytest.mark.django_db
def test_api_governance_includes_measure(client, db, platform_account):
    User.objects.create_user("mon_staff4", password="secret4", is_staff=True)
    client.login(username="mon_staff4", password="secret4")
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=1,
        生效轮次=1,
        措施类型="clickbait_detection",
        status="active",
        发布人账号="pytest",
        管理员确认账号="admin",
    )
    r = client.get("/admin/sandbox-monitor/api/governance/?round=1")
    assert r.status_code == 200
    data = r.json()
    plat = data["governance"]["platforms"][0]
    types = [m["type"] for m in plat["measures"]]
    assert "clickbait_detection" in types
