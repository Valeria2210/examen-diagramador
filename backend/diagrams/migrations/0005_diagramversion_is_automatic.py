from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0004_alter_projectmember_role_alter_projectshare_role_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="diagramversion",
            name="is_automatic",
            field=models.BooleanField(default=False),
        ),
    ]
