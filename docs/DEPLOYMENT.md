# 服务器部署教程（裸机 + MySQL + Gunicorn）

**最后更新：** 2026-05-22  

面向课堂/实验（约 **50 人同时访问**）。本文汇总在 Ubuntu 服务器（如 `~/course-sandbox`、PowerEdge R930）上从零部署的流程、常见坑与注意事项。  

- 本地命令索引：[README.md](../README.md)  
- **服务器运维命令（与 README 一一对应）：** 本文 [§11](#11-服务器运维命令与-readme-对照)  
- Docker 部署：[README.md §5](../README.md)  
- 架构说明：[ARCHITECTURE.md](ARCHITECTURE.md)

---

## 0. 架构一览

```text
浏览器 → (可选 Nginx :80) → Gunicorn (gthread) → Django (WSGI)
                                    ↓
                              MySQL 8（127.0.0.1）
```

| 组件 | 生产建议 | 勿用 |
|------|----------|------|
| 数据库 | **MySQL 8** | SQLite（多人并发易锁库） |
| 应用服务器 | **Gunicorn + gthread** | `manage.py runserver` |
| 配置 | 项目根 **`.env`** | 仅本地 `(1).env`、未上传到服务器 |
| 账号 | **`账号管理.xlsx`** + `load_accounts` | 仅 Django Admin 手工建号 |

---

## 1. 环境与目录

```bash
cd ~/course-sandbox
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

开发机可用 `uv sync`；命令里把 `python` 换成 `uv run python` 即可。

根目录需有：

- `.env`（MySQL、DeepSeek 等）
- `账号管理.xlsx`（常在 `.gitignore`，需自行上传）

---

## 2. 环境变量 `.env`

文件名必须是 **`.env`**，放在**项目根**。

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=sandbox
MYSQL_USER=sandbox
MYSQL_PASSWORD=你的密码

DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-reasoner

DJANGO_DEBUG=0
DJANGO_SECRET_KEY=随机长字符串
DJANGO_ALLOWED_HOSTS=你的公网IP或域名
```

### 坑：未配 `MYSQL_*` 会用 SQLite

`settings.py` 要求 **`MYSQL_HOST` 与 `MYSQL_DATABASE` 同时非空** 才连 MySQL，否则使用 `db.sqlite3`。

验证（必须先加载环境变量）：

```bash
set -a && source .env && set +a
python sandbox_site/manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

应输出：`django.db.backends.mysql`

---

## 3. MySQL

### 3.1 建库与用户（首次）

```bash
sudo mysql
```

```sql
CREATE DATABASE sandbox CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sandbox'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON sandbox.* TO 'sandbox'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

| 说明 | |
|------|--|
| `sandbox` | 数据库名，与 `MYSQL_DATABASE` 一致 |
| `'sandbox'@'localhost'` | Django 在本机连 `127.0.0.1` 时用此用户，**不要**写成服务器公网 IP |
| 公网 IP | 给学生访问 **网站**；连库仍是本机 |

### 3.2 库/用户已存在

```text
ERROR 1007: database exists
ERROR 1396: CREATE USER failed
```

用 root 改密码并授权即可：

```sql
ALTER USER 'sandbox'@'localhost' IDENTIFIED BY '新密码';
GRANT ALL PRIVILEGES ON sandbox.* TO 'sandbox'@'localhost';
FLUSH PRIVILEGES;
```

测试登录：

```bash
mysql -u sandbox -p sandbox -e "SELECT 1;"
```

### 3.3 1045 Access denied

密码与 `.env` 不一致。`ALTER USER` 统一密码后重试。

---

## 4. 数据库迁移

```bash
cd ~/course-sandbox
source venv/bin/activate
set -a && source .env && set +a
python sandbox_site/manage.py migrate
```

### 坑：0016 在 MySQL 8 失败（必看）

**报错：**

```text
Check constraint '用户_chk_1' uses column '粉丝数', hence column cannot be dropped or renamed.
```

**原因：** 迁移 `0016` 将 `粉丝数` 改名为 `关注数`；迁移 `0009` 在 MySQL 8 上为无符号整型加了 CHECK `用户_chk_1`。**空库也会复现。**

**处理：** 在 `migrate` 失败后执行一次：

```sql
USE sandbox;
ALTER TABLE `用户` DROP CHECK `用户_chk_1`;
```

终端中文显示异常时，用 Django：

```bash
set -a && source .env && set +a
python sandbox_site/manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('ALTER TABLE \`用户\` DROP CHECK \`用户_chk_1\`')
print('ok')
"
```

再执行：

```bash
python sandbox_site/manage.py migrate
```

### 坑：在 `mysql>` 里跑 bash 命令

`python manage.py`、`mysql -u sandbox ...` 只能在 **shell** 里执行，不能贴在 `mysql>` 下。

### 3.4 数据库是否正常（健康检查）

以下命令在 **Linux shell**（`~/course-sandbox`）执行；密码与 `.env` 里 `MYSQL_*` 一致。先加载环境变量：

```bash
cd ~/course-sandbox
source venv/bin/activate
set -a && source .env && set +a
```

#### 3.4.1 MySQL 服务是否在跑

```bash
sudo systemctl status mysql
# 或部分系统服务名为 mysqld
sudo systemctl status mysqld
```

`Active: active (running)` 为正常。若未启动：

```bash
sudo systemctl start mysql
```

#### 3.4.2 客户端能否连上库（不经过 Django）

```bash
mysql -h 127.0.0.1 -P 3306 -u sandbox -p sandbox -e "SELECT 1 AS ok;"
```

提示输入密码；显示 `ok` 和 `1` 即账号、库名、密码正确。

用 `.env` 变量（避免手打错主机/库名）：

```bash
mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT:-3306}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" -e "SELECT DATABASE(), VERSION();"
```

#### 3.4.3 Django 是否连的是 MySQL（推荐）

```bash
python sandbox_site/manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

应输出 `django.db.backends.mysql`（若仍是 `sqlite3`，说明 `.env` 未加载或 `MYSQL_HOST`/`MYSQL_DATABASE` 为空）。

```bash
python sandbox_site/manage.py check --database default
python sandbox_site/manage.py shell -c "
from django.db import connection
connection.ensure_connection()
print('连接成功:', connection.settings_dict['HOST'], connection.settings_dict['NAME'])
"
```

无报错即 Django 到 MySQL 通路正常。

#### 3.4.4 迁移是否齐全

```bash
python sandbox_site/manage.py showmigrations accounts | tail -20
python sandbox_site/manage.py migrate --plan | tail -5
```

未打 `[X]` 的迁移需执行 `migrate`。课堂部署至少应看到 `[X] 0051_round_snapshot_tables`。

#### 3.4.5 进入 MySQL 交互（`mysql>`）

**方式 A：** 系统客户端

```bash
mysql -u sandbox -p sandbox
```

**方式 B：** Django（自动用当前 `settings` 账号）

```bash
set -a && source .env && set +a
python sandbox_site/manage.py dbshell
```

进入后提示符为 `mysql>`，可执行下面 SQL；退出：`EXIT;` 或 `\q`。

#### 3.4.6 常用 SQL（沙盘库 `sandbox`）

```sql
-- 当前库与表数量
SELECT DATABASE();
SHOW TABLES;

-- 核心业务表是否有数据（部署后 load_accounts 应有行）
SELECT COUNT(*) AS 写手数 FROM `写手`;
SELECT COUNT(*) AS 用户数 FROM `用户`;
SELECT COUNT(*) AS 平台账号数 FROM `平台账号`;
SELECT COUNT(*) AS 监管机构数 FROM `监管机构账号`;

-- 当前模拟轮次（单行 pk=1）
SELECT * FROM `模拟轮次`;

-- Django 迁移记录（accounts 应用）
SELECT id, app, name, applied FROM django_migrations WHERE app = 'accounts' ORDER BY id DESC LIMIT 10;

-- 轮次快照（需已 migrate 0051 且至少结束过一轮才有数据）
SELECT COUNT(*) AS 快照批次数 FROM `轮次快照批次`;
```

| 现象 | 可能原因 |
|------|----------|
| `SHOW TABLES` 很少或没有中文表名 | 未执行 `migrate` |
| `写手`/`用户` 为 0 | 未执行 `load_accounts` 或 Excel 不在项目根 |
| `django_migrations` 无 `0051` | 未 migrate 到最新 |
| `SELECT 1` 失败 1045 | 密码与 `.env` 不一致，见 §3.3 |
| `Can't connect` | MySQL 未启动，或 `MYSQL_HOST` 不是本机可达地址 |

#### 3.4.7 连接数与慢查询（人多卡顿时可看）

```sql
SHOW STATUS LIKE 'Threads_connected';
SHOW FULL PROCESSLIST;
```

`Threads_connected` 持续很高时，检查是否有僵死连接或 Gunicorn worker 过多。

---

## 5. 导入账号

```bash
set -a && source .env && set +a
python sandbox_site/manage.py load_accounts --clear
```

| 说明 | |
|------|--|
| `--clear` | 清空写手、用户后重导；首次部署建议带上 |
| 「关注」列 | 如 `['writer14','writer13']`；写入 `用户关注写手` |
| 同平台校验 | 用户与写手 `所属平台` 须一致，否则整次失败 |
| 仅 migrate | 无账号，无法登录沙盘 |

Django **Admin 超户**（`/admin/`、`/admin/sandbox-ops/`）见 **§5.1**；与 Excel 沙盘账号无关。

---

## 5.1 Django Admin 超户：初始化与改密

### 两套账号，不要混用

| 用途 | 账号来源 | 登录入口 | 命令 |
|------|----------|----------|------|
| 课堂沙盘（写手/用户/平台/监管） | `账号管理.xlsx` → `load_accounts` | 站点首页 `/` | `load_accounts` |
| Django 后台 / 运营台 | `auth_user` 超级用户 | `/admin/`、`/admin/sandbox-ops/` | `createsuperuser` / `changepassword` |

`load_accounts`、`reset_test_data.py` **不会**创建或修改 Django Admin 用户。

### 公共前缀（SSH 上执行）

```bash
cd ~/course-sandbox
source venv/bin/activate
set -a && source .env && set +a
```

### 首次创建超户（交互式，推荐）

```bash
python sandbox_site/manage.py createsuperuser
```

按提示输入 **用户名**、**邮箱**（可回车跳过）、**密码**（输入两次，屏幕不回显）。  
创建后浏览器访问：

| URL | 说明 |
|-----|------|
| `http://202.112.113.142:8000/admin/` | Django 自带后台 |
| `http://202.112.113.142:8000/admin/sandbox-ops/` | 沙盘运营台（需先以超户登录 Admin） |

无需重启 Gunicorn / systemd；用户写在 MySQL 的 `auth_user` 表。

### 修改已有超户密码

```bash
python sandbox_site/manage.py changepassword <用户名>
```

示例：

```bash
python sandbox_site/manage.py changepassword admin
```

按提示输入新密码两次。改密后**立即生效**，旧会话可能仍有效直至过期或退出登录。

### 忘记超户用户名

```bash
python sandbox_site/manage.py shell -c "
from django.contrib.auth import get_user_model
for u in get_user_model().objects.filter(is_superuser=True):
    print(u.username, u.email, u.is_active)
"
```

### 非交互创建（脚本/CI，可选）

需 Django 支持 `DJANGO_SUPERUSER_*` 环境变量（本项目 Django 4.x 可用）。**勿**把密码写进仓库，仅在当前 shell 临时 export：

```bash
export DJANGO_SUPERUSER_USERNAME=admin
export DJANGO_SUPERUSER_EMAIL=admin@example.com
export DJANGO_SUPERUSER_PASSWORD='仅本次使用的强密码'
python sandbox_site/manage.py createsuperuser --noinput
unset DJANGO_SUPERUSER_PASSWORD
```

若用户名已存在会报错，改用 `changepassword` 或换用户名。

### 常见问题

| 情况 | 处理 |
|------|------|
| `/admin/` 能开但登录失败 | 确认用的是 **createsuperuser** 的用户名，不是 Excel 里的 `writer01` 等 |
| 提示无超户 / 无法登录运营台 | 执行 `createsuperuser` 或检查上表 `is_superuser` |
| 想再建一个超户 | 再次 `createsuperuser`（用户名不可重复） |
| 生产忘记密码 | SSH 上 `changepassword <用户名>`，无需停站 |

---

## 6. 启动 Gunicorn

### 6.1 加载 `.env`（必须）

`manage.py` 会 `load_dotenv`；**`wsgi.py` 不会**。启动前：

```bash
set -a && source .env && set +a
```

| 命令 | 作用 |
|------|------|
| `set -a` | 之后变量自动 export 给子进程 |
| `source .env` | 读入 MYSQL、DEEPSEEK 等 |
| `set +a` | 关闭自动 export |

### 6.2 推荐启动命令（单行）

```bash
gunicorn sandbox_site.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 12 --threads 24 --timeout 180 --access-logfile - --error-logfile -
```

| 参数 | 含义 |
|------|------|
| `0.0.0.0:8000` | 外网可访问 `:8000`（需防火墙放行） |
| `gthread` | 每 worker 多线程，等 LLM 时仍可处理其它请求 |
| `workers 12` | 12 个进程 |
| `threads 24` | 每进程 24 线程（粗算约 288 并发槽） |
| `timeout 180` | 单请求最长 180 秒 |
| `-` 日志 | 打到当前终端 |

一键：

```bash
cd ~/course-sandbox && source venv/bin/activate && set -a && source .env && set +a && gunicorn sandbox_site.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 12 --threads 24 --timeout 180 --access-logfile - --error-logfile -
```

### 6.3 坑：仅 `workers 4` + 默认 sync

约 **4** 个并发槽；多人同时调 DeepSeek 时整站像卡死。务必用 **gthread**。

### 6.4 坑：8000 已被占用

```text
Address already in use / Errno 98
```

旧 Gunicorn 仍在监听。若已用 **systemd**（§6.6），优先：

```bash
sudo systemctl stop course-sandbox.service
ss -lntp | grep 8000 || echo "8000 已空闲"
```

未用 systemd、或需强杀残留时：

```bash
pkill -9 -f "gunicorn sandbox_site.wsgi"
sleep 2
ss -lntp | grep 8000 || echo "8000 已空闲"
```

`Restart=always` 时只 `pkill` 会在数秒内被 systemd 拉起，端口仍占用。

| 部分 | 含义 |
|------|------|
| `pkill` | 按命令行匹配结束进程 |
| `-9` | 强制结束 |
| `-f "gunicorn sandbox_site.wsgi"` | 只杀本沙盘 Gunicorn |

若杀完又出现，检查 **systemd** 是否自动重启：

```bash
systemctl list-units --type=service --state=running | grep -iE 'gunicorn|sandbox|course'
```

### 6.5 坑：Gunicorn 未读 `.env`

网站仍连 SQLite 或账号对不上。检查：

```bash
tr '\0' '\n' < /proc/$(pgrep -f "gunicorn sandbox_site.wsgi" | head -1)/environ | grep MYSQL
```

生产建议用 **systemd** 托管（见 §6.6、§11.5），`EnvironmentFile=/home/ruc/course-sandbox/.env`，日常勿再手动起第二条 Gunicorn。

### 6.6 systemd `course-sandbox.service`（推荐）

R930 上常见单元：`/etc/systemd/system/course-sandbox.service`，`enabled` + `Restart=always` 会占 **8000** 并在进程被杀后自动拉起。

**查看 / 改配置：**

```bash
systemctl status course-sandbox.service
systemctl cat course-sandbox.service
systemctl show course-sandbox.service -p ExecStart --value
```

**建议 `ExecStart`（MySQL + gthread，路径按实际用户目录调整）：**

```ini
[Unit]
Description=course-sandbox gunicorn (MySQL)
After=network.target

[Service]
Type=simple
User=ruc
WorkingDirectory=/home/ruc/course-sandbox
EnvironmentFile=/home/ruc/course-sandbox/.env
ExecStart=/home/ruc/course-sandbox/venv/bin/gunicorn sandbox_site.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers 12 \
  --threads 24 \
  --timeout 180 \
  --access-logfile - \
  --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart course-sandbox.service
journalctl -u course-sandbox.service -n 50 --no-pager
```

| 运维 | 命令 |
|------|------|
| 重启（改 `.env` / 代码后） | `sudo systemctl restart course-sandbox.service` |
| 停止（再手动调试 Gunicorn） | `sudo systemctl stop course-sandbox.service` |
| 开机自启 | `sudo systemctl enable course-sandbox.service` |
| 取消自启 | `sudo systemctl disable course-sandbox.service` |

**勿**在 service `active` 时再前台 `gunicorn`，否则 `Address already in use`。`pkill` 后若端口又出现，多半是 `Restart=always` 拉回——应改 unit 后 `restart`，而不是与 systemd 抢端口。

---

## 7. 访问与验证

| 方式 | URL |
|------|-----|
| 直接 Gunicorn | `http://<服务器IP>:8000/` |
| 登录 | `账号管理.xlsx` 中账号/密码（非 createsuperuser） |

```bash
curl -I http://127.0.0.1:8000/
```

---

## 8. 与开新一局

与 [README §2.3](../README.md) 相同；服务器上先加载 `.env`（见 §11.0），再执行 §11.4 中的 `reset_test_data.py` / `load_accounts`。

---

## 9. 部署检查清单

- [ ] `.env` 含 `MYSQL_HOST`、`MYSQL_DATABASE` 等
- [ ] `ENGINE` 为 `django.db.backends.mysql`（§3.4.3）
- [ ] `mysql -e "SELECT 1"` 与 `SHOW TABLES` 正常（§3.4）
- [ ] `migrate` 完成（含 0016 DROP CHECK）
- [ ] `load_accounts --clear` 成功
- [ ] （可选）`createsuperuser` 或已知 Admin 账号（§5.1）
- [ ] `账号管理.xlsx` 在项目根
- [ ] 启动前 `set -a && source .env && set +a`
- [ ] Gunicorn 使用 `gthread`
- [ ] 防火墙放行 8000（或 Nginx 80）
- [ ] `DEEPSEEK_API_KEY` 有效

---

## 10. 故障速查

| 症状 | 处理 |
|------|------|
| 全班刷不开 | MySQL + gthread；勿 SQLite + 4×sync |
| migrate 3959 | `DROP CHECK 用户_chk_1` 再 migrate |
| 1045 | `ALTER USER` + 改 `.env` 密码；见 §3.4.2 |
| 不确定库是否正常 | 按 §3.4 顺序：`systemctl` → `mysql -e SELECT 1` → Django `check` → `SHOW TABLES` |
| Address already in use | `pkill -9 -f "gunicorn sandbox_site.wsgi"` |
| 账号登不上 | 首页 `/`：检查 `load_accounts`；`/admin/`：检查 §5.1 超户 |
| Admin 密码忘了 | SSH：`changepassword <用户名>`（§5.1） |
| 中文表名在 mysql 里打不出 | 粘贴 SQL 或用 Django shell |

---

## 11. 服务器运维命令（与 README 对照）

[README.md](../README.md) 面向**本地开发**（`uv run`、PowerShell、`runserver`）。**服务器**上业务含义一致，差异只有三点：

| 差异 | 本地 | 服务器 |
|------|------|--------|
| Python 前缀 | `uv run python` | `venv` 激活 + `python`（见 §11.0） |
| 环境变量 | `manage.py` 自动 `load_dotenv` | **每条** `manage.py`/脚本前建议 `set -a && source .env && set +a`；Gunicorn 由 systemd `EnvironmentFile` 注入 |
| Web 服务 | `runserver` | **Gunicorn**（§6.6 **systemd**），勿 `runserver` |

下文路径默认 `~/course-sandbox`（即 `/home/ruc/course-sandbox`）。

### 11.0 每次 SSH 后的公共前缀

维护命令（`migrate`、`load_accounts`、`end_round` 等）在**项目根**执行：

```bash
cd ~/course-sandbox
source venv/bin/activate
set -a && source .env && set +a
```

后文「`python ...`」均指已执行以上三行之后。可复制为别名：

```bash
# 可选：写入 ~/.bashrc
alias csb='cd ~/course-sandbox && source venv/bin/activate && set -a && source .env && set +a'
```

### 11.1 环境与依赖（对照 README §1）

| README（本地） | 服务器 |
|----------------|--------|
| `uv sync` | `cd ~/course-sandbox && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt` |
| 复制 `.env` | `scp` / 手工编辑 `/home/ruc/course-sandbox/.env`（勿用 `(1).env` 文件名） |
| SQLite 默认 | **必须** `.env` 含 `MYSQL_HOST` + `MYSQL_DATABASE`（§2） |

验证数据库引擎：

```bash
csb   # 或 §11.0 三行
python sandbox_site/manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

### 11.2 数据初始化（对照 README §2）

| 步骤 | README | 服务器 |
|------|--------|--------|
| ① 迁移 | `uv run python sandbox_site/manage.py migrate` | `python sandbox_site/manage.py migrate` |
| ② 导账号 | `uv run python ... load_accounts --clear` | `python sandbox_site/manage.py load_accounts --clear` |
| ③ Admin 超户 | `createsuperuser` | 见 **§5.1**（`/admin/`，与 Excel 无关） |

**首次部署（bash 一条龙）：**

```bash
cd ~/course-sandbox && source venv/bin/activate && set -a && source .env && set +a
python sandbox_site/manage.py migrate
# 若 0016 失败，见 §4 DROP CHECK 后再 migrate
python sandbox_site/manage.py load_accounts --clear
sudo systemctl restart course-sandbox.service
```

**`load_accounts` 参数**（与 README §2.1 相同）：

```bash
python sandbox_site/manage.py load_accounts
python sandbox_site/manage.py load_accounts --clear
python sandbox_site/manage.py load_accounts --clear-platform
python sandbox_site/manage.py load_accounts --clear-regulator
python sandbox_site/manage.py load_accounts --file /path/to/账号管理.xlsx
```

Excel 需在项目根 `账号管理.xlsx`（或 `--file`）。Sheet、`关注` 列、同平台校验见 README §2.1。

### 11.3 `sync_fans_count`（对照 README §2.2）

```bash
python sandbox_site/manage.py sync_fans_count
```

### 11.4 `reset_test_data.py`（对照 README §2.3）

```bash
python reset_test_data.py
```

清空一局业务数据、保留四类账号；**会删光关注**。恢复关注需再 `load_accounts`（是否 `--clear` 见 README 表）。

### 11.5 Web 服务（对照 README §3）

| README | 服务器 |
|--------|--------|
| `runserver` | **不要**在生产用；用 systemd |

```bash
sudo systemctl status course-sandbox.service
sudo systemctl restart course-sandbox.service
sudo systemctl stop course-sandbox.service    # 仅调试前
curl -I http://127.0.0.1:8000/               # 本机冒烟；Gunicorn 监听 0.0.0.0 时仍用 127.0.0.1 测
```

学生访问：`http://<服务器IP>:8000/`。登录账号来自 Excel，不是 `createsuperuser`。Admin 见 §5.1。

### 11.2.1 Django Admin 超户（对照 §5.1）

```bash
# 首次
python sandbox_site/manage.py createsuperuser

# 改密
python sandbox_site/manage.py changepassword <用户名>

# 列出超户
python sandbox_site/manage.py shell -c "from django.contrib.auth import get_user_model; [print(u.username) for u in get_user_model().objects.filter(is_superuser=True)]"
```

**改 `.env` 或拉代码后：** `migrate`（若有新迁移）→ `sudo systemctl restart course-sandbox.service`。

### 11.6 Django 管理命令（对照 README §4）

```bash
python sandbox_site/manage.py end_round
python sandbox_site/manage.py help load_accounts
python sandbox_site/manage.py migrate
python sandbox_site/manage.py collectstatic --noinput
python sandbox_site/manage.py shell
```

`end_round` 与平台页「结束本轮」同逻辑（`perform_end_round()`）。

### 11.7 测试与维护脚本（对照 README §6–§7）

| 项 | 建议 |
|----|------|
| `uv run python test/run.py` | **在开发机**跑；服务器课堂机一般不必装全套 pytest |
| 若必须在服务器跑 | `csb` 后 `python test/run.py`（需 dev 依赖已 `pip install`） |
| `allocate_roles.py` / `scripts/replan_accounts.py` | 改 Excel 用；改完 `load_accounts` |

### 11.8 日志（对照 README §8）

```bash
tail -f ~/course-sandbox/logs/simulation_actions.log
journalctl -u course-sandbox.service -f
```

### 11.9 快速对照：我该跑哪条？（服务器）

| 我想… | 服务器命令 |
|--------|------------|
| 第一次部署 | §1–§6 + §11.2 一条龙 → `systemctl enable --now course-sandbox` |
| 换一批学生账号 | 更新 `账号管理.xlsx` → `load_accounts --clear`（§11.0 前缀） |
| 实验结束，保留账号重来一局 | `reset_test_data.py` → 可选 `load_accounts` |
| 关注数不对 | `sync_fans_count` |
| 不打开网页，推进轮次 | `end_round` |
| 更新代码/迁移 | `git pull` → `migrate` → `systemctl restart course-sandbox` |
| 站点卡、多人调 LLM | 检查 `ExecStart` 是否 **gthread**（§6.6） |
| 8000 被占用 | 勿重复 `gunicorn`；`systemctl status` / `stop` 或改 unit 后 `restart` |
| 初始化 / 改 Admin 密码 | §5.1：`createsuperuser` / `changepassword` |
| 本地命令怎么对应 | 本文 §11 + [README §10](../README.md) |
