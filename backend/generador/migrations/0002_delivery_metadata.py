from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("generador", "0001_initial")]
    operations = [
        migrations.AddField(model_name="generacionbackend", name="sha256", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="generacionbackend", name="tamano_bytes", field=models.PositiveBigIntegerField(default=0)),
        migrations.AddField(model_name="generacionbackend", name="metricas", field=models.JSONField(default=dict)),
    ]
