---
name: feature-test-automation
description: Builds end-to-end feature testing deliverables for this project: writes a feature test requirements doc, implements pytest automation, runs tests, and outputs per-case reports with failure reasons. Use when the user asks to test a specific feature, mentions 功能测试需求书/自动化测试/测试报告, or gives an explicit command like "请按功能测试Skill执行：功能名".
---

# Feature Test Automation

## Purpose

在本仓库内，针对用户指定的“功能名称”，自动完成以下全流程：

1. 撰写功能测试需求书（对齐项目现有测试文档风格）
2. 编写自动化测试（pytest + pytest-django）
3. 执行测试并生成报告
4. 按业务口径输出逐用例结果与失败原因

适用于平台治理类功能，也可用于其它模块功能测试落地。

## Trigger

当用户使用如下显式口令时触发本 Skill：

- `请按功能测试Skill执行：<功能名>`
- `按功能测试Skill测试 <功能名>`

如果用户只给“功能名”，先补一句确认后再执行。

## Project Conventions

- 测试目录：`test/`
- 测试运行脚本：`test/run.py`
- 基础 fixture：`test/conftest.py`
- 现有风格样例：
  - `test/tests/test_clickbait_detection.py`
  - `test/tests/test_user_report_detection.py`
- 需求文档风格样例：
  - `平台治理-标题党检测测试.md`
  - `平台治理-用户举报机制测试.md`

## Workflow

### Step 1: Gather feature context

至少读取以下文件并提取“真实实现口径”：

- `系统开发说明.md`
- `平台模块.md`
- `需求说明.md`
- `accounts/models.py`
- `accounts/views.py`
- `accounts/urls.py`
- 对应功能模板页（`templates/accounts/*.html`）

目标：确定接口、模型、日志点、时序、生效轮次、异常分支。

### Step 2: Write feature test requirements doc

文档命名规则（平台治理功能）：

- `平台治理-<功能名>测试.md`

内容结构默认与既有模板一致：

1. 说明
2. 用途
3. 数据
4. 日志
5. 撰写测试用例，并进行自动测试（验收标准 + 测试要求）

必须覆盖：

- 前端
- 后端
- 数据
- 日志
- 常规/特殊/边界/异常

### Step 3: Implement automated tests

在 `test/tests/` 新建或更新目标测试文件，命名建议：

- `test_<feature_slug>.py`

每条业务用例至少包含三层断言：

1. 接口层：状态码、返回体、错误码/文案
2. 数据层：关键表关键字段
3. 日志层：关键事件与关键参数字段

优先复用 `test/conftest.py` fixture 与既有模式；必要时补充最小辅助 fixture。

### Step 4: Ensure report is business-readable

如果 `test/run.py` 已有报告机制，确保报告包含：

- 逐用例结果（通过/失败/跳过）
- 业务口径名称（不是纯技术函数名）
- 失败原因摘要（失败时）
- 产物路径（stdout/stderr/junit/log_excerpt）

必要时修复以下常见问题：

- 旧 `junit.xml` 被误用导致“假通过”或统计污染
- 参数化用例名未映射到业务文案

### Step 5: Execute and verify

优先使用项目虚拟环境运行：

- `& "<repo>/venv/Scripts/python.exe" "test/run.py"`

然后检查：

- `test/reports/report.md`
- `test/reports/junit.xml`
- `test/reports/pytest_stdout.txt`
- `test/reports/pytest_stderr.txt`
- `test/reports/log_excerpt.txt`

若失败，必须说明根因并给修复动作，再重跑直到可交付。

## Output Contract

向用户汇报时使用以下顺序：

1. 本次新增/修改文件列表
2. 测试执行结果（总数、通过、失败、耗时）
3. 关键业务用例结果摘要
4. 失败原因（如有）与修复动作
5. 报告与产物路径
6. 已知风险与后续建议

## Quality Gate

交付前必须满足：

- 需求书已生成且结构完整
- 自动化用例已落库并可重复运行
- 报告包含逐用例结果
- 日志检查覆盖“存在性 + 关键字段完整性”
- 至少一次全量执行通过（或给出明确阻塞原因）

## Notes

- 以代码真实实现为准，不盲从过期需求描述。
- 不使用手测替代自动化结论。
- 不输出“口头通过”，必须给出报告文件路径和可核对证据。
