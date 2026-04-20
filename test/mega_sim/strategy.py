from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class UserInteractionConfig:
    like_p: float = 0.20
    collect_p: float = 0.10
    read_complete_p: float = 0.35
    unfollow_p: float = 0.02
    switch_platform_p: float = 0.02
    report_p: float = 0.02


@dataclass(frozen=True)
class ReportTriggerConfig:
    enabled: bool
    target_articles_per_platform: int = 0
    trigger_report_p: float = 0.0
    threshold: str = "0.30"
    review_method: str = "auto"  # auto/manual


@dataclass(frozen=True)
class PlatformRoundPolicy:
    clickbait_p: float
    # 治理流程选择：normal/abnormal（由平台 agent 决定要走哪套发布顺序）
    governance_flow: str
    # 是否在本轮做“治理开关切换/取消/重发”等回归动作
    governance_toggle: bool = False


@dataclass(frozen=True)
class RoundPolicy:
    round_num: int
    # platform_id -> policy
    platforms: Dict[int, PlatformRoundPolicy]
    user_interactions: UserInteractionConfig
    report_trigger: Optional[ReportTriggerConfig] = None
    # 监管触发点
    regulator_patrol: bool = False
    regulator_fine: bool = False
    regulator_special_action: bool = False
    # 管理员是否需要在本轮做“人工审核/审批动作”
    admin_manual_reviews: bool = False


class MegaSimStrategy:
    """
    将《大型自动化模拟.md》中确认的 S0~S4 阶段策略固化为可执行策略。
    策略粒度：概率/阈值 + 特定轮次触发点（不做逐账号逐轮清单）。
    """

    def __init__(self, *, platforms: Iterable[int] = (0, 1, 2, 3)) -> None:
        self.platform_ids: Tuple[int, ...] = tuple(platforms)

    def round_policy(self, round_num: int) -> RoundPolicy:
        if round_num <= 0:
            raise ValueError("round_num must be >= 1")

        # 默认用户互动概率（可在触发轮覆盖）
        interactions = UserInteractionConfig()

        # --- 平台 clickbait 概率与治理流程（S0~S4） ---
        p: Dict[int, PlatformRoundPolicy] = {}

        def _set_all(clickbait: Dict[int, float], flow: Dict[int, str]) -> None:
            for pid in self.platform_ids:
                p[pid] = PlatformRoundPolicy(
                    clickbait_p=float(clickbait.get(pid, 0.0)),
                    governance_flow=str(flow.get(pid, "normal")),
                )

        # S0: 1-2
        if 1 <= round_num <= 2:
            _set_all(
                clickbait={0: 0.80, 3: 0.80, 1: 0.00, 2: 0.00},
                flow={0: "normal", 1: "abnormal", 2: "normal", 3: "abnormal"},
            )
            return RoundPolicy(round_num=round_num, platforms=p, user_interactions=interactions)

        # S1: 3-10
        if 3 <= round_num <= 10:
            _set_all(
                clickbait={0: 0.80, 3: 0.80, 1: 0.00, 2: 0.00},
                flow={0: "normal", 1: "abnormal", 2: "normal", 3: "abnormal"},
            )
            report_trigger = None
            if round_num == 6:
                report_trigger = ReportTriggerConfig(
                    enabled=True,
                    target_articles_per_platform=3,
                    trigger_report_p=0.60,
                    threshold="0.30",
                    review_method="auto",
                )
            # 平台4 在第5轮补齐前置并切回正常
            if round_num >= 5:
                p[3] = PlatformRoundPolicy(clickbait_p=p[3].clickbait_p, governance_flow="normal")
            return RoundPolicy(
                round_num=round_num,
                platforms=p,
                user_interactions=interactions,
                report_trigger=report_trigger,
            )

        # S2: 11-30
        if 11 <= round_num <= 30:
            # 平台2 扩散：分段
            if 11 <= round_num <= 14:
                p2_clickbait = 0.10
            elif 15 <= round_num <= 18:
                p2_clickbait = 0.50
            else:
                p2_clickbait = 0.80

            # 平台1 适度降低以触发恢复窗口
            p1_clickbait = 0.60

            # 平台4 逐步下降
            if 11 <= round_num <= 18:
                p4_clickbait = 0.80
            else:
                p4_clickbait = 0.30

            _set_all(
                clickbait={0: p1_clickbait, 1: p2_clickbait, 2: 0.00, 3: p4_clickbait},
                flow={
                    0: "normal",
                    1: "abnormal" if round_num < 20 else "normal",
                    2: "normal",
                    3: "normal",
                },
            )

            report_trigger = None
            admin_manual_reviews = False
            if round_num == 16:
                report_trigger = ReportTriggerConfig(
                    enabled=True,
                    target_articles_per_platform=3,
                    trigger_report_p=0.60,
                    threshold="0.30",
                    review_method="manual",
                )
            if round_num == 17:
                admin_manual_reviews = True

            return RoundPolicy(
                round_num=round_num,
                platforms=p,
                user_interactions=interactions,
                report_trigger=report_trigger,
                admin_manual_reviews=admin_manual_reviews,
            )

        # S3: 31-60
        if 31 <= round_num <= 60:
            _set_all(
                clickbait={0: 0.60, 1: 0.80, 2: 0.00, 3: 0.50},
                flow={0: "normal", 1: "normal", 2: "normal", 3: "normal"},
            )

            regulator_patrol = (round_num % 5 == 0)
            regulator_fine = round_num in (35, 45, 55)
            regulator_special_action = (round_num == 40)

            return RoundPolicy(
                round_num=round_num,
                platforms=p,
                user_interactions=interactions,
                regulator_patrol=regulator_patrol,
                regulator_fine=regulator_fine,
                regulator_special_action=regulator_special_action,
            )

        # S4: 61-100
        if 61 <= round_num <= 100:
            _set_all(
                clickbait={0: 0.50, 1: 0.70, 2: 0.00, 3: 0.30},
                flow={0: "normal", 1: "normal", 2: "normal", 3: "normal"},
            )
            # 每 10 轮一个“全正常档”窗口：用治理验证负例路径
            if round_num % 10 == 0:
                for pid in list(p.keys()):
                    p[pid] = PlatformRoundPolicy(clickbait_p=0.0, governance_flow=p[pid].governance_flow)

            governance_toggle = (round_num in (70, 71, 80, 81))
            if governance_toggle:
                # 随机挑一个平台做取消/重发，具体平台由编排器基于 seed 决定
                for pid in list(p.keys()):
                    p[pid] = PlatformRoundPolicy(
                        clickbait_p=p[pid].clickbait_p,
                        governance_flow=p[pid].governance_flow,
                        governance_toggle=True,
                    )

            return RoundPolicy(round_num=round_num, platforms=p, user_interactions=interactions)

        raise ValueError("round_num out of supported range (1-100)")

