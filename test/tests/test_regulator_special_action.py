from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import site
from django.test import RequestFactory

from accounts.admin import RegulationActionApplicationAdmin
from accounts.models import (
    RegulationAction,
    RegulationActionApplication,
    RegulatorAccount,
    SimulationRound,
)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def regulator_log_path(settings) -> Path:
    return Path(settings.BASE_DIR) / "logs" / "regulator_actions.log"


@pytest.fixture
def client_regulator_logged_in(client, db):
    RegulatorAccount.objects.update_or_create(
        账号="pytest_regulator_0",
        defaults={"密码": "pytest"},
    )
    r = client.post("/", {"account": "pytest_regulator_0", "password": "pytest"})
    assert r.status_code in (200, 302)
    return client


@pytest.mark.django_db
def test_regulator_submit_application_success(client_regulator_logged_in, action_log_path, regulator_log_path):
    client = client_regulator_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 3})

    r = client.post(
        "/regulator/special-action/submit/",
        content_type="application/json",
        data='{"platform_ids":[0,1],"duration_rounds":8,"reason":"定期整治","reason_other":""}',
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("action_id") == "0001"
    assert body.get("active_round_range") == {"start_round": 4, "end_round": 11}

    app = RegulationActionApplication.objects.order_by("-id").first()
    assert app is not None
    assert app.申请状态 == "pending"
    assert app.整治平台编号列表 == [0, 1]
    assert app.整治平台名称列表 == ["平台1", "平台2"]
    assert app.整治持续轮次 == 8
    assert app.当前轮次 == 3

    action_log_text = _read(action_log_path)
    regulator_log_text = _read(regulator_log_path)
    assert "监管机构提交专项整治申请 action_id=0001" in action_log_text
    assert "监管机构确认发起专项整治 action_id=0001" in regulator_log_text


@pytest.mark.django_db
def test_regulator_submit_blocked_when_platform_under_regulation(client_regulator_logged_in):
    client = client_regulator_logged_in
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 5})
    RegulationAction.objects.create(
        行动编号="0001",
        当前轮次=4,
        整治平台编号=0,
        整治平台名称="平台1",
        整治持续轮次=4,
        开始轮次=5,
        结束轮次=8,
        整治原因="定期整治",
        状态="active",
    )

    r = client.post(
        "/regulator/special-action/submit/",
        content_type="application/json",
        data='{"platform_ids":[0],"duration_rounds":4,"reason":"定期整治","reason_other":""}',
    )
    assert r.status_code == 400
    assert "处于整治中" in (r.json().get("error") or "")
    assert RegulationActionApplication.objects.count() == 0


@pytest.mark.django_db
def test_admin_approve_application_creates_formal_records(action_log_path, regulator_log_path):
    app = RegulationActionApplication.objects.create(
        行动编号="0003",
        当前轮次=3,
        整治平台编号列表=[0, 1],
        整治平台名称列表=["平台1", "平台2"],
        整治持续轮次=4,
        整治原因="标题党率过高",
        申请状态="pending",
        申请人账号="pytest_regulator_0",
    )
    admin_instance = RegulationActionApplicationAdmin(RegulationActionApplication, site)
    request = RequestFactory().post("/admin/accounts/regulationactionapplication/")
    request.user = SimpleNamespace(username="pytest_admin")

    admin_instance.approve_applications(request, RegulationActionApplication.objects.filter(pk=app.pk))

    app.refresh_from_db()
    assert app.申请状态 == "approved"
    assert app.管理员确认账号 == "pytest_admin"
    records = list(RegulationAction.objects.filter(行动编号="0003").order_by("整治平台编号"))
    assert len(records) == 2
    assert records[0].整治平台编号 == 0
    assert records[0].开始轮次 == 4
    assert records[0].结束轮次 == 7
    assert records[1].整治平台编号 == 1
    assert records[1].开始轮次 == 4
    assert records[1].结束轮次 == 7

    action_log_text = _read(action_log_path)
    regulator_log_text = _read(regulator_log_path)
    assert "管理员审核通过监管专项整治 action_id=0003" in regulator_log_text
    assert "管理员审核通过监管专项整治 action_id=0003" not in action_log_text


@pytest.mark.django_db
def test_admin_reject_application_no_formal_record(regulator_log_path):
    app = RegulationActionApplication.objects.create(
        行动编号="0008",
        当前轮次=8,
        整治平台编号列表=[1],
        整治平台名称列表=["平台2"],
        整治持续轮次=12,
        整治原因="用户投诉激增",
        申请状态="pending",
        申请人账号="pytest_regulator_0",
    )
    admin_instance = RegulationActionApplicationAdmin(RegulationActionApplication, site)
    request = RequestFactory().post("/admin/accounts/regulationactionapplication/")
    request.user = SimpleNamespace(username="pytest_admin")

    admin_instance.reject_applications(request, RegulationActionApplication.objects.filter(pk=app.pk))

    app.refresh_from_db()
    assert app.申请状态 == "rejected"
    assert app.管理员确认账号 == "pytest_admin"
    assert RegulationAction.objects.filter(行动编号="0008").count() == 0
    assert "管理员驳回监管专项整治申请 action_id=0008" in _read(regulator_log_path)
