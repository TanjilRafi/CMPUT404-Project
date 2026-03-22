from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("authors", "0036_populate_entry_uuid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entry",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]