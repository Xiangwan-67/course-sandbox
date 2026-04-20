from __future__ import annotations

from pathlib import Path

import os
import pytest

from .accounts_loader import load_accounts_from_excel
from .orchestrator import MegaSimConfig, MegaSimOrchestrator


@pytest.mark.django_db(transaction=True)
def test_mega_sim_46_agents_100_rounds(tmp_path: Path):
    """
    大型自动化模拟：pytest 驱动 + 独立 sqlite 测试库（不污染 db.sqlite3）。
    """
    if os.environ.get("MEGA_SIM_RUN") != "1":
        pytest.skip("mega sim is opt-in; set MEGA_SIM_RUN=1 to execute 100 rounds")

    load_accounts_from_excel()
    work_dir = tmp_path / "mega_sim_artifacts"
    rounds = int(os.environ.get("MEGA_SIM_ROUNDS", "100"))
    seed = int(os.environ.get("MEGA_SIM_SEED", "20260420"))
    reads = int(os.environ.get("MEGA_SIM_USER_READS", "5"))
    cfg = MegaSimConfig(rounds=rounds, seed=seed, user_reads_per_round=reads)
    MegaSimOrchestrator(cfg=cfg, work_dir=work_dir).run()

