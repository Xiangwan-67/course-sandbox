# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_clickbait_judgment_traceability'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='article',
            name='clickbait_detected_at',
        ),
        migrations.RemoveField(
            model_name='article',
            name='auto_rule_executed',
        ),
        migrations.RemoveField(
            model_name='article',
            name='method_auto_rule',
        ),
        migrations.RemoveField(
            model_name='article',
            name='method_user',
        ),
        migrations.AlterField(
            model_name='article',
            name='clickbait_source',
            field=models.CharField(
                blank=True,
                choices=[('auto', '自动检测'), ('user_report', '用户举报')],
                default='',
                max_length=20,
                verbose_name='检测来源',
            ),
        ),
    ]
