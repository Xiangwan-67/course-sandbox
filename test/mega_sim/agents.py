from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.test import Client
from django.db.utils import OperationalError


@dataclass(frozen=True)
class LoginInfo:
    account: str
    password: str


class BaseAgent:
    def __init__(self, *, login: LoginInfo, role: str, seed: int) -> None:
        self.login = login
        self.role = role
        self.seed = seed
        self.rng = random.Random(seed)
        self.client = Client()

    def login_session(self) -> None:
        r = self.client.post("/", {"account": self.login.account, "password": self.login.password})
        if r.status_code not in (200, 302):
            raise RuntimeError(f"login failed status={r.status_code}")

    def post_json_ok(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.client.post(path, data or {})
        try:
            payload = r.json()
        except Exception:
            raise RuntimeError(f"non-json response path={path} status={r.status_code} body={(r.content or b'')[:200]!r}")
        if r.status_code != 200 or not payload.get("ok", True) is True:
            raise RuntimeError(f"request failed path={path} status={r.status_code} payload={payload}")
        return payload

    def post_json_body_ok(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        r = self.client.post(path, body, content_type="application/json")
        try:
            data = r.json()
        except Exception:
            raise RuntimeError(f"non-json response path={path} status={r.status_code} body={(r.content or b'')[:200]!r}")
        if r.status_code != 200 or data.get("ok") is not True:
            raise RuntimeError(f"request failed path={path} status={r.status_code} payload={data}")
        return data

    def post_allow_400(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.client.post(path, data or {})
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": (r.content or b"")[:200].decode("utf-8", errors="replace")}
        payload["_status_code"] = r.status_code
        return payload


class WriterAgent(BaseAgent):
    def __init__(self, *, login: LoginInfo, seed: int) -> None:
        super().__init__(login=login, role="writer", seed=seed)

    def publish_article(self, *, title_level: int, relevance_level: int) -> int:
        """
        跳过 LLM 生成，直接走：
        /writer/start-article/ -> /writer/select-title/ -> /writer/select-body/
        """
        r = self.post_json_ok("/writer/start-article/")
        article_id = int(r["article_id"])
        title_text = f"mega_sim_title_{self.login.account}_{article_id}"
        body_text = f"mega_sim_body_{self.login.account}_{article_id}"
        self.post_json_ok(
            "/writer/select-title/",
            {"title_text": title_text, "position": 1, "title_exaggeration_level": int(title_level)},
        )
        self.post_json_ok(
            "/writer/select-body/",
            {"body_text": body_text, "position": 1, "content_relevance_level": int(relevance_level)},
        )
        return article_id


class UserAgent(BaseAgent):
    def __init__(self, *, login: LoginInfo, seed: int) -> None:
        super().__init__(login=login, role="user", seed=seed)

    def browse_platform(self, *, platform_id: int) -> None:
        for i in range(8):
            try:
                r = self.client.get(f"/user/browse/{int(platform_id)}/")
                if r.status_code == 200:
                    return
                if r.status_code == 500 and b"locked" in (r.content or b"").lower():
                    time.sleep(0.1 * (i + 1))
                    continue
                raise RuntimeError(f"browse failed status={r.status_code}")
                return
            except OperationalError as e:
                # sqlite 并发读写锁：按要求记录为竞态并重试（最终仍可能失败并停机）
                if "locked" not in str(e).lower():
                    raise
                time.sleep(0.1 * (i + 1))
        raise RuntimeError("browse failed after retries due to sqlite lock")

    def click_article(self, *, article_id: int) -> None:
        for i in range(12):
            try:
                r = self.client.get(f"/user/article/{int(article_id)}/")
                if r.status_code == 200:
                    return
                if r.status_code == 500 and b"locked" in (r.content or b"").lower():
                    time.sleep(0.1 * (i + 1))
                    continue
                raise RuntimeError(f"view article failed status={r.status_code}")
            except OperationalError as e:
                if "locked" not in str(e).lower():
                    raise
                time.sleep(0.1 * (i + 1))
        raise RuntimeError("view article failed after retries due to sqlite lock")

    def maybe_interact(self, *, article_id: int, probs: Dict[str, float], report_override_p: Optional[float] = None) -> None:
        # like/collect/read_complete
        if self.rng.random() < float(probs.get("like_p", 0.0)):
            self.post_json_ok(f"/user/article/{article_id}/like/")
        if self.rng.random() < float(probs.get("collect_p", 0.0)):
            self.post_json_ok(f"/user/article/{article_id}/collect/")
        if self.rng.random() < float(probs.get("read_complete_p", 0.0)):
            self.post_json_ok(f"/user/article/{article_id}/read-complete/")

        # report
        rp = float(probs.get("report_p", 0.0))
        if report_override_p is not None:
            rp = float(report_override_p)
        if self.rng.random() < rp:
            payload = self.post_allow_400(f"/user/article/{article_id}/report/")
            # 重复举报会返回 400，属于预期异常覆盖之一
            if payload.get("_status_code") not in (200, 400):
                raise RuntimeError(f"report unexpected status payload={payload}")


class PlatformAgent(BaseAgent):
    def __init__(self, *, login: LoginInfo, seed: int) -> None:
        super().__init__(login=login, role="platform", seed=seed)

    def submit_governance_configs(self, *, flow: str) -> None:
        """
        只负责“提交配置”的动作，审批由自动化通过 ORM 模拟完成。
        flow=normal: clickbait -> (report optional) -> health -> traffic -> revenue
        flow=abnormal: try penalties first, omit clickbait/report
        """
        flow = (flow or "normal").strip()
        if flow not in ("normal", "abnormal"):
            flow = "normal"

        if flow == "normal":
            self.post_allow_400("/platform/governance/report/save/", {"threshold": "0.30", "review_method": "auto"})
            self.post_allow_400("/platform/governance/traffic-penalty/save/", {"alpha": "0.50"})
            self.post_allow_400("/platform/governance/revenue-penalty/save/", {"beta": "0.50"})
            # 健康分配置/发布接口在 views 里，但 urls 里未暴露独立配置页；这里先不走 HTTP，后续由 ORM 模拟生效记录
            return

        # abnormal
        self.post_allow_400("/platform/governance/traffic-penalty/save/", {"alpha": "0.50"})
        self.post_allow_400("/platform/governance/revenue-penalty/save/", {"beta": "0.50"})

    def publish_governance_measures(self, *, flow: str) -> None:
        """
        发布治理措施（配置需已是 active）。发布后会生成 PlatformGovernanceMeasure(status=pending, 生效轮次=当前+1)。
        """
        flow = (flow or "normal").strip()
        if flow not in ("normal", "abnormal"):
            flow = "normal"

        if flow == "normal":
            # clickbait_detection：平台侧无法配置参数，但可发布（需已有 active 配置）
            self.post_allow_400("/platform/governance/publish/", {"measure_type": "clickbait_detection"})
            self.post_allow_400("/platform/governance/publish/", {"measure_type": "user_report"})
            self.post_allow_400("/platform/governance/publish/", {"measure_type": "traffic_penalty"})
            self.post_allow_400("/platform/governance/publish/", {"measure_type": "revenue_penalty"})
            return

        self.post_allow_400("/platform/governance/publish/", {"measure_type": "traffic_penalty"})
        self.post_allow_400("/platform/governance/publish/", {"measure_type": "revenue_penalty"})


class RegulatorAgent(BaseAgent):
    def __init__(self, *, login: LoginInfo, seed: int) -> None:
        super().__init__(login=login, role="regulator", seed=seed)

    def submit_patrol(self, *, platform_id: int, start_round: int, end_round: int, ratio: str = "0.50") -> None:
        self.post_json_body_ok(
            "/regulator/platform-patrol/submit/",
            {"platform_id": int(platform_id), "patrol_ratio": ratio, "start_round": int(start_round), "end_round": int(end_round)},
        )

    def submit_fine(self, *, platform_id: int, fine_tier: str) -> None:
        self.post_json_body_ok("/regulator/fine/submit/", {"platform_id": int(platform_id), "fine_tier": fine_tier})

    def submit_special_action(self, *, platform_ids: list[int], duration: int, reason: str = "定期整治") -> None:
        self.post_json_body_ok(
            "/regulator/special-action/submit/",
            {"platform_ids": platform_ids, "duration_rounds": int(duration), "reason": reason},
        )


class AdminAgent(BaseAgent):
    def __init__(self, *, login: LoginInfo, seed: int) -> None:
        super().__init__(login=login, role="admin", seed=seed)

    def end_round(self) -> Dict[str, Any]:
        return self.post_json_ok("/end-round/", {})

