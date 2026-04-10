# 用户表「粉丝数」改名为「关注数」（表示该用户关注的写手数量）

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_article_报酬'),
    ]

    operations = [
        migrations.RenameField(
            model_name='useraccount',
            old_name='粉丝数',
            new_name='关注数',
        ),
    ]
