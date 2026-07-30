from core.models import Meter, UserMeterPreference


from django.core.cache import cache # استيراد الكاش
from core.services.cache_service import CacheService

class MeterService:

    @staticmethod
    def add_new_meter(meter_id: str) -> Meter:
        return Meter.objects.create(meterId=meter_id)

    @staticmethod
    def delete_meter(meter_id: str) -> None:
        meter = Meter.objects.get(pk=meter_id)
        meter.delete()

    @staticmethod
    def update_user_meter_preference(preference_id: int, alias: str = None, is_default: bool = None) -> UserMeterPreference:
        pref = UserMeterPreference.objects.get(pk=preference_id)
        
        if alias is not None:
            pref.alias = alias
            
        if is_default is not None:
            if is_default:
                UserMeterPreference.objects.filter(user=pref.user).update(isDefault=False)
            pref.isDefault = is_default
            
        pref.save()

        # حل مشكلة الكاش: تصفير الكاش السريع فوراً بمجرد تعديل اسم العداد أو حالته الافتراضية
        CacheService.invalidate_meter_dashboard_cache(str(pref.meter.meterId))
        
        return pref