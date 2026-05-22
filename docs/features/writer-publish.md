# 写手发文与文章推送

**最后更新：** 2026-05-21

---

## 1. 用途

写手在沙盘内完成「选题 → 生成标题 → 选标题 → 生成正文 → 选正文」后发布文章；发布时按平台规则做标题党检测与健康分处理，并向**同平台用户**推送。

---

## 2. 触发链

```
写手首页 writer_home
  → POST writer/start-article/     writer_start_article      创建 Article，session article_id
  → POST writer/generate-titles/   writer_generate_titles    callLLM 生成 3 标题
  → POST writer/select-title/      writer_select_title       存标题、标题夸张度_校准值
  → POST writer/generate-bodies/   writer_generate_bodies    callLLM 生成 3 正文
  → POST writer/select-body/       writer_select_body        见 §4 副作用链
```

Session：`role=writer`，`account`，`article_id`（发文过程中）。

---

## 3. 核心符号

| 类型 | 名称 |
|------|------|
| 视图 | `writer_start_article`, `writer_generate_titles`, `writer_select_title`, `writer_generate_bodies`, `writer_select_body`, `article_detail` |
| 内部 | `_get_writer_article`, `_do_article_push`, `is_clickbait`, `record_clickbait_judgment` |
| 模型 | `Article`, `WriterAccount`, `ArticlePush`, `ArticlePushDetail`, `ArticleTraffic`, `ClickbaitDetectionResult`, `WriterHealthScoreLog` |
| 判定 | `accounts/clickbait_judge.py` |
| LLM | `sandbox_site.callLLM.call_deepseek_api` |
| 日志 | `action_log` |

---

## 4. 业务规则（当前真相）

### 4.1 `writer_select_body` 副作用顺序

1. 写入 `正文`、`内容相关度_校准值`、`轮次`（当前 `SimulationRound`）
2. **标题党检测**（仅当平台该轮次生效的 `clickbait_detection` 治理包存在）  
   - `record_clickbait_judgment(..., source=auto, ...)`  
   - 规则：`X >= 阈值X` 且 `Y < 阈值Y` → 标题党  
   - 审计：`ClickbaitDetectionResult`（`判定来源=auto`，True/False 均记）  
   - 文章：`is_clickbait`、`clickbait_source=auto`（覆盖为最新来源）
3. **健康分**（治理包 `account_health_rule` 生效且命中标题党）  
   - 扣分、更新 `推流系数` / `health_tier`，写 `WriterHealthScoreLog`
4. **`_do_article_push(article)`** — 见下

### 4.2 文章推送 `_do_article_push`

- **受众：** 仅 `UserAccount.所属平台 == 写手.所属平台` 的用户；**不跨平台推送**。
- **粉丝（关注列表，列表类型=0）：** 已关注该写手的同平台用户 **100%** 推送。
- **发现列表（列表类型=1）：** 非粉丝按抽样比例推送：  
  `final_ratio = clamp(写手表.推流系数 × α)`  
  - `推流系数`：健康分档位同步或默认 1  
  - `α`：仅当平台启用 `traffic_penalty` 且文章 `is_clickbait` 时取 `TrafficPenaltyConfig.降权系数alpha`，否则为 1
- **幂等：** 已存在 `ArticlePush(文章, 用户)` 的不再插入。
- **写入：** `bulk_create` `ArticlePush` + `ArticlePushDetail`（含 `平台` 字段）；更新 `Article.已推送`；创建 `ArticleTraffic` 记录。
- **性能：** 批量插入替代逐行 `get_or_create`（见 WORK_LOG 2026-05-21）。

### 4.3 标题与正文生成

- 五档夸张度/相关度由滑块与三选一位置决定校准值（`select-title` / `select-body` 内逻辑）。
- 生成依赖外部 LLM；失败时返回 JSON 错误。

---

## 5. 平台 / 轮次依赖

| 依赖 | 说明 |
|------|------|
| `writer.所属平台` | 决定推送用户池、治理配置 `platform_id` |
| `article.轮次` | 发文时写入当前轮；用户浏览只显示当前轮推送 |
| 治理包 | `PlatformGovernanceMeasure` 按平台+生效轮次决定是否执行检测/惩罚/健康分 |

---

## 6. 相关测试

- `test/tests/test_clickbait_detection.py`
- `test/tests/test_traffic_penalty.py`
- `test/tests/test_account_health_score.py`
- `test/tests/test_writer_health_popup.py`
- `test/mega_sim/`（端到端模拟）

---

## 7. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-21 | 推送 bulk_create；`ArticlePush` 增加 `平台` 字段（迁移 0047） |
| 2026-05-21 | 判定追溯：auto_rule_executed、clickbait_source、record_clickbait_judgment |
| 2026-05-21 | 初版文档 |
