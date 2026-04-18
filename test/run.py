from __future__ import annotations

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "test"
REPORTS_DIR = TEST_DIR / "reports"


CASE_DISPLAY_MAP = {
    "test_traffic_penalty_config_page_and_save_success": "平台负责人提交流量惩罚配置，系统保存待审核配置",
    "test_traffic_penalty_save_duplicate_rejected": "平台负责人重复提交流量惩罚配置被拦截",
    "test_traffic_penalty_publish_requires_approved_config": "平台负责人未有可用配置时提交发布被拒绝",
    "test_traffic_penalty_publish_next_round_effective": "平台负责人发布后下一轮生效，写手标题党文章命中惩罚",
    "test_traffic_penalty_not_applied_for_non_clickbait": "写手发布非标题党文章，不应触发流量惩罚",
    "test_traffic_penalty_cancel_next_round_disabled": "平台负责人取消流量惩罚后下一轮失效",
    "test_traffic_penalty_alpha_boundaries[0.00-expected_penalty0-0]": "alpha=0 边界：标题党文章发现流量降至最低边界",
    "test_traffic_penalty_alpha_boundaries[1.00-expected_penalty1-None]": "alpha=1 边界：标题党文章不额外降权",
    "test_traffic_penalty_invalid_alpha_and_permission": "非法参数与权限异常：默认值兜底且无权访问被拒绝",
    "test_traffic_penalty_with_health_rule_records_gamma": "流量惩罚与健康分联动：gamma 与惩罚记录一致",
    "test_traffic_penalty_round_result_matches_database": "平台查看治理结果页：受流量惩罚文章数与数据库一致",
    "test_revenue_penalty_config_page_and_save_success": "平台负责人提交收益惩罚配置，系统保存待审核配置",
    "test_revenue_penalty_save_duplicate_rejected": "平台负责人重复提交收益惩罚配置被拦截",
    "test_revenue_penalty_publish_requires_approved_config": "平台负责人未有可用收益惩罚配置时提交发布被拒绝",
    "test_revenue_penalty_publish_next_round_effective": "平台负责人发布收益惩罚后下一轮生效，标题党文章命中收益惩罚",
    "test_revenue_penalty_not_applied_for_non_clickbait": "非标题党文章结算时不应触发收益惩罚",
    "test_revenue_penalty_cancel_next_round_disabled": "平台负责人取消收益惩罚后下一轮失效",
    "test_revenue_penalty_beta_zero_boundary": "beta=0 边界：标题党文章最终收益归零",
    "test_revenue_penalty_beta_one_boundary": "beta=1 边界：标题党文章不额外扣减收益",
    "test_revenue_penalty_invalid_beta_and_permission": "收益惩罚非法参数与权限异常：默认值兜底且无权访问被拒绝",
    "test_revenue_penalty_round_result_matches_database": "平台查看治理结果页：受收益惩罚文章数与数据库一致",
    "test_revenue_penalty_settlement_log_contains_required_fields": "收益结算日志完整性：关键字段齐全且可对账",
    "test_health_levels_render_from_global_default_table": "平台治理页展示账号健康分档位时，可读取无平台编号默认档位",
    "test_account_health_publish_requires_submitted_config": "平台负责人未提交健康分配置时提交发布被拦截",
    "test_account_health_publish_next_round_effective_and_deducts": "平台发布账号健康分规则后下一轮生效，标题党文章命中扣分并更新档位",
    "test_non_clickbait_does_not_change_health_score": "非标题党文章不触发健康分扣减",
    "test_account_health_cancel_next_round_disabled": "平台取消账号健康分规则后下一轮失效",
    "test_health_recovery_updates_score_and_log": "健康分恢复机制生效后可自动恢复并记录日志",
    "test_health_recovery_not_run_when_measure_not_effective": "账号健康分治理措施未生效时，不执行健康分恢复",
    "test_health_deduction_floor_at_zero": "健康分扣减下限为0，不出现负分",
    "test_account_health_publish_permission_denied": "非平台角色提交账号健康分发布被拒绝",
}


def _run_pytest() -> tuple[int, bool]:
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "sandbox_site.settings")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    junit_path = REPORTS_DIR / "junit.xml"
    try:
        junit_path.unlink(missing_ok=True)
    except OSError:
        pass

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
    junit_generated = junit_path.exists()
    return p.returncode, junit_generated


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


def _parse_junit_cases(junit_path: Path) -> list[dict]:
    if not junit_path.exists():
        return []
    try:
        tree = ET.parse(junit_path)
    except Exception:
        return []

    root = tree.getroot()
    cases: list[dict] = []
    for tc in root.iter("testcase"):
        name = tc.attrib.get("name", "")
        classname = tc.attrib.get("classname", "")
        time_cost = tc.attrib.get("time", "0")
        status = "passed"
        reason = ""
        detail = ""
        node = None
        for tag in ("failure", "error", "skipped"):
            node = tc.find(tag)
            if node is not None:
                status = "failed" if tag in ("failure", "error") else "skipped"
                reason = (node.attrib.get("message") or "").strip()
                detail = (node.text or "").strip()
                break
        if not reason and detail:
            reason = detail.splitlines()[0].strip()
        if not reason:
            reason = "—"
        cases.append(
            {
                "name": name,
                "display_name": CASE_DISPLAY_MAP.get(name, name),
                "classname": classname,
                "time": time_cost,
                "status": status,
                "reason": reason,
                "detail": detail,
            }
        )
    return cases


def _write_report(exit_code: int, junit_generated: bool) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    junit_path = REPORTS_DIR / "junit.xml"
    stdout_path = REPORTS_DIR / "pytest_stdout.txt"
    stderr_path = REPORTS_DIR / "pytest_stderr.txt"

    if junit_generated:
        total, failures, errors = _parse_junit_results(junit_path)
        case_rows = _parse_junit_cases(junit_path)
    else:
        total, failures, errors = 0, 0, 0
        case_rows = []
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
    lines.append("# 平台治理自动化测试报告（标题党检测 + 用户举报 + 流量惩罚）")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 结果：{'通过' if exit_code == 0 else '失败'}（pytest exit_code={exit_code}）")
    if junit_generated:
        lines.append(f"- 用例统计（来自 junit.xml）：total={total}, passed≈{passed}, failures={failures}, errors={errors}")
    else:
        lines.append("- 用例统计：本次未生成 `junit.xml`（通常是 pytest 未成功启动或提前失败）")
    lines.append("")
    lines.append("## 产物路径")
    lines.append("")
    lines.append(f"- pytest 标准输出：`{stdout_path.relative_to(ROOT)}`")
    lines.append(f"- pytest 错误输出：`{stderr_path.relative_to(ROOT)}`")
    lines.append(f"- JUnit XML：`{junit_path.relative_to(ROOT)}`")
    lines.append(f"- 日志摘录：`{(REPORTS_DIR / 'log_excerpt.txt').relative_to(ROOT)}`（如生成）")
    lines.append("")
    lines.append("## 业务用例逐项结果")
    lines.append("")
    if case_rows:
        for idx, row in enumerate(case_rows, start=1):
            status_cn = "通过" if row["status"] == "passed" else ("失败" if row["status"] == "failed" else "跳过")
            lines.append(f"### 用例 {idx}")
            lines.append(f"- 业务口径：{row['display_name']}")
            lines.append(f"- pytest用例：`{row['classname']}::{row['name']}`")
            lines.append(f"- 检测结果：{status_cn}")
            lines.append(f"- 耗时（秒）：{row['time']}")
            if row["status"] == "failed":
                lines.append(f"- 问题原因：{row['reason']}")
            else:
                lines.append("- 问题原因：—")
            lines.append("")
    else:
        lines.append("- 未解析到本次用例明细，请检查 `pytest_stderr.txt` 与运行环境。")
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
    exit_code, junit_generated = _run_pytest()
    _write_report(exit_code, junit_generated)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
