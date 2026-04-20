from __future__ import annotations

import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from django.conf import settings

from accounts.models import PlatformAccount, RegulatorAccount, UserAccount, WriterAccount

from .agents import AdminAgent, LoginInfo, PlatformAgent, RegulatorAgent, UserAgent, WriterAgent
from .approvals import approve_pending_configs_and_measures, manual_review_reports_for_round
from .logging_utils import AgentLogContext, build_agent_logger, race_condition, round_banner
from .snapshot import snapshot_db_pre_round
from .strategy import MegaSimStrategy, RoundPolicy
from .validators import validate_round_minimal
from .world_seed import seed_required_admin_configs


@dataclass(frozen=True)
class MegaSimConfig:
    rounds: int = 100
    seed: int = 20260420
    # 每个用户每轮点击文章数（从浏览列表抽样）
    user_reads_per_round: int = 5


class MegaSimOrchestrator:
    def __init__(self, *, cfg: MegaSimConfig, work_dir: Path) -> None:
        self.cfg = cfg
        self.work_dir = work_dir
        # 日志固定写入仓库目录 test/mega_sim/logs/mega_sim.log（用户要求）
        self.logs_dir = Path(__file__).resolve().parent / "logs"
        self.snap_dir = work_dir / "snapshots"
        self.summary_log = build_agent_logger(base_dir=self.logs_dir, ctx=AgentLogContext(role="orchestrator", account="main"))
        self.strategy = MegaSimStrategy()

    def _seed_for(self, *, round_num: int, tag: str, account: str) -> int:
        # 可重放：全局 seed + round + account hash
        return abs(hash((self.cfg.seed, round_num, tag, account))) % (2**31 - 1)

    def _pick_accounts(self) -> Tuple[List[WriterAccount], List[UserAccount], List[PlatformAccount], List[RegulatorAccount]]:
        writers = list(WriterAccount.objects.all().order_by("id"))
        users = list(UserAccount.objects.all().order_by("id"))
        platforms = list(PlatformAccount.objects.all().order_by("id"))
        regulators = list(RegulatorAccount.objects.all().order_by("id"))
        if not writers or not users or not platforms:
            raise RuntimeError("accounts not seeded; ensure load_accounts or fixtures prepared in pytest db")
        return writers, users, platforms, regulators

    def run(self) -> None:
        writers, users, platforms, regulators = self._pick_accounts()
        seed_required_admin_configs(platform_ids=self.strategy.platform_ids)
        for r in regulators:
            if not (r.负责平台编号列表 or []):
                r.负责平台编号列表 = list(self.strategy.platform_ids)
                r.save(update_fields=["负责平台编号列表"])

        # AdminAgent：pytest 下不一定有管理员账号表；这里复用 platform_0 账号仅用于调用 /end-round/
        # /end-round/ 不校验 role，因此无需 admin session。
        admin_login = LoginInfo(account=platforms[0].账号, password=platforms[0].密码)
        admin = AdminAgent(login=admin_login, seed=self._seed_for(round_num=1, tag="admin", account=admin_login.account))
        admin.login_session()

        for round_num in range(1, self.cfg.rounds + 1):
            try:
                rp = self.strategy.round_policy(round_num)
                self.summary_log.info(round_banner(round_num, seed=self.cfg.seed))
                snapshot_db_pre_round(round_num=round_num, snapshot_dir=self.snap_dir)

                # 1) 平台提交配置/发布（并发）
                self._run_platform_actions(round_num=round_num, rp=rp, platforms=platforms)

                # 2) 写手发文（并发）
                published_by_writer = self._run_writer_actions(round_num=round_num, rp=rp, writers=writers)

                # 3) 用户浏览与互动（并发）
                self._run_user_actions(round_num=round_num, rp=rp, users=users, published_article_ids=published_by_writer)

                # 4) 监管行为（本轮触发点）
                if regulators:
                    self._run_regulator_actions(round_num=round_num, rp=rp, regulators=regulators)

                # 4.5) 人工审核覆盖：第17轮审核第16轮举报（与策略文档对齐）
                if rp.admin_manual_reviews:
                    reviewed = manual_review_reports_for_round(report_round=round_num - 1, admin_account="mega_sim_admin")
                    self.summary_log.info(f"manual_review_reports ok reviewed_articles={reviewed} report_round={round_num-1}")

                # 4.8) 轮次屏障（Barrier）最小校验：写手发文必须完成
                from accounts.models import Article
                expected_articles = len(writers)
                actual_articles = Article.objects.filter(轮次=round_num).count()
                if actual_articles < expected_articles:
                    raise AssertionError(f"barrier failed: articles_in_round={actual_articles} < expected_writers={expected_articles}")

                # 5) 屏障满足后推进轮次
                result = admin.end_round()
                self.summary_log.info(f"end_round ok new_round={result.get('current_round')}")

                # 6) 每轮校验
                v = validate_round_minimal(round_num=round_num)
                self.summary_log.info(f"validate round={round_num} ok={v.ok} stats={v.stats}")
                if not v.ok:
                    raise AssertionError(f"round validation failed: {v.errors} stats={v.stats}")
            except Exception as e:
                self.summary_log.error(f"STOP | round={round_num} error_type={type(e).__name__} error={e}")
                raise AssertionError(
                    f"mega_sim stopped at round {round_num}: {type(e).__name__}: {e} "
                    f"| replay: MEGA_SIM_RUN=1 MEGA_SIM_ROUNDS={round_num} MEGA_SIM_SEED={self.cfg.seed} "
                    f"| snapshot_dir={self.snap_dir}"
                ) from e

    def _run_platform_actions(self, *, round_num: int, rp: RoundPolicy, platforms: Sequence[PlatformAccount]) -> None:
        # A) 提交配置
        futures = []
        with ThreadPoolExecutor(max_workers=len(platforms)) as ex:
            for p in platforms:
                seed = self._seed_for(round_num=round_num, tag="platform", account=p.账号)
                agent = PlatformAgent(login=LoginInfo(p.账号, p.密码), seed=seed)
                logger = build_agent_logger(
                    base_dir=self.logs_dir,
                    ctx=AgentLogContext(role="platform", account=p.账号, platform_id=getattr(p, "所属平台", None)),
                )
                futures.append(ex.submit(self._platform_submit_configs_one, agent, logger, round_num, rp, int(getattr(p, "所属平台", 0))))
            for fut in as_completed(futures):
                fut.result()

        # B) 管理员审批配置（ORM）
        approve_pending_configs_and_measures(admin_account="mega_sim_admin")

        # C) 发布措施
        futures = []
        with ThreadPoolExecutor(max_workers=len(platforms)) as ex:
            for p in platforms:
                seed = self._seed_for(round_num=round_num, tag="platform", account=p.账号)
                agent = PlatformAgent(login=LoginInfo(p.账号, p.密码), seed=seed)
                logger = build_agent_logger(
                    base_dir=self.logs_dir,
                    ctx=AgentLogContext(role="platform", account=p.账号, platform_id=getattr(p, "所属平台", None)),
                )
                futures.append(ex.submit(self._platform_publish_measures_one, agent, logger, round_num, rp, int(getattr(p, "所属平台", 0))))
            for fut in as_completed(futures):
                fut.result()

        # D) 管理员审批措施（ORM）
        approve_pending_configs_and_measures(admin_account="mega_sim_admin")

    def _platform_submit_configs_one(self, agent: PlatformAgent, logger: logging.Logger, round_num: int, rp: RoundPolicy, platform_id: int) -> None:
        try:
            agent.login_session()
            pol = rp.platforms.get(platform_id)
            if not pol:
                return
            logger.info(round_banner(round_num, seed=agent.seed))
            agent.submit_governance_configs(flow=pol.governance_flow)
        except Exception as e:
            race_condition(logger, round_num=round_num, action="platform_submit_configs", error=e, extra={"platform_id": platform_id})
            raise

    def _platform_publish_measures_one(self, agent: PlatformAgent, logger: logging.Logger, round_num: int, rp: RoundPolicy, platform_id: int) -> None:
        try:
            agent.login_session()
            pol = rp.platforms.get(platform_id)
            if not pol:
                return
            logger.info(round_banner(round_num, seed=agent.seed))
            agent.publish_governance_measures(flow=pol.governance_flow)
        except Exception as e:
            race_condition(logger, round_num=round_num, action="platform_publish_measures", error=e, extra={"platform_id": platform_id})
            raise

    def _run_writer_actions(self, *, round_num: int, rp: RoundPolicy, writers: Sequence[WriterAccount]) -> Dict[str, int]:
        published: Dict[str, int] = {}
        futures = []
        with ThreadPoolExecutor(max_workers=len(writers)) as ex:
            for w in writers:
                platform_id = int(getattr(w, "所属平台", 0))
                pol = rp.platforms.get(platform_id)
                if not pol:
                    continue
                seed = self._seed_for(round_num=round_num, tag="writer", account=w.账号)
                agent = WriterAgent(login=LoginInfo(w.账号, w.密码), seed=seed)
                logger = build_agent_logger(base_dir=self.logs_dir, ctx=AgentLogContext(role="writer", account=w.账号, platform_id=platform_id))
                futures.append(ex.submit(self._writer_one, agent, logger, round_num, pol.clickbait_p))

            for fut in as_completed(futures):
                acct, article_id = fut.result()
                published[acct] = article_id
        return published

    def _writer_one(self, agent: WriterAgent, logger: logging.Logger, round_num: int, clickbait_p: float) -> Tuple[str, int]:
        try:
            agent.login_session()
            logger.info(round_banner(round_num, seed=agent.seed))
            is_cb = agent.rng.random() < float(clickbait_p)
            title_level = 5 if is_cb else 2
            relevance_level = 1 if is_cb else 4
            article_id = agent.publish_article(title_level=title_level, relevance_level=relevance_level)
            logger.info(f"publish_article ok article_id={article_id} clickbait={int(is_cb)} X={title_level} Y={relevance_level}")
            return agent.login.account, article_id
        except Exception as e:
            race_condition(logger, round_num=round_num, action="writer_publish", error=e)
            raise

    def _run_user_actions(
        self,
        *,
        round_num: int,
        rp: RoundPolicy,
        users: Sequence[UserAccount],
        published_article_ids: Dict[str, int],
    ) -> None:
        # 将文章按平台分桶，用户只浏览自身平台
        by_platform: Dict[int, List[int]] = {}
        from accounts.models import Article

        for a in Article.objects.filter(轮次=round_num).only("id", "写手账号"):
            # 用写手账号反查平台（避免在此处 join 大表）
            w = WriterAccount.objects.filter(账号=a.写手账号).only("所属平台").first()
            pid = int(getattr(w, "所属平台", 0)) if w else 0
            by_platform.setdefault(pid, []).append(int(a.pk))

        futures = []
        with ThreadPoolExecutor(max_workers=len(users)) as ex:
            for u in users:
                platform_id = int(getattr(u, "所属平台", 0))
                seed = self._seed_for(round_num=round_num, tag="user", account=u.账号)
                agent = UserAgent(login=LoginInfo(u.账号, u.密码), seed=seed)
                logger = build_agent_logger(base_dir=self.logs_dir, ctx=AgentLogContext(role="user", account=u.账号, platform_id=platform_id))
                articles = list(by_platform.get(platform_id) or [])
                futures.append(ex.submit(self._user_one, agent, logger, round_num, rp, platform_id, articles))
            for fut in as_completed(futures):
                fut.result()

    def _user_one(
        self,
        agent: UserAgent,
        logger: logging.Logger,
        round_num: int,
        rp: RoundPolicy,
        platform_id: int,
        article_ids: List[int],
    ) -> None:
        try:
            agent.login_session()
            logger.info(round_banner(round_num, seed=agent.seed))
            agent.browse_platform(platform_id=platform_id)
            if not article_ids:
                return
            agent.rng.shuffle(article_ids)
            n = max(0, min(self.cfg.user_reads_per_round, len(article_ids)))
            chosen = article_ids[:n]

            # 举报触发轮：仅对目标平台/文章提升举报概率
            report_override_p = None
            if rp.report_trigger and rp.report_trigger.enabled:
                report_override_p = rp.report_trigger.trigger_report_p

            probs = {
                "like_p": rp.user_interactions.like_p,
                "collect_p": rp.user_interactions.collect_p,
                "read_complete_p": rp.user_interactions.read_complete_p,
                "report_p": rp.user_interactions.report_p,
            }

            for aid in chosen:
                agent.click_article(article_id=aid)
                agent.maybe_interact(article_id=aid, probs=probs, report_override_p=report_override_p)
            logger.info(f"user_actions ok read={len(chosen)} articles_on_platform={len(article_ids)}")
        except Exception as e:
            race_condition(logger, round_num=round_num, action="user_actions", error=e, extra={"platform_id": platform_id})
            raise

    def _run_regulator_actions(self, *, round_num: int, rp: RoundPolicy, regulators: Sequence[RegulatorAccount]) -> None:
        reg = regulators[0]
        agent = RegulatorAgent(login=LoginInfo(reg.账号, reg.密码), seed=self._seed_for(round_num=round_num, tag="regulator", account=reg.账号))
        logger = build_agent_logger(base_dir=self.logs_dir, ctx=AgentLogContext(role="regulator", account=reg.账号))
        try:
            agent.login_session()
            logger.info(round_banner(round_num, seed=agent.seed))
            # 监管巡查：选择过去区间，满足接口约束 end_round < current_round
            if rp.regulator_patrol:
                target_platform = int(self.strategy.platform_ids[agent.rng.randrange(len(self.strategy.platform_ids))])
                start_r = max(1, round_num - 2)
                end_r = max(1, round_num - 1)
                agent.submit_patrol(platform_id=target_platform, start_round=start_r, end_round=end_r, ratio="0.50")
                logger.info(f"submit_patrol ok platform={target_platform} {start_r}-{end_r}")
            if rp.regulator_fine:
                target_platform = int(self.strategy.platform_ids[agent.rng.randrange(len(self.strategy.platform_ids))])
                tier = ["light", "basic", "medium", "strict"][agent.rng.randrange(4)]
                agent.submit_fine(platform_id=target_platform, fine_tier=tier)
                logger.info(f"submit_fine ok platform={target_platform} tier={tier}")
            if rp.regulator_special_action:
                # 选 1-2 个平台
                pids = list(self.strategy.platform_ids)
                agent.rng.shuffle(pids)
                chosen = pids[:2]
                duration = 8
                agent.submit_special_action(platform_ids=chosen, duration=duration, reason="定期整治")
                logger.info(f"submit_special_action ok platforms={chosen} duration={duration}")
        except Exception as e:
            race_condition(logger, round_num=round_num, action="regulator_actions", error=e)
            raise

