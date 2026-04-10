# Generated manually for UserArticleLike, UserArticleCollect, UserArticleReadComplete

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_writer_fans_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserArticleLike',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('用户', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='文章点赞记录', to='accounts.useraccount')),
                ('文章', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='点赞用户记录', to='accounts.article')),
            ],
            options={
                'db_table': '用户文章点赞',
                'unique_together': {('用户', '文章')},
            },
        ),
        migrations.CreateModel(
            name='UserArticleCollect',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('用户', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='文章收藏记录', to='accounts.useraccount')),
                ('文章', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='收藏用户记录', to='accounts.article')),
            ],
            options={
                'db_table': '用户文章收藏',
                'unique_together': {('用户', '文章')},
            },
        ),
        migrations.CreateModel(
            name='UserArticleReadComplete',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('用户', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='文章阅读完成记录', to='accounts.useraccount')),
                ('文章', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='阅读完成用户记录', to='accounts.article')),
            ],
            options={
                'db_table': '用户文章阅读完成',
                'unique_together': {('用户', '文章')},
            },
        ),
    ]
