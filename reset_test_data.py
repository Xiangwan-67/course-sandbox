# -*- coding: utf-8 -*-
"""
独立数据清理脚本：清空沙盘模拟产生的业务数据，保留账号与全局基础配置，便于重新开一局。

使用方式：在项目根目录执行  python reset_test_data.py

保留（不删行）：
- 写手、用户、平台账号、监管机构账号（账号信息）
- 管理员基础配置表（id=1，含写作成本映射等）
- 平台利润权重配置（周期/利润权重类基础配置）

会清空 / 重置：
- 所有文章及依赖的互动、推送、评论、结算、检测与流量记录、举报记录等
- 写手治理通知收件箱、写手通知已读、写手健康分审计
- 平台治理措施、各功能包配置（标题党/流量/举报/收益惩罚）
- 平台绩效方案、平台周期利润
- 监管专项申请与正式行动、抽查结果、巡查申请与结果、罚款申请与生效记录
- 模拟轮次重置为 1；写手粉丝数归零、健康分恢复默认；用户关注数归零

说明：
- 使用与 Web 相同的数据库（settings.DATABASES['default']），执行真实 DELETE/UPDATE。
- MySQL 使用反引号转义标识符；SQLite / PostgreSQL 使用双引号。
- 建议在无并发写库时执行。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sandbox_site.settings')

import django

django.setup()

from django.db import connection


def _sql_ident(name: str) -> str:
    """按数据库方言转义表名/列名。MySQL 用 `...`，SQLite 与 PostgreSQL 用 \"...\""""
    s = str(name)
    if connection.vendor == 'mysql':
        return '`' + s.replace('`', '``') + '`'
    return '"' + s.replace('"', '""') + '"'


# 按外键/依赖顺序：先子表，后父表。表名为 models.Meta.db_table。
TABLES_DELETE_ORDER = [
    # 依赖「平台治理措施」的通知与已读
    '写手治理通知收件箱',
    '写手通知已读',
    '写手健康分变更审计',
    # 依赖「文章」
    '文章收益结算',
    '标题党检测结果',
    '文章流量记录',
    '用户举报记录',
    '取关拉黑账号问卷调查',
    '切换平台问卷调查',
    '用户文章点赞',
    '用户文章收藏',
    '用户文章阅读完成',
    '文章推送明细',
    '文章推送记录',
    '评论',
    '文章',
    # 监管 / 巡查 / 罚款（顺序：子 → 父）
    '平台抽查结果表',
    '监管机构平台巡查表',
    '监管机构罚款记录表',
    '监管专项行动表',
    '监管专项行动申请表',
    '监管机构平台巡查申请表',
    '监管机构罚款申请表',
    # 平台治理与功能包配置（档位先于主配置）
    '平台治理措施记录',
    # 账号健康分相关配置（保留，不清空）：便于清空动态数据后继续沿用既有配置
    '标题党检测配置',
    '流量惩罚配置',
    '用户举报配置',
    '收益惩罚配置',
    '平台绩效方案记录',
    # 周期利润等业务汇总
    '平台周期利润记录',
    # 社交（文章已空）
    '用户关注写手',
]


def main():
    from django.db import transaction

    vendor = connection.vendor
    print(f'数据库后端: {vendor}')

    with transaction.atomic():
        with connection.cursor() as cursor:
            if vendor == 'mysql':
                cursor.execute('SET FOREIGN_KEY_CHECKS = 0')

            try:
                for table in TABLES_DELETE_ORDER:
                    try:
                        q = _sql_ident(table)
                        cursor.execute(f'DELETE FROM {q}')
                        n = cursor.rowcount
                        print(f'DELETE FROM {table}: {n} 行')
                    except Exception as e:
                        print(f'DELETE FROM {table}: 跳过 ({e})')

                for sql, label in [
                    (
                        f'UPDATE {_sql_ident("写手")} SET {_sql_ident("粉丝数")} = 0',
                        'UPDATE 写手 粉丝数=0',
                    ),
                    (
                        f'UPDATE {_sql_ident("写手")} SET {_sql_ident("健康分")} = 100, '
                        f'{_sql_ident("health_tier")} = \'\', '
                        f'{_sql_ident("推流系数")} = 1.0, '
                        f'{_sql_ident("健康分最近更新轮次")} = NULL',
                        'UPDATE 写手 健康分/档位/推流系数 重置',
                    ),
                    (
                        f'UPDATE {_sql_ident("用户")} SET {_sql_ident("关注数")} = 0',
                        'UPDATE 用户 关注数=0',
                    ),
                    (
                        f'UPDATE {_sql_ident("模拟轮次")} SET {_sql_ident("当前轮次")} = 1 WHERE id = 1',
                        'UPDATE 模拟轮次 当前轮次=1',
                    ),
                ]:
                    try:
                        cursor.execute(sql)
                        print(f'{label}: {cursor.rowcount} 行')
                    except Exception as e:
                        print(f'{label}: 跳过 ({e})')
            finally:
                if vendor == 'mysql':
                    cursor.execute('SET FOREIGN_KEY_CHECKS = 1')

    print(
        '清理完成。已保留：写手/用户/平台账号/监管机构账号、'
        '管理员基础配置表、平台利润权重配置。'
    )


if __name__ == '__main__':
    main()
