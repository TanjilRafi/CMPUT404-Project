from django.db import migrations
import uuid

# https://docs.djangoproject.com/en/6.0/howto/writing-migrations/#migrations-that-add-unique-fields

def gen_uuid(apps, schema_editor):
    Entry = apps.get_model("authors", "Entry")
    db_alias = schema_editor.connection.alias

    # Only fetch PKs so we do not force Django to read drifted columns
    # such as contentType/content_type during the migration.
    pks = list(
        Entry.objects.using(db_alias).values_list("pk", flat=True)
    )

    for pk in pks:
        Entry.objects.using(db_alias).filter(pk=pk, uuid__isnull=True).update(
            uuid=uuid.uuid4()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("authors", "0035_add_entry_uuid"),
    ]

    operations = [
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]