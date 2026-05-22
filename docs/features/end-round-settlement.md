# 结束本轮与结算

**最后更新：** 2026-05-21

---

## 1. 用途

在用户阶段结束后，按**每个平台**结算本轮文章收益、处理举报、恢复写手健康分，必要时结算周期利润，然后将 **模拟轮次 +1**，并触发治理通知与监管自动巡查。

---

## 2. 触发链

```
POST /end-round/              end_round                 JSON 返回 new_round、结算摘要
manage.py end_round           Command                   调用同一 perform_end_round()
Admin 运营台                  （可选）                   同上

perform_end_round()           accounts/round_ops.py
  对每个 platform_id in valid_platform_ids():
    _recover_writer_health_for_platform
    _process_article_reports
    _settle_article_revenue
    （若命中周期）_settle_cycle_profit
  capture_round_snapshot(round_to_settle)   # 轮次快照，见 §4.5
  SimulationRound 当前轮次 += 1
  dispatch_governance_notices_for_round(new_round)
  _run_regulation_auto_patrols_for_round_transition(old, new)
```

---

## 3. 核心符号

| 类型 | 名称 |
|------|------|
| HTTP | `end_round` |
| 核心 | `perform_end_round`（`round_ops.py`） |
| 结算 | `_settle_article_revenue`, `_settle_cycle_profit`, `_process_article_reports`, `_recover_writer_health_for_platform` |
| 配置 | `_get_effective_profit_config`, `ProfitWeightConfig`, `writing_cost.get_writing_cost_value_for_relevance` |
| 轮次 | `SimulationRound`, `_get_current_round` |
| 轮次快照 | `capture_round_snapshot`（`accounts/round_snapshot.py`） |
| 监管 | `_run_regulation_auto_patrols_for_round_transition` |

---

## 4. 业务规则（当前真相）

### 4.1 不删数据

- 结束本轮**不删除**文章、推送、互动记录。
- 用户浏览只查 `文章__轮次=current_round`，故轮次 +1 后列表等效清空。

### 4.2 每平台结算顺序（`perform_end_round`）

1. `_recover_writer_health_for_platform` — 健康分恢复规则  
2. `_process_article_reports` — 用户举报达阈值后的处理（依赖 `user_report` 治理包）  
3. `_settle_article_revenue` — 单篇报酬：绩效权重、写作成本扣除、收益惩罚 β 等，写 `ArticleRevenueSettlement`，更新 `Article.报酬`  
4. 若 `round_to_settle % 利润展示窗口轮数 == 0` → `_settle_cycle_profit` → `PlatformCycleProfitRecord`

### 4.3 轮次递增后

- `dispatch_governance_notices_for_round(new_round)` — 账号健康分措施收件箱  
- `_run_regulation_auto_patrols_for_round_transition` — 专项整治结束后的配套自动巡查

### 4.4 调用方

- 通常由管理员或脚本在用户退出后调用；返回 JSON：`current_round`, `settled_revenue`, `settled_cycle_profit`。

### 4.5 轮次快照（`round_to_settle`）

在轮次 +1 **之前**，`capture_round_snapshot(round_to_settle)` 写入四张表（同轮先删后写，幂等）：

| 表 | 粒度 | 主要内容 |
|----|------|----------|
| `轮次快照批次` | 每轮 1 行 | `round_num`, `captured_at`, `trigger` |
| `轮次快照_平台` | 每轮 × 平台 | 用户数；`clickbait_count_article_field`（`is_clickbait=True`）；`clickbait_count_by_rule`（X/Y 规则重算）；周期利润 FK（仅周期末） |
| `轮次快照_写手` | 每轮 × 写手 | 粉丝数；本轮收益/收益惩罚；流量惩罚篇数；健康分/档位/推流系数 |
| `轮次快照_写手粉丝` | 每轮 × 关注关系 | `writer_account`, `user_account` |

用于按轮趋势分析；文章级明细仍查 `文章收益结算` / `文章流量记录`。

---

## 5. 平台 / 轮次依赖

- 外层循环 **`for pid in valid_platform_ids()`**，任何新增结算逻辑须按平台隔离。
- 收益/举报/治理生效均依赖 **被结算的轮次** `round_to_settle` 与各平台 `PlatformGovernanceMeasure`。

---

## 6. 相关测试

- `test/tests/test_revenue_penalty.py`
- `test/tests/test_user_report_detection.py`
- `test/tests/test_account_health_recovery_cap.py`
- `test/mega_sim/test_mega_simulation.py`

---

## 7. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-21 | 初版文档 |
