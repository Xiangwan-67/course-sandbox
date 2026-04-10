# 写手表新增 所属平台；新增 文章推送记录 表

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_article_title_content_initial_calibrated'),
    ]

    operations = [
        migrations.AddField(
            model_name='writeraccount',
            name='所属平台',
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name='ArticlePush',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('列表类型', models.PositiveSmallIntegerField()),
                ('文章', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='推送记录', to='accounts.article')),
                ('用户', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='被推送文章', to='accounts.useraccount')),
            ],
            options={
                'db_table': '文章推送记录',
                'ordering': ['文章__创建时间'],
                'unique_together': {('文章', '用户')},
            },
        ),
    ]
