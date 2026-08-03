from datetime import date
from django.core.cache import cache

class CacheService:
    """
    خدمة معزولة مخصصة لإدارة مفاتيح الكاش الموجهة للداشبورد والتحليلات (Scoped Cache Invalidation)
    """
    STATIC_DASHBOARD_PREFIX = "dashboard_static_v5"
    STATIC_ANALYTICS_PREFIX = "analytics_static_v1"

    @classmethod
    def get_dashboard_key(cls, meter_id: str, target_date: date) -> str:
        date_str = target_date.strftime('%Y%m%d')
        return f"{cls.STATIC_DASHBOARD_PREFIX}_{meter_id}_{date_str}"

    @classmethod
    def get_analytics_key(cls, meter_id: str, target_date: date) -> str:
        """توليد مفتاح الكاش للبيانات التاريخية والتنبؤية الثابتة لشاشة التحليلات"""
        date_str = target_date.strftime('%Y%m%d')
        return f"{cls.STATIC_ANALYTICS_PREFIX}_{meter_id}_{date_str}"

    @classmethod
    def invalidate_meter_cache(cls, meter_id: str, target_date: date = None) -> None:
        """تصفية كاش الداشبورد والتحليلات الخاص بعداد محدد فقط"""
        if target_date is None:
            target_date = date.today()
        
        cache.delete(cls.get_dashboard_key(meter_id, target_date))
        cache.delete(cls.get_analytics_key(meter_id, target_date))

    @classmethod
    def invalidate_all_caches(cls) -> None:
        """تستخدم فقط عند تغيير التعرفة الحكومية العامة"""
        cache.clear()