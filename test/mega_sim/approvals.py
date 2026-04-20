from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from accounts.models import (
    Article,
    ArticleReport,
    ClickbaitDetectionConfig,
    PlatformGovernanceMeasure,
    RevenuePenaltyConfig,
    TrafficPenaltyConfig,
    UserReportConfig,
)


def approve_pending_configs_and_measures(*, admin_account: str = "mega_sim_admin") -> None:
    """
    “零侵入”审批模拟：将 pending 配置/措施置为 active。
    注意：这不是改业务代码，只是自动化在测试库里做等价落库效果。
    """
    now = timezone.now()

    for model in (TrafficPenaltyConfig, RevenuePenaltyConfig, UserReportConfig):
        model.objects.filter(status="pending").update(
            status="active",
            管理员确认账号=admin_account,
            管理员确认时间=now,
        )

    # clickbait_detection config 由 world_seed 预置 active；这里容错地把 pending 也激活
    ClickbaitDetectionConfig.objects.filter(status="pending").update(
        status="active",
        管理员确认账号=admin_account,
        管理员确认时间=now,
    )

    PlatformGovernanceMeasure.objects.filter(status="pending").update(
        status="active",
        管理员确认账号=admin_account,
        管理员确认时间=now,
    )


def manual_review_reports_for_round(*, report_round: int, admin_account: str = "mega_sim_admin") -> int:
    """
    对某一举报轮次的 pending 举报做“人工审核通过/不通过”覆盖：
    - 达阈值：通过（置 Article.is_clickbait=True, method_user=True；ArticleReport 审核状态=approved）
    - 未达阈值：保持 pending（等价于未处理/未通过）

    阈值/审核方式来自 UserReportConfig 的最新 active 记录（按 platform_id）。
    """
    reviewed = 0
    now = timezone.now()

    # 先按平台分组，读取阈值；避免每条查询一次
    platform_ids = list(
        ArticleReport.objects.filter(举报轮次=report_round, 审核状态="pending")
        .values_list("platform_id", flat=True)
        .distinct()
    )
    cfg_by_platform = {
        pid: UserReportConfig.objects.filter(platform_id=pid, status="active").order_by("-id").first()
        for pid in platform_ids
    }

    for pid in platform_ids:
        cfg = cfg_by_platform.get(pid)
        if not cfg:
            continue
        threshold = cfg.举报触发阈值

        # 对每篇文章计算 ratio = report_count / click_count
        art_ids = list(
            ArticleReport.objects.filter(platform_id=pid, 举报轮次=report_round, 审核状态="pending")
            .values_list("文章_id", flat=True)
            .distinct()
        )
        for art_id in art_ids:
            try:
                art = Article.objects.get(pk=art_id)
            except Article.DoesNotExist:
                continue
            report_cnt = ArticleReport.objects.filter(platform_id=pid, 文章_id=art_id, 举报轮次=report_round).count()
            read_cnt = int(art.点击量 or 1)
            ratio = report_cnt / float(read_cnt)
            if ratio >= float(threshold):
                Article.objects.filter(pk=art_id).update(is_clickbait=True, method_user=True)
                ArticleReport.objects.filter(platform_id=pid, 文章_id=art_id, 举报轮次=report_round).update(审核状态="approved")
                reviewed += 1

    return reviewed

