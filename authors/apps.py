from django.apps import AppConfig


class AuthorsConfig(AppConfig):
    name = "authors"

    def ready(self):
        # Import signals to ensure they’re registered
        import authors.signals
