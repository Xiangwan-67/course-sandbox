## 标题党检测自动化测试

### 依赖
在虚拟环境中安装测试依赖（仅需一次）：

```bash
pip install -r test/requirements.txt
```

### 运行
在项目虚拟环境中执行：

```bash
python test/run.py
```

### 产物
- `test/reports/report.md`：测试报告（汇总用例结果、失败原因与改进建议）
- `test/reports/junit.xml`：pytest 生成的 JUnit XML
- `test/reports/log_excerpt.txt`：本次测试关键日志摘录（如有）
- `test/reports/pytest_stdout.txt` / `pytest_stderr.txt`：pytest 原始输出

### 备注
- 测试使用独立 sqlite 文件（默认：项目根目录下 `.pytest/sandbox_pytest.sqlite3`，避免与开发库 `db.sqlite3` 争用）。

