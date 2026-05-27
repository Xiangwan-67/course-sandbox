# course-sandbox 项目整体报告

---

## 1. 项目概述

| 项 | 说明 |
|----|------|
| **项目名称** | 标题党 / 平台治理沙盘（clickbait-shapan） |
| **仓库目录** | `course-sandbox/` |
| **用途** | 教学/实验用多角色模拟系统，面向课堂（约 50 人同时访问），模拟互联网内容平台的完整生态链 |
| **核心业务流** | 写手发文 → 内容推送 → 用户互动 → 平台治理 → 轮次结算 → 监管行动 |
| **最新版本** | 架构文档最后更新 2026-05-21，共 51 个数据库迁移 |

---

## 2. 技术栈

| 维度 | 详情 |
|------|------|
| **语言** | Python 3.11 |
| **Web 框架** | Django 6（`>=6.0,<7`） |
| **数据库（开发）** | SQLite（默认，无需配置） |
| **数据库（生产）** | MySQL 8（`utf8mb4`，通过环境变量切换） |
| **LLM 集成** | DeepSeek API（OpenAI SDK 兼容接口，`callLLM.py`） |
| **认证方式** | 自建 Session，明文密码比对（沙盘教学特性，非生产安全模型） |
| **应用服务器** | Gunicorn（gthread 模式，12 workers × 24 threads） |
| **容器化** | Docker + docker-compose（MySQL 8 + Web 两服务） |
| **依赖管理** | uv（本地开发）/ pip + requirements.txt（生产） |
| **测试框架** | pytest（`test/tests/` 功能测试 + `test/mega_sim/` 大型自动模拟） |

### 核心依赖包

| 包 | 版本 | 用途 |
|----|------|------|
| `Django` | `>=6.0,<7` | Web 框架 |
| `gunicorn` | latest | 生产 WSGI 服务器 |
| `PyMySQL` | latest | MySQL 纯 Python 驱动 |
| `openpyxl` | latest | 读写账号管理 Excel |
| `python-dotenv` | latest | 加载 `.env` 环境变量 |
| `openai` | latest | DeepSeek API 调用（兼容接口） |

---

## 3. 项目目录结构

```
course-sandbox/
├── sandbox_site/                   # Django 项目配置层
│   ├── settings.py                 # 核心配置（DB / LLM / 平台目录）
│   ├── urls.py                     # 根路由（含 Admin 运营台/看板）
│   ├── callLLM.py                  # DeepSeek API 封装
│   ├── manage.py                   # Django 管理入口
│   ├── wsgi.py / asgi.py           # 部署接口
│   └── __init__.py
├── accounts/                       # 唯一业务 App，承载全部业务逻辑
│   ├── models.py                   # 全部 ORM 模型（34+ 个，中文表名/字段名）
│   ├── views.py                    # 全部 HTTP 视图（大文件）
│   ├── urls.py                     # 业务路由（app_name='accounts'，60 条）
│   ├── admin.py                    # Django Admin 注册
│   ├── admin_operations.py         # 沙盘运营台页面（/admin/sandbox-ops/）
│   ├── admin_monitor.py            # 模拟看板页面与 API（/admin/sandbox-monitor/）
│   ├── admin_monitor_data.py       # 看板数据查询辅助
│   ├── approval_actions.py         # 管理员审批动作
│   ├── round_ops.py                # perform_end_round() 核心逻辑
│   ├── round_snapshot.py           # 轮次快照写入
│   ├── governance_notices.py       # 治理通知投递写手收件箱
│   ├── clickbait_judge.py          # 标题党判定（与治理包解耦）
│   ├── platform_scope.py           # 平台目录与监管辖区校验
│   ├── writing_cost.py             # 内容相关度→写作成本映射
│   ├── account_import.py           # Excel 账号导入辅助
│   ├── action_logger.py            # 多路日志
│   ├── db_retry.py                 # SQLite 锁重试装饰器
│   └── management/commands/
│       ├── end_round.py            # 管理命令：结束本轮
│       ├── load_accounts.py        # 管理命令：从 Excel 导入账号
│       └── sync_fans_count.py      # 管理命令：重算粉丝数
├── templates/
│   ├── accounts/                   # 各角色页面 HTML（17 个模板）
│   └── admin/                      # Admin 基础/运营台/看板模板
├── docs/
│   ├── ARCHITECTURE.md             # 架构地图
│   ├── ROUTES.md                   # URL 路由速查
│   ├── DEPLOYMENT.md               # 服务器部署教程
│   ├── 并发与数据不丢失说明.md
│   └── features/                   # 分功能业务说明（6 个）
├── test/
│   ├── tests/                      # pytest 功能测试（18 个文件）
│   └── mega_sim/                   # 大型自动化模拟（100 轮）
├── reset_test_data.py              # 清空业务数据（保留账号）
├── allocate_roles.py               # Excel 角色分配脚本
├── requirements.txt                # 生产依赖
├── Dockerfile                      # 单阶段 python:3.11-slim
├── docker-compose.yml              # web + db 编排
├── docker-entrypoint.sh            # 容器启动脚本
├── .env.example                    # 环境变量样板
├── README.md                       # 使用说明
├── CLAUDE.md                       # AI 协作规范
└── WORK_LOG.md                     # 变更日志
```

---

## 4. 核心业务逻辑

### 4.1 四大参与角色

| 角色 | Session role | 数据模型 | 主要职能 |
|------|-------------|---------|---------|
| **写手** | `writer` | `WriterAccount` | 借助 LLM 生成并发布文章，查看收益/排行/通知，受健康分约束 |
| **用户** | `user` | `UserAccount` | 浏览文章、点赞/收藏/举报/评论/关注写手，可在平台间切换 |
| **平台** | `platform` | `PlatformAccount` | 配置治理包（标题党检测/流量惩罚/举报机制/收益惩罚/健康分/绩效方案），查看运营数据 |
| **监管** | `regulator` | `RegulatorAccount` | 发起专项整治/平台巡查/罚款申请（均需管理员审批生效） |
| **管理员** | Django Admin | Django User | 全表管理、运营台审批各类申请、模拟看板监控 |

### 4.2 整体业务流

```
写手发文（LLM 辅助，5 步流程）
    ↓
标题党自动检测（治理包生效时）
    ↓
健康分扣减 + 推流系数影响
    ↓
文章推送给用户（关注列表 / 发现列表）
    ↓
用户浏览互动（点赞/收藏/阅读完成/关注/取关/举报/评论）
    ↓
平台配置治理包 → 管理员审批 → 下一轮生效
    ↓
结束本轮（结算收益、周期利润、轮次+1、投递通知、触发监管自动巡查）
    ↓
监管行动（专项整治/巡查/罚款，管理员审批后生效）
```

### 4.3 写手发文流程（5 步）

| 步骤 | 视图函数 | 说明 |
|------|---------|------|
| 1 | `writer_start_article` | 创建空 Article，写入 session |
| 2 | `writer_generate_titles` | 调用 DeepSeek 生成 3 个候选标题（含夸张度评分） |
| 3 | `writer_select_title` | 写手选择标题，记录 `标题夸张度_初始值` |
| 4 | `writer_generate_bodies` | 调用 DeepSeek 生成 3 个候选正文（含内容相关度评分） |
| 5 | `writer_select_body` | **发布终点**：标题党检测 → 健康分扣减 → `_do_article_push()` 推送 |

推送流量公式：`最终流量 = 基础流量 × 流量惩罚系数(α) × 健康分推流系数`

### 4.4 结束本轮（`perform_end_round()`）

按所有平台循环执行：

1. 健康分恢复（无违规 N 轮后 +分）
2. 用户举报处理（达阈值 → `is_clickbait=True`，记录结算）
3. 文章收益结算（`_settle_article_revenue`）：`w1×点击 + w2×阅读完成 + w3×收藏 - 写作成本`
4. 周期利润结算（每 period 轮一次，含监管成本）
5. 写入轮次快照（`capture_round_snapshot`，幂等 `bulk_create`）
6. 轮次 +1
7. 投递治理通知到写手收件箱
8. 触发监管自动巡查

---

## 5. 关键模块说明

| 文件 | 职责 |
|------|------|
| `accounts/views.py` | 全部 HTTP 视图（写手/用户/平台/监管/结束本轮），业务逻辑主体 |
| `accounts/models.py` | 全部 34+ 个 ORM 模型，中文 db_table 与字段名 |
| `accounts/round_ops.py` | `perform_end_round()`，与 HTTP 视图和管理命令共用同一逻辑 |
| `accounts/round_snapshot.py` | 每轮快照写入（平台/写手/粉丝三维度，幂等） |
| `accounts/clickbait_judge.py` | `judge_clickbait_by_config()`，与治理包生效解耦，巡查/举报/发文共用 |
| `accounts/approval_actions.py` | 管理员审批（罚款/专项整治/巡查/治理措施/绩效方案/功能包配置） |
| `accounts/governance_notices.py` | 轮次切换后向写手投递治理通知 |
| `accounts/platform_scope.py` | 平台 ID 集合/名称/监管辖区，读 `settings.SANDBOX_PLATFORMS` |
| `accounts/writing_cost.py` | 内容相关度(1~5)→写作成本，查 `AdminBaseConfig.写作成本映射` |
| `accounts/action_logger.py` | 5 路日志：simulation/regulator/admin/platform/system |
| `accounts/admin_operations.py` | 沙盘运营台（Tab 式审批界面） |
| `accounts/admin_monitor.py` | 模拟看板（写手完稿状态、治理包/巡查统计） |
| `accounts/db_retry.py` | `retry_on_db_locked` 装饰器，应对 SQLite 并发写锁 |
| `sandbox_site/callLLM.py` | DeepSeek API 调用，仅用于写手生成标题/正文 |

---

## 6. 数据模型（完整索引）

### 账号类（4 个）

| 模型 | db_table | 关键字段 |
|------|----------|---------|
| `WriterAccount` | 写手 | 账号、密码、所属平台、粉丝数、健康分、health_tier、推流系数 |
| `UserAccount` | 用户 | 账号、密码、所属平台、关注数、禁止登录截止时间 |
| `PlatformAccount` | 平台账号 | 账号、密码、所属平台 |
| `RegulatorAccount` | 监管机构账号 | 账号、密码、负责平台编号列表（JSON） |

### 内容与推送类（7 个）

| 模型 | db_table | 关键字段 |
|------|----------|---------|
| `SimulationRound` | 模拟轮次 | 当前轮次（单行 pk=1） |
| `Article` | 文章 | 写手账号、轮次、标题、夸张度初始/校准值、正文、相关度初始/校准值、点击/点赞/收藏/阅读完成量、报酬、`is_clickbait`、`clickbait_source`、`clickbait_auto_executed` |
| `Comment` | 评论 | 文章(FK)、内容、评论者 |
| `ArticlePush` | 文章推送记录 | 平台、文章(FK)、用户(FK)、列表类型(0关注/1发现) |
| `ArticlePushDetail` | 文章推送明细 | 平台、文章(FK)、用户(FK)、是否粉丝 |
| `ArticleTraffic` | 文章流量记录 | 文章(FK)、轮次、基础/最终流量、惩罚系数、健康分系数 |

### 用户互动类（8 个）

| 模型 | 说明 |
|------|------|
| `UserFollowWriter` | 用户关注写手（unique_together） |
| `UserArticleLike` | 点赞（unique_together） |
| `UserArticleCollect` | 收藏（unique_together） |
| `UserArticleReadComplete` | 阅读完成（unique_together） |
| `ArticleReport` | 用户举报记录 |
| `PlatformSwitchSurvey` | 切换平台问卷调查 |
| `UnfollowSurvey` | 取关问卷调查 |
| `ReportAnomalyRecord` | 举报异常记录 |

### 平台治理类（12 个）

| 模型 | 说明 |
|------|------|
| `PlatformGovernanceMeasure` | 治理措施记录（6 种类型，status: pending/active/rejected/cancelled） |
| `ClickbaitDetectionConfig` | 标题党检测配置（夸张度阈值 X、内容相关度阈值 Y） |
| `ClickbaitDetectionResult` | 检测结果（来源：auto/user_report/patrol） |
| `TrafficPenaltyConfig` | 流量惩罚配置（降权系数 α） |
| `UserReportConfig` | 举报配置（触发阈值、审核方式 auto/manual） |
| `RevenuePenaltyConfig` | 收益惩罚配置（惩罚系数 β） |
| `AccountHealthConfig` | 健康分规则（初始分、违规扣减、恢复机制） |
| `AccountHealthLevelConfig` | 健康分档位（档位标签、分数区间、推流比例） |
| `WriterGovernanceNotice` | 写手治理通知收件箱 |
| `WriterHealthScoreLog` | 健康分变更审计日志 |
| `PlatformPerformanceScheme` | 绩效方案（S1均衡/S2点击优先/S3质量优先，w1/w2/w3 权重） |
| `ProfitWeightConfig` | 平台利润权重配置（利润展示窗口轮数） |

### 监管类（8 个）

| 模型 | 说明 |
|------|------|
| `RegulationActionApplication` | 监管专项整治申请 |
| `RegulationAction` | 专项整治正式记录 |
| `PlatformSpotCheckResult` | 抽查结果 |
| `PlatformPatrolApplication` | 监管机构平台巡查申请 |
| `PlatformPatrolResult` | 监管机构平台巡查记录 |
| `PlatformSelfPatrolApplication` | 平台自查申请 |
| `PlatformSelfPatrolResult` | 平台自查记录 |
| `RegulatorFineApplication` | 罚款申请 |
| `RegulatorFineRecord` | 罚款记录（四档：light/basic/medium/strict） |

### 结算类（3 个）

| 模型 | 说明 |
|------|------|
| `ArticleRevenueSettlement` | 单篇文章收益结算（含各因子金额、惩罚系数） |
| `PlatformCycleProfitRecord` | 平台周期利润（含监管成本） |
| `AdminBaseConfig` | 全局基础配置（写作成本映射、自动巡查比例、罚款四档数值） |

### 轮次快照类（4 个）

| 模型 | 说明 |
|------|------|
| `RoundSnapshotBatch` | 快照批次（每轮唯一，记录触发方式） |
| `RoundSnapshotPlatform` | 平台维度快照（用户数、标题党数、利润等） |
| `RoundSnapshotWriter` | 写手维度快照（粉丝数、收益、健康分、推流系数） |
| `RoundSnapshotWriterFan` | 写手-粉丝关系快照 |

---

## 7. API 路由列表

### 根路由（`sandbox_site/urls.py`）

| 路径 | 说明 |
|------|------|
| `admin/sandbox-ops/` | 沙盘运营台（需 Admin 登录） |
| `admin/sandbox-monitor/` | 模拟看板 HTML |
| `admin/sandbox-monitor/api/writers/` | JSON：写手完稿状态（`?round=`） |
| `admin/sandbox-monitor/api/governance/` | JSON：治理包+巡查统计（`?round=`） |
| `admin/` | Django Admin 标准后台 |

### 公共路由

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET/POST | 登录页 |
| `/logout/` | GET | 退出 |
| `/end-round/` | POST | 结束本轮（返回 JSON） |

### 写手路由（`writer/`，11 条）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/writer/` | GET | 写手首页 |
| `/writer/history/` | GET | 发文历史 |
| `/writer/notices/` | GET | 通知收件箱 |
| `/writer/article/<id>/` | GET | 文章详情 |
| `/writer/start-article/` | POST | 开始写文 |
| `/writer/generate-titles/` | POST | LLM 生成候选标题 |
| `/writer/select-title/` | POST | 选择标题 |
| `/writer/generate-bodies/` | POST | LLM 生成候选正文 |
| `/writer/select-body/` | POST | 选择正文并发布 |
| `/writer/notices/<id>/read/` | POST | 标记通知已读 |
| `/writer/health-log/<id>/confirm/` | POST | 确认健康分变更 |

### 用户路由（`user/`，12 条）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/user/` | GET | 用户首页 |
| `/user/browse/<platform_id>/` | GET | 浏览指定平台文章 |
| `/user/article/<id>/` | GET | 文章详情 |
| `/user/platform-check/` | POST JSON | 切换平台前检查 |
| `/user/switch-platform/` | POST JSON | 切换平台（含冷却） |
| `/user/article/<id>/like/` | POST JSON | 点赞 |
| `/user/article/<id>/collect/` | POST JSON | 收藏 |
| `/user/article/<id>/read-complete/` | POST JSON | 标记阅读完成 |
| `/user/article/<id>/follow/` | POST JSON | 关注写手 |
| `/user/article/<id>/unfollow/` | POST JSON | 取关写手 |
| `/user/article/<id>/report/` | POST JSON | 举报文章 |
| `/user/article/<id>/comment/` | POST JSON | 评论 |

### 平台路由（`platform/`，19 条）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/platform/` | GET | 平台首页 |
| `/platform/governance/` | GET | 治理包总览 |
| `/platform/governance/clickbait-detection/` | GET | 标题党检测配置页 |
| `/platform/governance/traffic-penalty/` | GET | 流量惩罚配置页 |
| `/platform/governance/report/` | GET | 举报机制配置页 |
| `/platform/governance/revenue-penalty/` | GET | 收益惩罚配置页 |
| `/platform/round-result/` | GET | 轮次结果页 |
| `/platform/performance/` | GET | 绩效方案页 |
| `/platform/platform-patrol/` | GET | 平台自查页 |
| `/platform/governance/publish/` | POST | 发布治理措施 |
| `/platform/governance/cancel/` | POST | 撤销治理措施 |
| `/platform/governance/clickbait-detection/save/` | POST | 保存标题党检测参数 |
| `/platform/governance/traffic-penalty/save/` | POST | 保存流量惩罚参数 |
| `/platform/governance/report/save/` | POST | 保存举报机制参数 |
| `/platform/governance/revenue-penalty/save/` | POST | 保存收益惩罚参数 |
| `/platform/performance/apply/` | POST | 申请绩效方案 |
| `/platform/performance/submit/` | POST | 提交绩效方案 |
| `/platform/platform-patrol/submit/` | POST | 提交平台自查申请 |

### 监管路由（`regulator/`，8 条）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/regulator/` | GET | 监管首页 |
| `/regulator/special-action/` | GET | 专项整治申请页 |
| `/regulator/platform-patrol/` | GET | 平台巡查申请页 |
| `/regulator/platform-spot-check/<pk>/` | GET | 抽查结果详情 |
| `/regulator/platform-spot-check/<pk>/open/` | GET | 查看抽查结果 |
| `/regulator/special-action/submit/` | POST | 提交专项整治申请 |
| `/regulator/platform-patrol/submit/` | POST | 提交巡查申请 |
| `/regulator/fine/submit/` | POST | 提交罚款申请 |

---

## 8. 配置与环境变量

### 核心环境变量（`.env.example`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MYSQL_HOST` | MySQL 主机（设置后切换至 MySQL 模式） | — |
| `MYSQL_DATABASE` | 数据库名 | `sandbox` |
| `MYSQL_USER` | 数据库用户 | `sandbox` |
| `MYSQL_PASSWORD` | 数据库密码 | — |
| `MYSQL_PORT` | 端口 | `3306` |
| `DEEPSEEK_API_KEY` | DeepSeek LLM 密钥（写手功能必需） | — |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-reasoner` |
| `DJANGO_SECRET_KEY` | Django 密钥（生产必须设置） | — |
| `DJANGO_DEBUG` | 调试模式 | `1` |
| `DJANGO_ALLOWED_HOSTS` | 允许的 Host（生产设域名/IP） | `*` |

### 平台配置（`settings.SANDBOX_PLATFORMS`）

```python
SANDBOX_PLATFORMS = (
    (0, "平台1"), (1, "平台2"),
    (2, "平台3"), (3, "平台4"),
)
```

当前支持 4 个平台，通过 `platform_scope.valid_platform_ids()` 访问，禁止硬编码。

---

## 9. 部署架构

### 本地开发

```
uv run python sandbox_site/manage.py runserver
→ SQLite（自动）+ Django 开发服务器
```

### 生产（裸机）

```
浏览器 → (可选 Nginx :80) → Gunicorn gthread :8000 → Django WSGI
                                      ↓
                                MySQL 8（127.0.0.1）
```

推荐 Gunicorn 参数：`--worker-class gthread --workers 12 --threads 24 --timeout 180`

### 容器化（Docker）

```
docker-compose up -d
→ web 服务（python:3.11-slim + Gunicorn，宿主机 80 → 容器 8000）
→ db 服务（MySQL 8，内部通信，数据 volume 持久化）
```

容器启动流程：等待 MySQL → `migrate` → `collectstatic` → `gunicorn`

---

## 10. 管理命令速查

| 命令 | 说明 |
|------|------|
| `manage.py migrate` | 应用数据库迁移（共 51 个） |
| `manage.py load_accounts [--clear] [--file path]` | 从 Excel 导入账号及初始关注关系 |
| `manage.py end_round` | 结束本轮（与 HTTP `/end-round/` 等价） |
| `manage.py sync_fans_count` | 按关注表重算写手粉丝数/用户关注数 |
| `manage.py createsuperuser` | 创建 Django Admin 超级用户 |
| `manage.py collectstatic` | 收集静态文件 |
| `python reset_test_data.py` | 清空业务数据（保留账号），重开一局 |
| `python allocate_roles.py` | 从学生名册分配角色写入 Excel |

---

## 11. 测试体系

| 类型 | 路径 | 说明 |
|------|------|------|
| 功能测试 | `test/tests/`（18 个文件） | 涵盖标题党检测、举报、治理包、结算等核心流程 |
| 大型模拟 | `test/mega_sim/test_mega_simulation.py` | 100 轮随机种子自动模拟，需 `MEGA_SIM_RUN=1` 启用 |
| 运行入口 | `uv run python test/run.py` | 执行 `test/tests/`，生成 `test/reports/` |

大型模拟可配环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `MEGA_SIM_RUN` | 未设置（跳过） | 必须为 `1` 才执行 |
| `MEGA_SIM_ROUNDS` | `100` | 模拟轮数 |
| `MEGA_SIM_SEED` | `20260420` | 随机种子 |
| `MEGA_SIM_USER_READS` | `5` | 每轮每用户阅读篇数 |

---

## 12. 关键设计决策与注意事项

| 决策 | 说明 |
|------|------|
| **认证安全** | 明文密码比对 + 自建 Session，沙盘教学特性，不适用于真实生产安全场景 |
| **中文字段名** | 全部 ORM 字段与 db_table 均为中文，可读性高；MySQL 迁移时需注意 CHECK constraint 问题（`0016` 迁移需手动 `DROP CHECK 用户_chk_1`） |
| **平台可扩展** | 通过 `settings.SANDBOX_PLATFORMS` 统一管理平台数量，代码禁止硬编码平台数/ID |
| **治理包解耦** | 标题党判定（`clickbait_judge.py`）与治理包是否生效解耦，巡查/举报/发文自动检测统一使用 `judge_clickbait_by_config()` |
| **快照机制** | 每轮结束写入 `RoundSnapshot*` 四张快照表，历史数据持久化，支持回溯和看板展示 |
| **SQLite 并发** | `db_retry.py` 装饰器重试 + `threading.Lock` 序列化写路径 + DB timeout=20，适用于开发；生产需 MySQL + Gunicorn gthread |
| **单 App 设计** | 全部业务逻辑集中于 `accounts` 一个 Django App，`views.py` 为大文件，通过函数名 grep 定位 |

---

## 13. 文档索引

| 文档 | 内容 |
|------|------|
| `README.md` | 环境准备、初始化、运行、管理命令、Docker、测试 |
| `docs/DEPLOYMENT.md` | 服务器裸机部署全流程（MySQL 建库、迁移坑、Gunicorn、systemd、故障排查） |
| `docs/ARCHITECTURE.md` | 架构地图、目录说明、功能树（Mermaid）、模型索引 |
| `docs/ROUTES.md` | URL 路由速查表 |
| `docs/features/*.md` | 分功能详细说明（标题党字段、写手发文、用户浏览、平台治理、结束本轮结算、监管端） |
| `docs/并发与数据不丢失说明.md` | SQLite 并发处理机制 |
| `CLAUDE.md` | AI 协作规范与读档顺序 |
| `WORK_LOG.md` | 按日期的变更/部署记录 |

---

*报告基于代码库实际内容生成，架构文档最后更新 2026-05-21，包含 51 个数据库迁移，34+ 个数据模型，约 60 条业务路由。*
