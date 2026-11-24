from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_blockedip_securityevent_securitystate")]

    operations = [
        migrations.AddField(
            model_name="equipment",
            name="manufactured_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Ishlab chiqarilgan yili"),
        ),
    ]
