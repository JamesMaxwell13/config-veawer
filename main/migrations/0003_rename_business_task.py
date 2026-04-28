from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0002_deviceplatformprofile"),
    ]

    operations = [
        migrations.RenameField(
            model_name="networkscenario",
            old_name="business_task",
            new_name="device_task",
        ),
    ]
