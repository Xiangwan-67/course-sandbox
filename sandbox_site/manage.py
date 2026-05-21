#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 加载 .env 环境变量（一次性，API key 等非数据库配置）
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(project_root, '.env'))
    except ImportError:
        pass

    # 把项目根目录（课程沙盘）加入路径，便于从 sandbox_site 目录运行也能找到 sandbox_site 包
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sandbox_site.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
