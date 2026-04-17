from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "test"
REPORTS_DIR = TEST_DIR / "reports"


def _run_pytest() -> int:
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "sandbox_site.settings")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    junit_path = REPORTS_DIR / "junit.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(TEST_DIR / "pytest.ini"),
        str(TEST_DIR / "tests"),
        f"--junitxml={junit_path}",
    ]
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True, capture_output=True)
    (REPORTS_DIR / "pytest_stdout.txt").write_text(p.stdout or "", encoding="utf-8")
    (REPORTS_DIR / "pytest_stderr.txt").write_text(p.stderr or "", encoding="utf-8")
    return p.returncode


def _parse_junit_results(junit_path: Path) -> tuple[int, int, int]:
    if not junit_path.exists():
        return 0, 0, 0
    try:
        text = junit_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0, 0
    # pytest 生成的 junit 一般是单 testsuite，属性顺序不固定；逐个提取更稳
    def _attr(name: str) -> int | None:
        m = re.search(rf'{name}="(\d+)"', text)
        return int(m.group(1)) if m else None

    tests = _attr("tests") or 0
    failures = _attr("failures") or 0
    errors = _attr("errors") or 0
    return tests, failures, errors


def _extract_failure_summary(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("E   ") or line.startswith("FAILED "):
            out.append(line.strip())
            continue
        if ("AssertionError" in line) or (
            ("Error" in line) and ("Traceback" in "\n".join(lines[max(0, i - 8) : i]))
        ):
            # keep short; user can open full stdout
            if line.strip():
                out.append(line.strip())
    # de-duplicate while keeping order
    dedup: list[str] = []
    seen = set()
    for s in out:
        if s not in seen:
            dedup.append(s)
            seen.add(s)
    return dedup[:30]


def _write_report(exit_code: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    junit_path = REPORTS_DIR / "junit.xml"
    stdout_path = REPORTS_DIR / "pytest_stdout.txt"
    stderr_path = REPORTS_DIR / "pytest_stderr.txt"

    total, failures, errors = _parse_junit_results(junit_path)
    passed = max(0, total - failures - errors)

    stdout = ""
    try:
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        stdout = ""

    failure_hints = _extract_failure_summary(stdout)
    hint_counter = Counter()
    for h in failure_hints:
        hl = h.lower()
        if "database is locked" in hl or "locked" in hl and "database" in hl:
            hint_counter["sqlite 并发锁：建议保证测试库隔离/WAL/拉长 timeout/拆分写事务"] += 1
        if "csrf" in hl or "403" in hl:
            hint_counter["HTTP 403/CSRF：检查测试 client 是否带 session/csrfmiddleware 行为"] += 1
        if "transaction" in hl and "atomic" in hl:
            hint_counter["数据库事务：可能需要在失败后用新 client 或检查 sqlite 连接回滚状态"] += 1

    lines: list[str] = []
    lines.append("# 标题党检测自动化测试报告")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 结果：{'通过' if exit_code == 0 else '失败'}（pytest exit_code={exit_code}）")
    lines.append(f"- 用例统计（来自 junit.xml）：total={total}, passed≈{passed}, failures={failures}, errors={errors}")
    lines.append("")
    lines.append("## 产物路径")
    lines.append("")
    lines.append(f"- pytest 标准输出：`{stdout_path.relative_to(ROOT)}`")
    lines.append(f"- pytest 错误输出：`{stderr_path.relative_to(ROOT)}`")
    lines.append(f"- JUnit XML：`{junit_path.relative_to(ROOT)}`")
    lines.append(f"- 日志摘录：`{(REPORTS_DIR / 'log_excerpt.txt').relative_to(ROOT)}`（如生成）")
    lines.append("")
    lines.append("## 失败摘要（自动抽取，可能不完整）")
    lines.append("")
    if exit_code == 0:
        lines.append("- 无")
    else:
        if failure_hints:
            for s in failure_hints:
                lines.append(f"- {s}")
        else:
            lines.append("- 未能从 stdout 自动抽取失败行；请直接打开 `pytest_stdout.txt`。")
        lines.append("")
        lines.append("## 改进建议（启发式）")
        lines.append("")
        if hint_counter:
            for k, v in hint_counter.most_common():
                lines.append(f"- **{k}**（命中 {v} 次）")
        else:
            lines.append("- 依据失败栈定位具体断言/接口；若是偶现锁问题，可重跑 `python test/run.py` 对比。")

    (REPORTS_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    excerpt_path = REPORTS_DIR / "log_excerpt.txt"
    index_path = REPORTS_DIR / "action_log_paths.txt"
    excerpt_chunks: list[str] = []
    if index_path.exists():
        try:
            raw_paths = [
                p.strip()
                for p in index_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if p.strip()
            ]
        except OSError:
            raw_paths = []

        seen = set()
        for p in raw_paths:
            if p in seen:
                continue
            seen.add(p)
            try:
                lp = Path(p)
                if not lp.exists():
                    continue
                text = lp.read_text(encoding="utf-8", errors="replace")
                tail = "\n".join(text.splitlines()[-120:])
                excerpt_chunks.append(f"===== {p} (tail) =====\n{tail}\n")
            except OSError:
                continue

    if excerpt_chunks:
        excerpt_path.write_text("\n".join(excerpt_chunks) + "\n", encoding="utf-8")
    else:
        excerpt_path.write_text(
            "说明：未收集到日志路径索引（`test/reports/action_log_paths.txt`）。\n",
            encoding="utf-8",
        )


def main() -> int:
    exit_code = _run_pytest()
    _write_report(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
