# 平台治理包

**最后更新：** 2026-05-21

---

## 1. 用途

平台负责人配置并**申请发布**各类治理措施；管理员在运营台审批后，在指定**生效轮次**对写手发文、推送、结算产生约束。

---

## 2. 触发链

```
platform/governance/              platform_governance          展示措施列表与发布状态
  → POST governance/publish/      platform_governance_publish  提交发布（pending）
  → POST governance/cancel/       platform_governance_cancel   申请取消
  → 子页 */save/                  platform_*_save              保存各 Config（部分需先配置再发布）
Admin /admin/sandbox-ops/         审批 → status active
结束本轮 perform_end_round        生效轮次 == new_round 时投递通知等
写手 select-body                  is_clickbait / 健康分 / 推送 α 读取生效措施
结束本轮                          _process_article_reports / _settle_article_revenue 等
```

---

## 3. 核心符号

| 类型 | 名称 |
|------|------|
| 视图 | `platform_governance`, `platform_governance_publish`, `platform_governance_cancel`, `platform_clickbait_detection(_save)`, `platform_traffic_penalty(_save)`, `platform_report(_save)`, `platform_revenue_penalty(_save)`, `platform_performance_*` |
| 判定 | `_get_effective_governance_measure`, `_config_snapshot_active`, `_measure_published_for_ui`, `is_clickbait` |
| 模型 | `PlatformGovernanceMeasure`, `ClickbaitDetectionConfig`, `TrafficPenaltyConfig`, `UserReportConfig`, `RevenuePenaltyConfig`, `AccountHealthConfig`, `AccountHealthLevelConfig`, `PlatformPerformanceScheme` |
| 通知 | `governance_notices.dispatch_governance_notices_for_round`, `create_inbox_rows_for_measure` |
| 审批 | `accounts/approval_actions.py` |

---

## 4. 业务规则（当前真相）

### 4.1 措施类型（`measure_type`）

| type | 名称 | 平台侧配置 | 主要影响 |
|------|------|------------|----------|
| `account_health_rule` | 账号健康分规则 | 档位在治理页展示；参数在 Admin | 标题党扣分、推流系数；写手通知收件箱 |
| `clickbait_detection` | 标题党检测 | 开关为主，阈值 Admin | `writer_select_body` 内 `is_clickbait` |
| `user_report` | 用户举报 | 需先 save 配置再发布 | 用户举报；结束本轮 `_process_article_reports` |
| `traffic_penalty` | 流量惩罚 | 降权系数 α | `_do_article_push` 发现列表抽样 |
| `revenue_penalty` | 收益惩罚 | 系数 β | `_settle_article_revenue` |
| `performance_rule` | 绩效规则 | `platform_performance` 流程 | 收益权重 w1～w3 |

### 4.2 发布与生效

- 平台 `publish` 创建 `PlatformGovernanceMeasure`，通常 `status=pending`，`生效轮次` 多为 **当前轮+1**（见 `platform_governance_publish`）。
- Admin 批准后 `active`；在 `生效轮次` 到达时参与 `_get_effective_governance_measure(platform_id, measure_type, round_num)`。
- 同类型已有 pending/active 且未安排取消时，不可重复提交发布。

### 4.3 标题党判定与追溯

详见 [clickbait-fields.md](clickbait-fields.md)。

- **Article**：仅 `is_clickbait` + `clickbait_source`（检测来源，最新 auto/user_report 覆盖）。
- **ClickbaitDetectionResult**：三种 `判定来源`（`auto` / `user_report` / `patrol`）全量审计，True/False 均记录；仅前两者更新 Article。

`is_clickbait()` 仍要求标题党检测治理包生效；举报/巡查判定口径用 `judge_clickbait_by_config`。

### 4.4 写手通知

- **仅** `account_health_rule` 在生效轮次向该平台全体写手写 `WriterGovernanceNotice`（`governance_notices`）。
- 轮次切换时 `dispatch_governance_notices_for_round(new_round)` 并可能 `_sync_writer_push_ratios_for_account_health_platform`。

---

## 5. 平台 / 轮次依赖

- 所有 Config / Measure 均带 **平台编号**（`platform_id` 或 `平台`）。
- 生效判断使用 **文章发布轮次** 或 **结算轮次** 与 `PlatformGovernanceMeasure.生效轮次`、`status` 组合。
- 改阈值或措施逻辑时，同步检查 `is_clickbait`、`_do_article_push`、`_settle_article_revenue`、`_process_article_reports`。

---

## 6. 相关测试

- `test/tests/test_clickbait_detection.py`
- `test/tests/test_traffic_penalty.py`
- `test/tests/test_revenue_penalty.py`
- `test/tests/test_user_report_detection.py`
- `test/tests/test_platform_performance_scheme.py`
- `test/tests/test_account_health_score.py`
- `test/tests/test_writer_notices_health_only.py`

---

## 7. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-21 | 判定事件表扩展；Article.clickbait_source 仅 auto/user_report |
| 2026-05-21 | 初版文档 |
