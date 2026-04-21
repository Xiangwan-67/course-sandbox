from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import (
    AccountHealthConfig,
    AccountHealthLevelConfig,
    PlatformGovernanceMeasure,
    SimulationRound,
    WriterAccount,
)


@pytest.mark.django_db
def test_health_score_over_100_is_normalized_to_100_on_round_end(writer_accounts):
    """
    防御：历史遗留数据若出现 100+，系统在结算/同步阶段会归一化回 100。
    """
    w = writer_accounts[0]
    WriterAccount.objects.filter(pk=w.pk).update(健康分=105, 所属平台=0)

    AccountHealthConfig.objects.create(
        platform_id=0,
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
        平台=0,
        config=None,
        档位标签="正常",
        生效轮次起=1,
        下界开=0,
        上界闭=100,
        可推流比例=Decimal("1.0000"),
        排序=1,
    )
    PlatformGovernanceMeasure.objects.create(
        平台=0,
        轮次=1,
        生效轮次=1,
        措施类型="account_health_rule",
        措施内容={},
        config_id=None,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})

    from django.test import Client

    c = Client()
    assert c.post("/", {"account": "pytest_platform_0", "password": "pytest"}).status_code in (200, 302)
    r = c.post("/end-round/")
    assert r.status_code == 200

    w.refresh_from_db()
    assert w.健康分 == 100

