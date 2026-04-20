from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AgentLogContext:
    role: str
    account: str
    platform_id: Optional[int] = None


def build_agent_logger(*, base_dir: Path, ctx: AgentLogContext) -> logging.Logger:
    base_dir.mkdir(parents=True, exist_ok=True)
    name = f"mega_sim.{ctx.role}.{ctx.account}"
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 防止 pytest 多次收集/复用 logger 时重复添加 handler
    if getattr(logger, "_mega_sim_configured", False):
        return logger

    safe_platform = "na" if ctx.platform_id is None else str(ctx.platform_id)
    log_path = base_dir / f"{ctx.role}_{safe_platform}_{ctx.account}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    setattr(logger, "_mega_sim_configured", True)
    return logger


def round_banner(round_num: int, *, seed: int) -> str:
    return f"------------------- 当前为第{round_num}轮 (seed={seed}) -------------------"


def race_condition(
    logger: logging.Logger,
    *,
    round_num: int,
    action: str,
    error: BaseException,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"round": round_num, "action": action, "error_type": type(error).__name__, "error": str(error)}
    if extra:
        payload.update(extra)
    logger.error(f"RACE_CONDITION | {payload}")

