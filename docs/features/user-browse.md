# 用户浏览与互动

**最后更新：** 2026-05-21

---

## 1. 用途

用户登录后切换/浏览各平台内容流（关注列表 + 发现列表），阅读文章并进行点赞、收藏、读毕、关注、举报、评论；行为更新 `Article` 统计字段。

---

## 2. 触发链

```
/user/                              user_home
/user/platform-check/               user_platform_check        POST 切换前检查
/user/switch-platform/              user_switch_platform       POST 改所属平台 + 冷却
/user/browse/<platform_id>/         user_browse                关注/发现列表（ArticlePush）
/user/article/<id>/                 user_article_view          点击量 +1，进入详情
/user/article/<id>/like|collect|... POST JSON 互动
```

列表数据来自 **`ArticlePush`**（推送记录），非直接扫全表 `Article`。

---

## 3. 核心符号

| 类型 | 名称 |
|------|------|
| 视图 | `user_home`, `user_platform_check`, `user_switch_platform`, `user_browse`, `user_article_view`, `user_article_like`, `user_article_collect`, `user_article_read_complete`, `user_article_follow`, `user_article_unfollow`, `user_article_report`, `user_article_add_comment` |
| 辅助 | `_require_user_article`, `_normalize_platform_id`, `_submit_user_report` |
| 模型 | `UserAccount`, `ArticlePush`, `Article`, `UserFollowWriter`, `UserArticleLike`, `UserArticleCollect`, `UserArticleReadComplete`, `ArticleReport`, `Comment` |

---

## 4. 业务规则（当前真相）

### 4.1 浏览列表 `user_browse`

- 参数 `platform_id` 须合法（`platform_scope.normalize_platform_id`）。
- 仅展示 **推送给当前用户** 且 **`ArticlePush.平台 == platform_id`** 且 **`Article.轮次 == 当前轮次`** 的文章。
- `列表类型=0` → 关注列表；`列表类型=1` → 发现列表；按 `文章__创建时间` 升序。
- 过滤无标题文章。Session 记录 `user_browse_platform_id`、`visited_article_ids`（已读标题变灰）。

### 4.2 平台切换

- `user_switch_platform` 修改 `UserAccount.所属平台`，并设置 `禁止登录截止时间`（冷却期内无法登录）。
- 切换可能触发 `PlatformSwitchSurvey`（见模型与视图 POST 字段）。

### 4.3 文章详情与互动

- `user_article_view`：`点击量 += 1`。
- 点赞/收藏/读毕：对应表去重创建，更新 `Article` 上 `点赞量` 等计数。
- 关注/取关：更新 `UserFollowWriter`、写手 `粉丝数`、用户 `关注数`。
- 举报：`user_article_report` → `_submit_user_report`；需治理包 `user_report`；结束本轮 `_process_article_reports` 统一处理阈值。
- 评论：`Comment` 关联 `Article`。

### 4.4 与推送的关系

- 用户只能看到已被 `_do_article_push` 写入 `ArticlePush` 的当前轮文章。
- 粉丝见关注列表；非粉丝若未被抽样进发现列表则看不到该文。

---

## 5. 平台 / 轮次依赖

| 依赖 | 说明 |
|------|------|
| `UserAccount.所属平台` | 登录后默认浏览上下文；举报记录带 platform_id |
| `ArticlePush.平台` | 浏览的 platform_id 与推送时写入一致 |
| `SimulationRound` | 仅当前轮文章出现在列表 |

---

## 6. 相关测试

- `test/tests/test_user_report_detection.py`
- `test/tests/test_smoke.py`
- `test/mega_sim/`

---

## 7. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-21 | 初版文档 |
