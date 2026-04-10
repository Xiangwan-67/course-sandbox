# 文章表：删除 标题夸张度、内容相关度；新增 标题夸张度_初始值、标题夸张度_校准值、内容相关度_初始值、内容相关度_校准值

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_user_article_like_collect_read'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='标题夸张度_初始值',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='标题夸张度_校准值',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='内容相关度_初始值',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='内容相关度_校准值',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.RemoveField(
            model_name='article',
            name='标题夸张度',
        ),
        migrations.RemoveField(
            model_name='article',
            name='内容相关度',
        ),
    ]
