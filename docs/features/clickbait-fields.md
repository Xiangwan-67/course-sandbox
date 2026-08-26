# 标题党：文章表字段与检测结果表（审计）

**最后更新：** 2026-05-21

---

## Article（发布状态与当前结论）

| 字段 | 说明 |
|------|------|
| `is_clickbait` | 当前是否标题党：`True` / `False` / `None`（未判定） |
| `clickbait_source`（检测来源） | 当前结论来源：**仅** `auto` / `user_report`；**最新一次** auto 或 user_report 判定会**覆盖** |
| `clickbait_auto_executed` | 发文时是否执行过标题党**自动检测**（治理包 `clickbait_detection` 生效且落库）；`True`/`False`，默认 `False`；**举报、巡查不改** |
| `is_published` | 是否完成最终正文提交、推送与流量记录；巡查只抽样已发布文章 |

巡查、监管抽查只处理 `is_published=True` 的文章；**不写入** `clickbait_source` / `clickbait_auto_executed`，也不改 `is_clickbait`。

已移除字段（勿再使用）：`clickbait_detected_at`、`auto_rule_executed`、`method_auto_rule`、`method_user`。

---

## ClickbaitDetectionResult（审计，全量事件）

每条记录 = 一次判定（`检测结果` 可为 True 或 False）。

| `判定来源` | 何时写入 | 是否更新 Article |
|------------|----------|------------------|
| `auto` | 发文且标题党检测治理包生效 | 是：覆盖 `is_clickbait`、`clickbait_source=auto` |
| `user_report` | 结束本轮举报达阈值处理 | 是：覆盖 `is_clickbait`、`clickbait_source=user_report` |
| `patrol` | 平台/监管巡查抽样（每篇抽中文章一条） | **否** |

同篇文章可有多条审计记录（不同轮次、不同来源）。

---

## 四路径与 Article 变化（简表）

| 路径 | 标题党 | 非标题党 | Article |
|------|--------|----------|---------|
| 自动检测 | 审计 + `is_clickbait=True`, `source=auto`, `clickbait_auto_executed=True` | 审计 + `is_clickbait=False`, `source=auto`, `clickbait_auto_executed=True` | 更新 |
| 用户举报达阈值 | 审计 + 覆盖 `source=user_report` | 同上 | 更新结论与来源；**不改** `clickbait_auto_executed` |
| 平台/监管巡查 | 审计 `patrol`，`检测结果=True` | 审计 `patrol`，`检测结果=False` | **不更新** |

实现：`accounts/clickbait_judge.py` → `record_clickbait_judgment`。
