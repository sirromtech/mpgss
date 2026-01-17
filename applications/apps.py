# applications/apps.py
from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'applications'

    def ready(self):
        # Import signals so they are registered when Django starts
        # Keep import local to avoid side effects at import time
        from . import signals  # noqa: F401
