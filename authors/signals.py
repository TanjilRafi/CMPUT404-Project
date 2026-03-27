from django.db.models import signals
from django.dispatch import receiver
from .models import Author, Inbox

# https://stackoverflow.com/questions/1652550/can-django-automatically-create-a-related-one-to-one-model, Accessed March 21, 2026
# Automatically creates an inbox for every new author
def create_inbox_for_author(sender, instance, created, **kwargs):
    """Create ModelB for every new ModelA."""
    if created:
        Inbox.objects.get_or_create(author=instance)

signals.post_save.connect(create_inbox_for_author, sender=Author, weak=False,
                          dispatch_uid='models.create_model_b')