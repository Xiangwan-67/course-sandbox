from django.db import migrations, models


def mark_existing_articles_published(apps, schema_editor):
    Article = apps.get_model('accounts', 'Article')
    Article.objects.all().update(is_published=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0051_round_snapshot_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='is_published',
            field=models.BooleanField(default=False, db_index=True, verbose_name='已发布'),
        ),
        migrations.RunPython(mark_existing_articles_published, migrations.RunPython.noop),
    ]
