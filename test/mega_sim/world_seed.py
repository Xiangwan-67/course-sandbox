from __future__ import annotations

from datetime import datetime
from typing import Iterable

from django.utils import timezone

from accounts.models import (
    AccountHealthConfig,
    AccountHealthLevelConfig,
    ClickbaitDetectionConfig,
    PlatformGovernanceMeasure,
)


def seed_required_admin_configs(*, platform_ids: Iterable[int]) -> None:
    """
    在“零侵入”约束下，为了让平台侧能发布 clickbait_detection/account_health_rule，
    需要在测试库里预置管理员侧的 active 配置（平台侧无法配置标题党检测参数）。
    """
    now = timezone.now()
    for pid in platform_ids:
        ClickbaitDetectionConfig.objects.update_or_create(
            platform_id=int(pid),
            defaults={
                "标题夸张度阈值X": 4,
                "内容相关度阈值Y": 3,
                "status": "active",
                "提交人账号": "mega_sim_seed",
                "管理员确认账号": "mega_sim_seed",
                "管理员确认时间": now,
            },
        )

        # 账号健康分：提供一个基础规则 + 档位，便于写手端扣分/推流系数联动覆盖
        health_cfg, _ = AccountHealthConfig.objects.update_or_create(
            platform_id=int(pid),
            defaults={
                "每次违规扣减分值": 10,
                "恢复所需连续无违规轮次": 3,
                "status": "active",
                "提交人账号": "mega_sim_seed",
                "管理员确认账号": "mega_sim_seed",
                "管理员确认时间": now,
            },
        )

        # 默认档位：100/80/60/40/20/0 六档（可推流比例简单线性）
        # 区间为“前开后闭”：(下界开, 上界闭]
        levels = [
            (80, 100, 1.00, "A"),
            (60, 80, 0.90, "B"),
            (40, 60, 0.80, "C"),
            (20, 40, 0.60, "D"),
            (0, 20, 0.40, "E"),
            (-1, 0, 0.20, "F"),
        ]
        for idx, (low_open, high_close, ratio, tier) in enumerate(levels, start=1):
            AccountHealthLevelConfig.objects.update_or_create(
                平台=int(pid),
                config_id=health_cfg.pk,
                档位标签=tier,
                defaults={
                    "下界开": int(low_open),
                    "上界闭": int(high_close),
                    "可推流比例": str(ratio),
                    "生效轮次起": 1,
                    "生效轮次止": None,
                    "排序": idx,
                    "备注": "mega_sim_seed",
                },
            )

        # 提前存在一条 active 的健康分措施记录，后续平台可做“异常顺序/取消/重发”覆盖
        PlatformGovernanceMeasure.objects.get_or_create(
            平台=int(pid),
            措施类型="account_health_rule",
            status="active",
            生效轮次=1,
            defaults={
                "轮次": 1,
                "措施内容": {},
                "config_id": health_cfg.pk,
                "发布人账号": "mega_sim_seed",
                "管理员确认账号": "mega_sim_seed",
            },
        )

