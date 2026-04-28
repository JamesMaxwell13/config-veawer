from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0004_unify_and_uml"),
    ]

    operations = [
        migrations.AddField(
            model_name="configurationbackup",
            name="version_name",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
