from __future__ import annotations

import pytest

from accounts.models import (
    AccountHealthConfig,
    PlatformGovernanceMeasure,
    WriterGovernanceNotice,
)
from accounts.governance_notices import dispatch_governance_notices_for_round
from accounts.views import _get_current_round


@pytest.mark.django_db
def test_writer_notices_only_dispatched_for_account_health_rule(writer_accounts):
    """
    写手端「平台通知」仅投递账号健康分治理措施，其它措施不投递收件箱。
    """
    round_num = _get_current_round()
    platform_id = 0

    cfg = AccountHealthConfig.objects.create(
        platform_id=platform_id,
        初始健康分=100,
        每次违规扣减分值=10,
        是否启用恢复机制=False,
        恢复所需连续无违规轮次=3,
        每次恢复分值=5,
        status="active",
        提交人账号="admin",
        管理员确认账号="admin",
    )

    PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="account_health_rule",
        措施内容={},
        config_id=cfg.pk,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="traffic_penalty",
        措施内容={},
        config_id=None,
        发布人账号="pytest_platform_0",
        status="active",
        管理员确认账号="admin",
    )

    dispatch_governance_notices_for_round(round_num)

    # 每个写手只收到 1 条健康分通知
    for w in writer_accounts:
        rows = list(WriterGovernanceNotice.objects.filter(写手账号=w.账号))
        assert len(rows) == 1
        assert rows[0].measure.措施类型 == "account_health_rule"

