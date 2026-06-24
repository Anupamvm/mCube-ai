from django.apps import AppConfig


class InvestmentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.investments'
    verbose_name = 'Family Portfolio Intelligence'

    def ready(self):
        pass
