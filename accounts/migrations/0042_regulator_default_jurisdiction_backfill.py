# Generated manually: 旧数据无辖区时默认 [0,1] 以保持与双平台时期行为一致

from django.db import migrations


def forwards(apps, schema_editor):
    RegulatorAccount = apps.get_model('accounts', 'RegulatorAccount')
    for row in RegulatorAccount.objects.all():
        raw = getattr(row, '负责平台编号列表', None)
        if raw is None or len(raw) == 0:
            row.负责平台编号列表 = [0, 1]
            row.save(update_fields=['负责平台编号列表'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0041_regulator_jurisdiction_platforms'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
