from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # تسجيل وتفعيل مستمعي نمط المراقب (Observer Pattern Listeners)
        import core.events.listeners