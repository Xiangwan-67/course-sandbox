# 监管端

**最后更新：** 2026-05-21

---

## 1. 用途

监管机构账号在辖区内发起**专项整治**、**平台巡查**、**罚款**等申请；管理员审批后落库执行；专项整治结束后可触发自动巡查与平台抽查占位。

---

## 2. 触发链

```
/regulator/                           regulator_home
/regulator/special-action/            regulator_special_action
  → POST special-action/submit/       regulator_special_action_submit   RegulationActionApplication
/regulator/platform-patrol/           regulator_platform_patrol
  → POST platform-patrol/submit/        regulator_platform_patrol_submit  PlatformPatrolApplication
/regulator/fine/submit/               regulator_fine_submit             RegulatorFineApplication
/regulator/platform-spot-check/<pk>/  platform_spot_check_detail        抽查结果查看

Admin sandbox-ops 审批 → RegulationAction / PlatformPatrolResult / RegulatorFineRecord 等

结束本轮 perform_end_round → _run_regulation_auto_patrols_for_round_transition
```

---

## 3. 核心符号

| 类型 | 名称 |
|------|------|
| 视图 | `regulator_home`, `regulator_special_action(_submit)`, `regulator_platform_patrol(_submit)`, `regulator_fine_submit`, `platform_spot_check_open`, `platform_spot_check_detail` |
| 辖区 | `platform_scope.jurisdiction_for_regulator_account`, `validate_regulator_platform_list` |
| 模型 | `RegulatorAccount`, `RegulationActionApplication`, `RegulationAction`, `PlatformSpotCheckResult`, `PlatformPatrolApplication`, `PlatformPatrolResult`, `RegulatorFineApplication`, `RegulatorFineRecord` |
| 巡查执行 | `_run_platform_patrol_core`, `_run_regulation_auto_patrol_pair`, `_execute_platform_patrol` |
| 同步 | `_sync_regulation_actions_finished`, `_is_platform_under_regulation` |

---

## 4. 业务规则（当前真相）

### 4.1 辖区

- `RegulatorAccount.负责平台编号列表` 定义可见/可操作平台；须与 `SANDBOX_PLATFORMS` 合法 ID 一致且**辖区互斥**（Admin/导入校验，`validate_regulator_platform_list`）。
- UI 与提交应拒绝辖区外 `platform_id`。

### 4.2 专项整治

- 申请 → `RegulationActionApplication`（pending）→ 审批通过 → 每平台一条 `RegulationAction`（`active`，含开始/结束轮次）。
- 整治期间 `_is_platform_under_regulation` 影响平台侧能力（见 `views` 内平台首页逻辑）。
- 专项整治结束后：`配套自动巡查已执行` 标记；结束本轮时 `_run_regulation_auto_patrols_for_round_transition` 可跑**两次**配套巡查并写 `PlatformPatrolResult`。
- `PlatformSpotCheckResult` 与专项行动一对一，供抽查页「是否查看」。

### 4.3 平台巡查

- 监管手动申请：`PlatformPatrolApplication` → 审批 → `_execute_platform_patrol`。
- 平台自查：`PlatformSelfPatrolApplication` / `PlatformSelfPatrolResult`（路由在 `platform/platform-patrol/`）。
- 巡查比例等来自申请单与 `AdminBaseConfig.自动巡查比例`（自动巡查时）。
- **标题党率**由 `_compute_platform_patrol_metrics` 统计；抽样范围仅包含 `Article.is_published=True` 的有效发布文章；抽中文章均写 `ClickbaitDetectionResult(判定来源=patrol)`（True/False 全量），**不修改** Article 的 `is_clickbait` / `clickbait_source`。见 [clickbait-fields.md](clickbait-fields.md)。

### 4.4 罚款

- `regulator_fine_submit` 提交 `RegulatorFineApplication`；审批后 `RegulatorFineRecord`；结算时 `_supervision_cost_from_regulatory_fines` 等计入平台成本（见 `views` 周期利润逻辑）。

---

## 5. 平台 / 轮次依赖

- 所有申请/记录带 **平台编号** 与 **轮次** 字段。
- 自动巡查绑定 **轮次切换** 与 `RegulationAction` 状态。

---

## 6. 相关测试

- `test/tests/test_regulator_special_action.py`
- `test/tests/test_platform_self_patrol.py`
- `test/tests/test_admin_sandbox_ops.py`

---

## 7. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-21 | 初版文档 |
