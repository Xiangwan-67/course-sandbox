# -*- coding: utf-8 -*-
from decimal import Decimal

from django.db import migrations, models


def default_writing_cost_map():
    return {'1': 1, '2': 2, '3': 3, '4': 4, '5': 5}


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0038_writer_governance_notice'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminbaseconfig',
            name='写作成本映射',
            field=models.JSONField(blank=True, default=default_writing_cost_map),
        ),
        migrations.RenameField(
            model_name='platformperformancescheme',
            old_name='w4_satisfaction',
            new_name='w4_writing_cost',
        ),
        migrations.RenameField(
            model_name='articlerevenuesettlement',
            old_name='满意度均分',
            new_name='写作成本数值',
        ),
        migrations.AddField(
            model_name='articlerevenuesettlement',
            name='因子_点击量',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18),
        ),
        migrations.AddField(
            model_name='articlerevenuesettlement',
            name='因子_阅读完成',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18),
        ),
        migrations.AddField(
            model_name='articlerevenuesettlement',
            name='因子_收藏',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18),
        ),
        migrations.AddField(
            model_name='articlerevenuesettlement',
            name='因子_写作成本',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18),
        ),
    ]
