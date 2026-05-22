# Generated manually for round snapshot tables

from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0050_article_clickbait_auto_executed'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoundSnapshotBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_num', models.PositiveIntegerField(unique=True, verbose_name='模拟轮次')),
                ('captured_at', models.DateTimeField(auto_now_add=True, verbose_name='快照时间')),
                ('trigger', models.CharField(choices=[('end_round', '结束本轮'), ('manual', '手工')], default='end_round', max_length=32)),
            ],
            options={
                'verbose_name': '轮次快照批次',
                'verbose_name_plural': '轮次快照批次',
                'db_table': '轮次快照批次',
                'ordering': ['-round_num'],
            },
        ),
        migrations.CreateModel(
            name='RoundSnapshotPlatform',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_num', models.PositiveIntegerField(db_index=True, verbose_name='模拟轮次')),
                ('platform_id', models.IntegerField(verbose_name='平台编号')),
                ('user_count', models.PositiveIntegerField(default=0, verbose_name='用户数')),
                ('clickbait_count_article_field', models.PositiveIntegerField(default=0, verbose_name='标题党篇数(Article字段)')),
                ('clickbait_count_by_rule', models.PositiveIntegerField(default=0, verbose_name='标题党篇数(规则重算)')),
                ('clickbait_count_unjudged', models.PositiveIntegerField(default=0, verbose_name='未判定篇数')),
                ('rule_threshold_x', models.IntegerField(default=4, verbose_name='规则阈值X')),
                ('rule_threshold_y', models.IntegerField(default=3, verbose_name='规则阈值Y')),
                ('cycle_index', models.PositiveIntegerField(blank=True, null=True, verbose_name='周期序号')),
                ('cycle_profit_total', models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True, verbose_name='周期利润')),
                ('cycle_profit_record', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='轮次快照', to='accounts.platformcycleprofitrecord', verbose_name='周期利润记录')),
            ],
            options={
                'verbose_name': '轮次快照_平台',
                'verbose_name_plural': '轮次快照_平台',
                'db_table': '轮次快照_平台',
                'ordering': ['round_num', 'platform_id'],
                'unique_together': {('round_num', 'platform_id')},
            },
        ),
        migrations.CreateModel(
            name='RoundSnapshotWriter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_num', models.PositiveIntegerField(db_index=True, verbose_name='模拟轮次')),
                ('writer_account', models.CharField(db_index=True, max_length=64, verbose_name='写手账号')),
                ('platform_id', models.IntegerField(verbose_name='平台编号')),
                ('fan_count', models.PositiveIntegerField(default=0, verbose_name='粉丝数')),
                ('round_revenue_total', models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18, verbose_name='本轮最终收益合计')),
                ('round_revenue_raw', models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18, verbose_name='本轮原始收益合计')),
                ('revenue_penalty_deduction', models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=18, verbose_name='收益惩罚扣减额')),
                ('revenue_penalty_article_count', models.PositiveIntegerField(default=0, verbose_name='收益惩罚文章数')),
                ('traffic_penalty_article_count', models.PositiveIntegerField(default=0, verbose_name='流量惩罚文章数')),
                ('health_score', models.IntegerField(default=100, verbose_name='健康分')),
                ('health_tier', models.CharField(blank=True, default='', max_length=50, verbose_name='健康档位')),
                ('push_coefficient', models.DecimalField(decimal_places=4, default=Decimal('1.0000'), max_digits=5, verbose_name='推流系数')),
            ],
            options={
                'verbose_name': '轮次快照_写手',
                'verbose_name_plural': '轮次快照_写手',
                'db_table': '轮次快照_写手',
                'ordering': ['round_num', 'writer_account'],
                'unique_together': {('round_num', 'writer_account')},
            },
        ),
        migrations.CreateModel(
            name='RoundSnapshotWriterFan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_num', models.PositiveIntegerField(db_index=True, verbose_name='模拟轮次')),
                ('writer_account', models.CharField(db_index=True, max_length=64, verbose_name='写手账号')),
                ('user_account', models.CharField(db_index=True, max_length=64, verbose_name='用户账号')),
                ('user_platform_id', models.IntegerField(default=0, verbose_name='用户所属平台')),
            ],
            options={
                'verbose_name': '轮次快照_写手粉丝',
                'verbose_name_plural': '轮次快照_写手粉丝',
                'db_table': '轮次快照_写手粉丝',
                'ordering': ['round_num', 'writer_account', 'user_account'],
                'unique_together': {('round_num', 'writer_account', 'user_account')},
            },
        ),
    ]
