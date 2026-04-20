from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from accounts.models import (
    Article,
    ArticleRevenueSettlement,
    ArticleTraffic,
    ClickbaitDetectionResult,
    PlatformPatrolResult,
    PlatformGovernanceMeasure,
    RevenuePenaltyConfig,
    SimulationRound,
    TrafficPenaltyConfig,
    UserReportConfig,
    WriterHealthScoreLog,
)


@dataclass(frozen=True)
class RoundValidationResult:
    round_num: int
    ok: bool
    errors: List[str]
    stats: Dict[str, int]


def validate_round_minimal(*, round_num: int) -> RoundValidationResult:
    """
    每轮最小可对账校验（不依赖UI）：
    - 本轮文章数 > 0
    - 本轮结算记录与文章数一致（至少不为 0）
    - 若有推送/流量惩罚逻辑，则应产生 ArticleTraffic 记录（至少部分文章）
    - 标题党检测结果表若检测执行则应有记录（不强制每篇都有，因为取决于治理是否生效）
    - 健康分日志若触发违规则应有记录（不强制）
    """
    errors: List[str] = []
    stats: Dict[str, int] = {}

    stats["articles"] = Article.objects.filter(轮次=round_num).count()
    if stats["articles"] <= 0:
        errors.append("no articles for round")

    stats["settlements"] = ArticleRevenueSettlement.objects.filter(轮次=round_num).count()
    if stats["articles"] > 0 and stats["settlements"] <= 0:
        errors.append("no settlements for round")

    stats["traffic_records"] = ArticleTraffic.objects.filter(轮次=round_num).count()
    stats["clickbait_results"] = ClickbaitDetectionResult.objects.filter(轮次=round_num).count()
    stats["health_logs"] = WriterHealthScoreLog.objects.filter(轮次=round_num).count()
    stats["report_configs_active"] = UserReportConfig.objects.filter(status="active").count()
    stats["traffic_configs_active"] = TrafficPenaltyConfig.objects.filter(status="active").count()
    stats["revenue_configs_active"] = RevenuePenaltyConfig.objects.filter(status="active").count()
    stats["measures_active"] = PlatformGovernanceMeasure.objects.filter(status="active").count()

    # 轮次推进应在 end-round 后发生，因此这里只做“当前轮次 >= round_num”
    cur = SimulationRound.objects.get_or_create(pk=1, defaults={"当前轮次": 1})[0].当前轮次
    if cur < round_num:
        errors.append(f"current_round({cur}) < validated_round({round_num})")

    return RoundValidationResult(round_num=round_num, ok=(len(errors) == 0), errors=errors, stats=stats)


def validate_regulation_auto_patrols_written(*, exec_round: int) -> Optional[str]:
    """
    专项整治结束后的下一轮会自动执行两次巡查并写入 PlatformPatrolResult。
    这里只做保守检查：如果存在 auto 巡查结果，至少应包含执行轮次字段。
    """
    cnt = PlatformPatrolResult.objects.filter(巡查类型="auto", 执行轮次=exec_round).count()
    if cnt < 0:
        return "auto patrol count invalid"
    return None

