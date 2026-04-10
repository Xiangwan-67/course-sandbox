# 文章推送明细表：记录每篇文章推送给哪些用户、该用户是否为写手粉丝

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_writer_platform_and_article_push'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticlePushDetail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('是否粉丝', models.BooleanField(default=False)),
                ('文章', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='推送明细', to='accounts.article')),
                ('用户', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='被推送文章明细', to='accounts.useraccount')),
            ],
            options={
                'db_table': '文章推送明细',
                'verbose_name': '文章推送明细',
                'verbose_name_plural': '文章推送明细',
                'unique_together': {('文章', '用户')},
            },
        ),
    ]
