# 路由速查

> **权威源：** [`accounts/urls.py`](../accounts/urls.py)、[`sandbox_site/urls.py`](../sandbox_site/urls.py)。本文供 AI/新人速查；改路由后须同步本文。

**命名空间：** `app_name = 'accounts'` → 反向解析 `accounts:<name>`

**最后更新：** 2026-05-21

---

## 根路由（sandbox_site）

| 路径 | name | 处理 |
|------|------|------|
| `admin/sandbox-ops/` | `admin_sandbox_ops` | 沙盘运营台（`admin_operations.sandbox_operations_dashboard`） |
| `admin/sandbox-monitor/` | `admin_sandbox_monitor` | 模拟看板（`admin_monitor.sandbox_monitor_dashboard`） |
| `admin/sandbox-monitor/api/writers/` | `admin_sandbox_monitor_api_writers` | 看板 JSON：写手完稿（`?round=`） |
| `admin/sandbox-monitor/api/governance/` | `admin_sandbox_monitor_api_governance` | 看板 JSON：治理包 + 本轮巡查统计（`?round=`） |
| `admin/` | — | Django Admin |
| `` | — | `include('accounts.urls')` → 下表 |

---

## A. 公共

| 路径 | name | 视图 | 方法 | 说明 |
|------|------|------|------|------|
| `/` | `login` | `login_view` | GET/POST | 登录页；POST 按写手→用户→平台→监管顺序校验 |
| `/logout/` | `logout` | `logout_view` | GET | 清空 session |
| `/end-round/` | `end_round` | `end_round` | **POST** | **JSON** 结束本轮（`perform_end_round`） |

---

## B. 写手 `writer/`

### 页面（GET HTML）

| 路径 | name | 视图 |
|------|------|------|
| `/writer/` | `writer_home` | `writer_home` |
| `/writer/history/` | `writer_article_history` | `writer_article_history` |
| `/writer/notices/` | `writer_notices` | `writer_notices` |
| `/writer/article/<id>/` | `article_detail` | `article_detail` |

### API（POST，多为 JSON）

| 路径 | name | 视图 | 说明 |
|------|------|------|------|
| `/writer/start-article/` | `writer_start_article` | `writer_start_article` | 创建 `Article`，`session['article_id']` |
| `/writer/generate-titles/` | `writer_generate_titles` | `writer_generate_titles` | LLM 生成 3 标题 |
| `/writer/select-title/` | `writer_select_title` | `writer_select_title` | 选定标题与夸张度校准值 |
| `/writer/generate-bodies/` | `writer_generate_bodies` | `writer_generate_bodies` | LLM 生成 3 正文 |
| `/writer/select-body/` | `writer_select_body` | `writer_select_body` | **发布终点**：标题党检测、健康分、**推送** |
| `/writer/notices/<id>/read/` | `writer_notice_read` | `writer_notice_read` | 通知已读 |
| `/writer/health-log/<id>/confirm/` | `writer_health_log_confirm` | `writer_health_log_confirm` | 健康分弹窗确认 |

---

## C. 用户 `user/`

### 页面

| 路径 | name | 视图 |
|------|------|------|
| `/user/` | `user_home` | `user_home` |
| `/user/browse/<platform_id>/` | `user_browse` | `user_browse` |
| `/user/article/<id>/` | `user_article_view` | `user_article_view` |

### API（POST JSON 为主）

| 路径 | name | 视图 | 说明 |
|------|------|------|------|
| `/user/platform-check/` | `user_platform_check` | `user_platform_check` | 切换前检查 |
| `/user/switch-platform/` | `user_switch_platform` | `user_switch_platform` | 切换所属平台 + 冷却 |
| `/user/article/<id>/like/` | `user_article_like` | `user_article_like` | 点赞 |
| `/user/article/<id>/collect/` | `user_article_collect` | `user_article_collect` | 收藏 |
| `/user/article/<id>/read-complete/` | `user_article_read_complete` | `user_article_read_complete` | 阅读完成 |
| `/user/article/<id>/follow/` | `user_article_follow` | `user_article_follow` | 关注写手 |
| `/user/article/<id>/unfollow/` | `user_article_unfollow` | `user_article_unfollow` | 取关 |
| `/user/article/<id>/report/` | `user_article_report` | `user_article_report` | 举报 |
| `/user/article/<id>/comment/` | `user_article_add_comment` | `user_article_add_comment` | 评论 |

---

## D. 平台 `platform/`

### 页面

| 路径 | name | 视图 |
|------|------|------|
| `/platform/` | `platform_home` | `platform_home` |
| `/platform/governance/` | `platform_governance` | `platform_governance` |
| `/platform/governance/clickbait-detection/` | `platform_clickbait_detection` | 标题党参数页 |
| `/platform/governance/traffic-penalty/` | `platform_traffic_penalty` | 流量惩罚参数 |
| `/platform/governance/report/` | `platform_report` | 用户举报参数 |
| `/platform/governance/revenue-penalty/` | `platform_revenue_penalty` | 收益惩罚参数 |
| `/platform/round-result/` | `platform_round_result` | 轮次结果 |
| `/platform/performance/` | `platform_performance` | 绩效方案 |
| `/platform/platform-patrol/` | `platform_self_patrol` | 平台自查 |

### API（POST）

| 路径 | name | 说明 |
|------|------|------|
| `/platform/governance/publish/` | `platform_governance_publish` | 提交治理措施发布（待审） |
| `/platform/governance/cancel/` | `platform_governance_cancel` | 申请取消措施 |
| `/platform/governance/clickbait-detection/save/` | `platform_clickbait_detection_save` | 保存标题党配置 |
| `/platform/governance/traffic-penalty/save/` | `platform_traffic_penalty_save` | 保存流量惩罚配置 |
| `/platform/governance/report/save/` | `platform_report_save` | 保存举报配置 |
| `/platform/governance/revenue-penalty/save/` | `platform_revenue_penalty_save` | 保存收益惩罚配置 |
| `/platform/performance/apply/` | `platform_performance_apply` | 申请绩效方案 |
| `/platform/performance/submit/` | `platform_performance_submit` | 提交绩效方案 |
| `/platform/platform-patrol/submit/` | `platform_self_patrol_submit` | 提交平台自查 |

---

## E. 监管 `regulator/`

### 页面

| 路径 | name | 视图 |
|------|------|------|
| `/regulator/` | `regulator_home` | `regulator_home` |
| `/regulator/special-action/` | `regulator_special_action` | 专项行动 |
| `/regulator/platform-patrol/` | `regulator_platform_patrol` | 平台巡查 |
| `/regulator/platform-spot-check/<pk>/` | `platform_spot_check_detail` | 抽查详情 |
| `/regulator/platform-spot-check/<pk>/open/` | `platform_spot_check_open` | 标记已查看 |

### API（POST）

| 路径 | name | 视图 |
|------|------|------|
| `/regulator/special-action/submit/` | `regulator_special_action_submit` | 提交专项行动申请 |
| `/regulator/platform-patrol/submit/` | `regulator_platform_patrol_submit` | 提交巡查申请 |
| `/regulator/fine/submit/` | `regulator_fine_submit` | 提交罚款申请 |

---

## 角色与前缀对照

| 前缀 | session role | 典型首页 |
|------|--------------|----------|
| `writer/` | `writer` | `accounts:writer_home` |
| `user/` | `user` | `accounts:user_home` |
| `platform/` | `platform` | `accounts:platform_home` |
| `regulator/` | `regulator` | `accounts:regulator_home` |
