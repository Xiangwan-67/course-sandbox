# -*- coding: utf-8 -*-
from django.db import migrations, models


def backfill_clickbait_auto_executed(apps, schema_editor):
    Article = apps.get_model('accounts', 'Article')
    Result = apps.get_model('accounts', 'ClickbaitDetectionResult')
    auto_article_ids = (
        Result.objects.filter(判定来源='auto')
        .values_list('文章_id', flat=True)
        .distinct()
    )
    Article.objects.filter(pk__in=auto_article_ids).update(clickbait_auto_executed=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0049_simplify_article_clickbait_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='clickbait_auto_executed',
            field=models.BooleanField(
                default=False,
                verbose_name='标题党自动检测已执行',
            ),
        ),
        migrations.RunPython(backfill_clickbait_auto_executed, migrations.RunPython.noop),
    ]
