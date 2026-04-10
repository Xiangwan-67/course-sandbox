# 文章报酬字段，用于历史文章列表展示

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_simulation_round_and_article_round'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='报酬',
            field=models.IntegerField(default=0),
        ),
    ]
