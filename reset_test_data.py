# -*- coding: utf-8 -*-
"""
独立数据清理脚本：清空测试产生的动态数据，保留写手、用户账号。

使用方式：在项目根目录执行  python reset_test_data.py

说明：
- 使用与 Web 应用相同的数据库（settings.DATABASES['default']），对 db.sqlite3 执行真实
  DELETE/UPDATE，数据从磁盘上被删除或更新，并非仅清空 Admin 展示。
- 不修改任何前后端代码、路由、配置；仅操作数据库表数据，不影响功能与并发逻辑。
  建议在无用户请求或低峰时执行，以避免与 Web 进程同时写库时的短暂锁等待。
"""
import os
import sys

# 使用项目根目录并加载 Django 配置以定位同一数据库
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sandbox_site.settings')

import django
django.setup()

from django.db import connection


# 按依赖顺序排列：先删子表/关联表，再删主表。不删除「写手」「用户」表数据。
TABLES_TO_TRUNCATE = [
    '取关拉黑账号问卷调查',
    '切换平台问卷调查',
    '用户文章点赞',
    '用户文章收藏',
    '用户文章阅读完成',
    '文章推送明细',
    '文章推送记录',
    '评论',
    '文章',
    '用户关注写手',
]


def _quote(s):
    """SQLite 标识符加双引号转义。"""
    return '"' + str(s).replace('"', '""') + '"'


def main():
    with connection.cursor() as cursor:
        for table in TABLES_TO_TRUNCATE:
            try:
                q = _quote(table)
                cursor.execute(f'DELETE FROM {q}')
                n = cursor.rowcount
                print(f'DELETE FROM {table}: {n} 行')
            except Exception as e:
                print(f'DELETE FROM {table}: 跳过 ({e})')

        # 将写手、用户的粉丝数归零，与清空后的关注关系一致
        try:
            cursor.execute(f'UPDATE {_quote("写手")} SET {_quote("粉丝数")} = 0')
            print(f'UPDATE 写手 粉丝数=0: {cursor.rowcount} 行')
        except Exception as e:
            print(f'UPDATE 写手 粉丝数: 跳过 ({e})')
        try:
            cursor.execute(f'UPDATE {_quote("用户")} SET {_quote("关注数")} = 0')
            print(f'UPDATE 用户 关注数=0: {cursor.rowcount} 行')
        except Exception as e:
            print(f'UPDATE 用户 关注数: 跳过 ({e})')
        # 模拟轮次重置为 1，下一轮从 1 开始
        try:
            cursor.execute(f'UPDATE {_quote("模拟轮次")} SET {_quote("当前轮次")} = 1 WHERE id = 1')
            print(f'UPDATE 模拟轮次 当前轮次=1: {cursor.rowcount} 行')
        except Exception as e:
            print(f'UPDATE 模拟轮次: 跳过 ({e})')

    print('清理完成。已保留写手、用户账号数据。')


if __name__ == '__main__':
    main()
