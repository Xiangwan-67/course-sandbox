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

---

### feat: 收益惩罚配置改为管理员配置参数、平台主动发起申请

**需求：** 原流程要求平台自填 β 值提交、等管理员审核，驳回后重新提交流程繁琐。改为由管理员在后台预置参数，平台仅负责提交发布申请，与标题党检测的模式对齐。

**修改文件及位置：**

- `accounts/views.py`：`platform_revenue_penalty_save` 改为直接返回 410，平台侧不再允许提交 β 参数
- `accounts/views.py:1713`：`platform_revenue_penalty` GET 视图查询 `cfg` 时加 `status='active'` 过滤，只展示管理员已审核通过的配置
- `accounts/views.py:1488`：`platform_governance_publish` 中 revenue_penalty 分支前置检查从 `status IN ('pending','active')` 收紧为 `status == 'active'`，平台须等管理员审核通过后才能提交发布申请
- `accounts/views.py:1966`：结算函数取 β 时加 `status='active'` 过滤，防止被驳回的配置参数仍被结算读取
- `templates/accounts/platform_revenue_penalty.html`：删除 β 输入表单与 `saveConfig()` JS 函数，改为只读展示管理员配置的参数值，并更新无配置时的提示文字

---

### fix: 修复平台参数无法重新提交（方案一——允许覆盖 pending 配置）

**问题：** 流量惩罚与用户举报的配置提交接口在 `status IN ('pending', 'active')` 时均拒绝新提交。平台提交参数后若管理员迟迟未审核，平台将无法修改参数，只能等待，体验差。

**修改文件及位置：**

- `accounts/views.py` — `platform_traffic_penalty_save`：将前置检查从"pending 或 active 均拒绝"收紧为"仅 active 时拒绝"；同时在创建新配置前将已有 pending 记录自动置为 `rejected`，允许平台随时以新参数覆盖待审核的旧配置
- `accounts/views.py` — `platform_report_save`：同上，适用于 `UserReportConfig`
- `templates/accounts/platform_traffic_penalty.html`：前端"配置已生效"禁用提示的条件从 `config.status == 'pending' or 'active'` 收紧为仅 `config.status == 'active'`，pending 状态下提交按钮仍可见
- `templates/accounts/platform_report.html`：同上，适用于用户举报配置页

**设计决策：** 仅 `active`（已生效）状态阻止重新提交，保证线上生效参数不被意外覆盖；`pending`（待审核）视为草稿，可随时被新提交替换。

---

### style: 前端界面统一美化

**目标：** 消除散乱的内联样式，建立一套统一的视觉设计语言，不影响任何业务逻辑。

**新增文件：**

- `templates/accounts/_base_style.html`：共用 CSS 片段，通过 `{% include %}` 在各模板 `<head>` 末尾引入，定义以下样式体系：
  - 布局：`.sb-page`（居中容器）、`.sb-navbar`（顶部固定导航栏）
  - 区块：`.sb-section`（通用内容区块）、`.sb-card`、`.sb-infobox`/`.sb-infobox-ok`/`.sb-infobox-warn`（参数展示子块）、`.sb-summary`（虚线摘要区）
  - 组件：`.badge-green/orange/gray/red/blue`（状态徽章）、`btn-primary`/`btn-danger`（按钮语义化）
  - 工具类：`.text-error`/`.text-warn`/`.text-muted`/`.text-green`

**修改文件（11 个模板，纯样式重构，无逻辑变更）：**

- `login.html`：改为居中卡片登录布局
- `platform_home.html`、`platform_governance.html`、`platform_performance.html`：引入 navbar + sb-page 容器；老式表格属性（`border="1"` / `cellspacing` / `cellpadding`）移除；区块容器改为 `.sb-section`；内联颜色改为工具类
- `platform_clickbait_detection.html`、`platform_traffic_penalty.html`、`platform_revenue_penalty.html`、`platform_report.html`：统一结构（navbar + sb-page + sb-section）；`style="color:#888"` 等内联色改为 `.text-muted`；删除底部冗余 `<p>` 文字导航
- `platform_round_result.html`：区块容器改为 `.sb-section`；新增 `.stat-grid`/`.stat-card` 统计卡片网格
- `regulator_home.html`：罚款记录小表格的 20+ 处 `th`/`td` 内联样式全部移除；状态色改为工具类
- `regulator_special_action.html`：区块容器改为 `.sb-section`/`.sb-infobox`；删除底部冗余导航

