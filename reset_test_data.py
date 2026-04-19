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
- 平台治理措施、各功能包配置（标题党/流量/举报/收益惩罚）、账号健康分配置与档位
- 平台绩效方案、平台周期利润
- 监管专项申请与正式行动、抽查结果、巡查申请与结果、罚款申请与生效记录
- 模拟轮次重置为 1；写手粉丝数归零、健康分恢复默认；用户关注数归零

说明：
- 使用与 Web 相同的数据库（settings.DATABASES['default']），对 SQLite 执行真实 DELETE/UPDATE。
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


def _quote(s):
    return '"' + str(s).replace('"', '""') + '"'


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
    '账号健康分档位配置',
    '账号健康分配置',
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

    with transaction.atomic():
        with connection.cursor() as cursor:
            for table in TABLES_DELETE_ORDER:
                try:
                    q = _quote(table)
                    cursor.execute(f'DELETE FROM {q}')
                    n = cursor.rowcount
                    print(f'DELETE FROM {table}: {n} 行')
                except Exception as e:
                    print(f'DELETE FROM {table}: 跳过 ({e})')

            for sql, label in [
                (f'UPDATE {_quote("写手")} SET {_quote("粉丝数")} = 0', 'UPDATE 写手 粉丝数=0'),
                (
                    f'UPDATE {_quote("写手")} SET {_quote("健康分")} = 100, '
                    f'{_quote("health_tier")} = \'\', '
                    f'{_quote("推流系数")} = 1.0, '
                    f'{_quote("健康分最近更新轮次")} = NULL',
                    'UPDATE 写手 健康分/档位/推流系数 重置',
                ),
                (f'UPDATE {_quote("用户")} SET {_quote("关注数")} = 0', 'UPDATE 用户 关注数=0'),
                (
                    f'UPDATE {_quote("模拟轮次")} SET {_quote("当前轮次")} = 1 WHERE id = 1',
                    'UPDATE 模拟轮次 当前轮次=1',
                ),
            ]:
                try:
                    cursor.execute(sql)
                    print(f'{label}: {cursor.rowcount} 行')
                except Exception as e:
                    print(f'{label}: 跳过 ({e})')

    print(
        '清理完成。已保留：写手/用户/平台账号/监管机构账号、'
        '管理员基础配置表、平台利润权重配置。'
    )


if __name__ == '__main__':
    main()
