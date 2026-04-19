# -*- coding: utf-8 -*-
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0039_writing_cost_and_settlement_factors'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='platformperformancescheme',
            name='w4_writing_cost',
        ),
        migrations.RemoveField(
            model_name='articlerevenuesettlement',
            name='w4',
        ),
        migrations.AddField(
            model_name='articlerevenuesettlement',
            name='写作成本系数',
            field=models.DecimalField(decimal_places=4, default=Decimal('-1'), max_digits=10),
        ),
    ]
