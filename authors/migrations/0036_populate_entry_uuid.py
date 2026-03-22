from django.db import migrations
import uuid

# https://docs.djangoproject.com/en/6.0/howto/writing-migrations/#migrations-that-add-unique-fields

def gen_uuid(apps, schema_editor):
    Entry = apps.get_model("authors", "entry")
    for row in Entry.objects.all():
        row.uuid = uuid.uuid4()
        row.save(update_fields=["uuid"])


class Migration(migrations.Migration):
    dependencies = [
        ("authors", "0035_add_entry_uuid"),
    ]

    operations = [
        # omit reverse_code=... if you don't want the migration to be reversible.
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]