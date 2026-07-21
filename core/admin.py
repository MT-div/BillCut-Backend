from django.contrib import admin
from .models import (
    User, Meter, UserMeterPreference, Budget, 
    ConsumptionReading, DailyForecast, MonthlyForecast, 
    Notification, NotificationSettings, TariffVersion, TariffTier
)

# تسجيل الكيانات لكي تظهر وتدار بالكامل من لوحة التحكم الرسومية
admin.site.register(User)
admin.site.register(Meter)
admin.site.register(UserMeterPreference)
admin.site.register(Budget)
admin.site.register(ConsumptionReading)
admin.site.register(DailyForecast)
admin.site.register(MonthlyForecast)
admin.site.register(Notification)
admin.site.register(NotificationSettings)
admin.site.register(TariffVersion)
admin.site.register(TariffTier)