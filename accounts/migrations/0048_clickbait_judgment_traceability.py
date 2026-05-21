# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0047_add_platform_to_article_push'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='auto_rule_executed',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='clickbait_source',
            field=models.CharField(
                blank=True,
                choices=[('auto', '自动检测'), ('user_report', '用户举报')],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='clickbaitdetectionresult',
            name='判定来源',
            field=models.CharField(
                choices=[
                    ('auto', '自动检测'),
                    ('user_report', '用户举报'),
                    ('patrol', '平台巡查'),
                ],
                default='auto',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='clickbaitdetectionresult',
            name='判定阈值X',
            field=models.IntegerField(default=4),
        ),
        migrations.AddField(
            model_name='clickbaitdetectionresult',
            name='判定阈值Y',
            field=models.IntegerField(default=3),
        ),
        migrations.AddField(
            model_name='clickbaitdetectionresult',
            name='config_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
