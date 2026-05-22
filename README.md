# 标题党 / 平台治理沙盘（clickbait-shapan）

多角色教学沙盘：写手发文 → 推送 → 用户互动 → 平台治理 → 轮次结算 → 监管行动。  
架构与业务细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs/ROUTES.md](docs/ROUTES.md)、[CLAUDE.md](CLAUDE.md)。

**服务器裸机部署（MySQL + Gunicorn gthread、迁移坑、`.env` 等）：** 见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

**约定：** 本项目使用 [uv](https://github.com/astral-sh/uv) 管理依赖；下文所有 Python 命令均以 `uv run` 为前缀，请勿直接使用裸 `python` / `pip`。

**服务器（`~/course-sandbox` + venv + MySQL）：** 业务命令与下文相同，但前缀不同、Web 用 **systemd/Gunicorn** 而非 `runserver`。完整对照与 systemd 运维见 [docs/DEPLOYMENT.md §11](docs/DEPLOYMENT.md#11-服务器运维命令与-readme-对照)。

---

## 1. 环境准备

| 项 | 说明 |
|----|------|
| Python | 由 uv 按 `pyproject.toml` 解析 |
| 依赖 | 仓库根目录执行 `uv sync`（首次克隆后） |
| 环境变量 | 复制并编辑根目录 `.env`（如 `DEEPSEEK_API_KEY`，写手生成标题/正文用） |
| 数据库 | **未设置** `MYSQL_HOST` + `MYSQL_DATABASE` 时使用 SQLite：`db.sqlite3`（项目根目录） |
| 数据库（生产/Docker） | 设置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD` 等，见 `sandbox_site/settings.py` |

---

## 2. 数据初始化（推荐顺序）

首次部署或换一批账号时，按顺序执行：

```powershell
cd <项目根目录>

# ① 创建/更新表结构
uv run python sandbox_site/manage.py migrate

# ② 从 Excel 导入写手、用户、平台、监管账号，并写入用户初始关注（需项目根目录有 账号管理.xlsx）
uv run python sandbox_site/manage.py load_accounts --clear

# ③ 可选：创建 Django 超级用户（仅访问 /admin/ 需要）
uv run python sandbox_site/manage.py createsuperuser
```

### 2.1 `load_accounts` — 从 Excel 导入账号

| 命令 | 作用 |
|------|------|
| `uv run python sandbox_site/manage.py load_accounts` | 从默认路径 `<项目根>/账号管理.xlsx` 导入/更新账号；**不**清空已有写手、用户 |
| `uv run python sandbox_site/manage.py load_accounts --clear` | 导入前**删除全部写手、用户**（级联删除其关注关系），再导入 |
| `uv run python sandbox_site/manage.py load_accounts --clear-platform` | 导入前**删除全部平台账号** |
| `uv run python sandbox_site/manage.py load_accounts --clear-regulator` | 导入前**删除全部监管机构账号** |
| `uv run python sandbox_site/manage.py load_accounts --file <路径>` | 指定 Excel 文件（默认仍为项目根 `账号管理.xlsx`） |

**Excel 工作表约定：**

| Sheet | 导入目标 | 主要列 |
|-------|----------|--------|
| 第 1 表（写手） | `写手` | `账号`、`密码`；可选 `所属平台`（整数，与 `SANDBOX_PLATFORMS` 一致） |
| 第 2 表（用户） | `用户` | `账号`、`密码`；可选 `所属平台`；可选 **`关注`**（初始关注的写手账号列表） |
| `平台`（按名或第 3 表） | `平台账号` | `账号`、`密码`、`对应编号`（平台编号） |
| `监管机构` | `监管机构账号` | `账号`、`密码`、`负责平台`（如 `[0,1]` 或 `0,1`） |

**`关注` 列格式：** 例如 `['writer14', 'writer13']`（JSON/字面量）或逗号分隔。导入时会：

- 写入表 `用户关注写手`；
- 校验**用户 `所属平台` 与每个被关注写手的 `所属平台` 必须相同**，否则**整次命令失败**并输出错误；
- 按 Excel **覆盖**该用户的关注列表（空单元格表示不关注任何写手）；
- 同步 `用户.关注数`、`写手.粉丝数`。

> `账号管理.xlsx` 通常在 `.gitignore` 中，需自行放在项目根目录或 Docker 挂载目录（见 §5）。

### 2.2 `sync_fans_count` — 按关注表重算计数

```powershell
uv run python sandbox_site/manage.py sync_fans_count
```

**作用：** 根据 `用户关注写手` 表重新计算并写回：

- 每个写手的 `粉丝数` = 关注该写手的用户数；
- 每个用户的 `关注数` = 该用户关注行数。

**何时用：** 在 Admin 或 SQL 中手工增删关注记录后；一般 `load_accounts` 已同步，可不执行。

### 2.3 `reset_test_data.py` — 清空一局模拟（保留账号）

```powershell
uv run python reset_test_data.py
```

**作用：** 清空沙盘**业务数据**，便于「重新开一局」，**不删除**写手/用户/平台/监管账号行本身。

**会删除/重置（摘要）：** 文章及推送、评论、互动、结算、标题党检测记录、举报、治理措施与功能包配置、绩效与周期利润、监管专项/巡查/罚款、模拟相关汇总等；**删除 `用户关注写手` 全部行**；`模拟轮次` 置为 1；写手 `粉丝数` 归零、健康分等恢复默认；用户 `关注数` 归零。

**不会删除：** 四类账号表、管理员基础配置（id=1）、平台利润权重等基础配置。

**注意：** 执行后初始关注也被清空；若要从 Excel 恢复关注，需再执行 `load_accounts`（是否加 `--clear` 视是否要重写写手/用户全表而定）。

**与 `load_accounts` 的区别：**

| | `load_accounts` | `reset_test_data.py` |
|--|-----------------|----------------------|
| 目的 | 灌入/更新账号与初始关注 | 清业务、保留账号 |
| 账号表 | 写入/更新 | 保留 |
| 文章/轮次/治理 | 不动 | 清空 |

### 2.4 Django Admin 超户（`/admin/`，与 Excel 无关）

沙盘首页 `/` 的写手/用户/平台/监管账号**只**来自 `load_accounts`；Django **Admin** 与运营台 `/admin/sandbox-ops/` 需单独建 **超级用户**：

```powershell
# 首次创建（交互输入用户名、密码）
uv run python sandbox_site/manage.py createsuperuser

# 修改已有超户密码
uv run python sandbox_site/manage.py changepassword <用户名>
```

**服务器**上同样命令，前缀见 [docs/DEPLOYMENT.md §5.1](docs/DEPLOYMENT.md#51-django-admin-超户初始化与改密)（`venv` + `source .env`）。

---

## 3. 运行 Web 服务（本地开发）

```powershell
uv run python sandbox_site/manage.py runserver
```

**作用：** 启动 Django 开发服务器（默认 `http://127.0.0.1:8000/`）。  
沙盘业务登录走 `accounts` 自建 Session（`writer` / `user` / `platform` / `regulator`），与 `createsuperuser` 的 Django 用户无关。

| 入口 | URL |
|------|-----|
| 登录 | `/` |
| Django Admin | `/admin/` |
| 沙盘运营台 | `/admin/sandbox-ops/` |

---

## 4. Django 管理命令（本项目）

除 Django 内置命令外，`accounts` 应用提供：

### 4.1 `end_round` — 结束当前模拟轮次

```powershell
uv run python sandbox_site/manage.py end_round
```

**作用（与平台页「结束本轮」同一套 `perform_end_round()`）：**

1. 各平台：健康分恢复、**用户举报达阈值处理**、本轮文章收益结算；
2. 若命中周期末：周期利润结算；
3. 监管自动巡查（轮次切换触发）；
4. `模拟轮次.当前轮次` **+1**。

**适用：** 无浏览器批量推进轮次、脚本/运维调度。有 Web 会话时也可在平台端操作等价逻辑。

### 4.2 查看命令帮助

```powershell
uv run python sandbox_site/manage.py help
uv run python sandbox_site/manage.py help load_accounts
uv run python sandbox_site/manage.py help end_round
```

### 4.3 其他常用 Django 内置命令

| 命令 | 作用 |
|------|------|
| `uv run python sandbox_site/manage.py migrate` | 应用数据库迁移 |
| `uv run python sandbox_site/manage.py makemigrations accounts` | 模型变更后生成迁移（开发用） |
| `uv run python sandbox_site/manage.py createsuperuser` | 创建 Django 超级用户（Admin） |
| `uv run python sandbox_site/manage.py collectstatic --noinput` | 收集静态文件（Docker 入口会执行） |
| `uv run python sandbox_site/manage.py shell` | Django shell，调试 ORM |

---

## 5. Docker 部署

在项目根目录（与 `.env` 同级）：

```powershell
docker-compose build
docker-compose up -d
```

**容器 `web` 启动时自动执行：**

1. 等待 MySQL（`MYSQL_HOST` 默认 `db`）；
2. `python sandbox_site/manage.py migrate`；
3. `python sandbox_site/manage.py collectstatic --noinput`；
4. `gunicorn` 监听 `8000`（映射宿主机 **80**）。

**账号 Excel：** `docker-compose.yml` 将宿主机 `/opt/sandbox/data` 只读挂载到容器 `/data`。若需容器内导入，请将 `账号管理.xlsx` 放在该目录，并执行：

```powershell
docker-compose exec web python sandbox_site/manage.py load_accounts --file /data/账号管理.xlsx --clear
```

（具体 `exec` 语法以本机 Docker 版本为准。）

---

## 6. 测试

### 6.1 默认功能测试套件

```powershell
uv run python test/run.py
```

**作用：** 在 `test/tests/` 下运行 pytest（配置 `test/pytest.ini`），生成 `test/reports/`（`junit.xml`、`report.md`、`pytest_stdout.txt` 等）。

等价于：

```powershell
uv run python -m pytest -c test/pytest.ini test/tests
```

### 6.2 运行单个测试文件

```powershell
uv run python -m pytest test/tests/test_clickbait_detection.py -c test/pytest.ini
```

### 6.3 大型模拟（可选，耗时长）

```powershell
$env:MEGA_SIM_RUN = "1"
uv run python -m pytest test/mega_sim/test_mega_simulation.py -c test/pytest.ini
```

| 环境变量 | 默认 | 作用 |
|----------|------|------|
| `MEGA_SIM_RUN` | （未设置则跳过） | 必须为 `1` 才执行该测试 |
| `MEGA_SIM_ROUNDS` | `100` | 模拟轮数 |
| `MEGA_SIM_SEED` | `20260420` | 随机种子 |
| `MEGA_SIM_USER_READS` | `5` | 每轮每用户阅读篇数 |

测试库会从仓库根 `账号管理.xlsx` 加载账号（见 `test/mega_sim/accounts_loader.py`），**不修改** 开发用 `db.sqlite3`。

---

## 7. 维护脚本（可选，改 Excel 用）

以下脚本**不是**日常开服必需；用于按名册重排 `账号管理.xlsx`：

| 脚本 | 命令 | 作用 |
|------|------|------|
| `allocate_roles.py` | `uv run python allocate_roles.py` | 从 Sheet1 学生名册打乱并分配写手/用户/平台/监管等角色写入 Excel |
| `scripts/replan_accounts.py` | `uv run python scripts/replan_accounts.py` | 按 Sheet1 名册与目标比例重写 Excel 四角色表 |

修改 Excel 后，请重新执行 §2 的 `load_accounts`。

---

## 8. 日志

| 路径 | 内容 |
|------|------|
| `logs/simulation_actions.log` | 沙盘关键操作（推送、治理、结算等），由 `accounts/action_logger.py` 写入 |

---

## 9. 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 本文：命令与数据初始化 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | **服务器部署**（全过程、坑、systemd）+ [§11 命令对照](docs/DEPLOYMENT.md#11-服务器运维命令与-readme-对照) |
| `/admin/sandbox-monitor/` | **模拟看板**（写手完稿、用户分布、治理状态；需 Admin 超户） |
| [CLAUDE.md](CLAUDE.md) | AI/协作规范、读档顺序 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构、功能树、模型 |
| [docs/ROUTES.md](docs/ROUTES.md) | 路由与 API |
| [docs/features/](docs/features/) | 分功能业务说明 |
| [WORK_LOG.md](WORK_LOG.md) | 变更与部署记录 |

---

## 10. 快速对照：我该跑哪条？

| 我想… | 本地（README） | 服务器（[DEPLOYMENT §11](docs/DEPLOYMENT.md#11-服务器运维命令与-readme-对照)） |
|--------|----------------|-------------------------------------------------------------------------------------|
| 第一次搭环境 | `uv sync` → `migrate` → `load_accounts --clear` → `runserver` | `pip install` → `migrate` → `load_accounts --clear` → `systemctl start course-sandbox` |
| 换一批学生账号 | 更新 Excel → `load_accounts --clear` | 同上（先 `source .env`） |
| 比赛结束，保留账号重来一局 | `reset_test_data.py` → 可选 `load_accounts` | 同上 |
| 手工改过关注表，数字不对 | `sync_fans_count` | 同上 |
| 不打开网页，推进到下一轮 | `end_round` | 同上 |
| 初始化 / 改 Django Admin 密码 | `createsuperuser` / `changepassword` | [DEPLOYMENT §5.1](docs/DEPLOYMENT.md#51-django-admin-超户初始化与改密) |
| 跑自动化测试 | `uv run python test/run.py` | 建议在开发机跑；服务器见 DEPLOYMENT |
| 生产容器更新表结构 | `docker-compose exec web ... migrate` | 裸机：`migrate` + `systemctl restart` |
