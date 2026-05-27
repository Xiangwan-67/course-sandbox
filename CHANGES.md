# 修改追踪

## 2026-05-27

### fix: 阻止空文章被发布（方案三——发布前校验）

**问题：** 写手点击「发布文章」按钮后，若不选择标题或正文直接关闭/放弃，后端已在 `writer_start_article` 中提前创建了空 Article 记录（标题/正文均为空字符串），构成空文章。

**修改文件：** `accounts/views.py`

**修改位置：** `writer_select_body` 函数，第 3338-3341 行

**变更内容：** 在解析 `body_text` 之后、写库之前新增两条前置校验：

1. `body_text` 为空时返回 400，阻止正文为空的文章被发布
2. `article.标题` 为空时返回 400，阻止跳过选标题步骤直接提交正文

**局限：** 空文章记录在 `writer_start_article` 时仍会被创建并残留于数据库，本次修改仅阻止其被推送给用户。如需彻底解决，可后续采用方案二（增加 `is_published` 状态字段）或方案一（延迟建库至最后一步）。

---

### fix: 修复平台利润看板不显示（措施 A + C）

**问题：** 平台首页利润看板始终显示"暂不展示"，原因有二：
1. `ProfitWeightConfig` 表为空时，结算端 `_settle_cycle_profit` 直接跳过写库，`PlatformCycleProfitRecord` 永远为空
2. 展示端查询 `period` 所用轮次为 `current_round`，而结算端使用 `round_to_settle`（即 `current_round - 1`），在权重配置轮次边界处两侧 `period` 不一致，导致 `cycle_index` 错位查不到记录

**修改文件及位置：**

- `accounts/management/commands/load_accounts.py`：`handle()` 末尾新增检查，若 `ProfitWeightConfig` 表为空则自动创建全局默认配置（各权重=1，窗口=4轮），每次 `load_accounts` 时执行，已有配置则跳过
- `accounts/views.py:340`：`platform_home` 展示端查询 `period` 时，将传入 `_get_effective_profit_config` 的轮次从 `current_round` 改为 `max(1, current_round - 1)`，与结算端对齐
