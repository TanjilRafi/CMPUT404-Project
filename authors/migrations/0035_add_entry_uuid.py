from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("authors", "0034_node"),
    ]

    operations = [
        migrations.AddField(
            model_name="entry",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, null=True),
        ),
    ]