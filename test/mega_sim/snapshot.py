from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.db import connection as default_connection


@dataclass(frozen=True)
class SnapshotInfo:
    round_num: int
    pre_path: Path


def snapshot_db_pre_round(*, round_num: int, snapshot_dir: Path) -> SnapshotInfo:
    """
    pytest 下默认 DB 为 sqlite 文件（见 test/conftest.py）。
    每轮开始前复制该文件，作为可复盘的 round_<N>_pre.sqlite3。
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    db_name = settings.DATABASES["default"]["NAME"]
    dst = snapshot_dir / f"round_{round_num:03d}_pre.sqlite3"

    src = Path(str(db_name))
    if src.exists():
        # 文件库：直接复制
        connections.close_all()
        shutil.copy2(src, dst)
        return SnapshotInfo(round_num=round_num, pre_path=dst)

    # 内存库（pytest-django 在 sqlite 下可能使用 shared memory URI）
    if default_connection.vendor != "sqlite":
        raise RuntimeError(f"snapshot only supports sqlite in this harness; got vendor={default_connection.vendor}")

    # 尽量关闭非默认连接，避免并发线程持有连接
    connections.close_all()
    # 强制建立默认连接（若尚未连接）
    default_connection.ensure_connection()
    raw = default_connection.connection
    if raw is None:
        raise RuntimeError("sqlite raw connection not available")

    import sqlite3

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst_conn = sqlite3.connect(str(dst))
    try:
        raw.backup(dst_conn)  # type: ignore[attr-defined]
    finally:
        dst_conn.close()
    return SnapshotInfo(round_num=round_num, pre_path=dst)

