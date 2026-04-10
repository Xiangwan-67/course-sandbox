# 模拟轮次表 + 文章.轮次字段；结束本轮仅做轮次+1，不删数据

from django.db import migrations, models


def create_initial_round(apps, schema_editor):
    SimulationRound = apps.get_model('accounts', 'SimulationRound')
    SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_article_push_detail'),
    ]

    operations = [
        migrations.CreateModel(
            name='SimulationRound',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('当前轮次', models.PositiveIntegerField(default=1)),
            ],
            options={
                'db_table': '模拟轮次',
                'verbose_name': '模拟轮次',
                'verbose_name_plural': '模拟轮次',
            },
        ),
        migrations.AddField(
            model_name='article',
            name='轮次',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RunPython(create_initial_round, noop),
    ]
