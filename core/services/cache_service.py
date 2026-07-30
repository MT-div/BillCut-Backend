from datetime import date
from django.core.cache import cache

class CacheService:
    """
    خدمة معزولة مخصصة لإدارة توليد وتصفية المفاتيح المؤقتة (Cache Keys)
    تطبق مبدأ Single Responsibility لمنع إتلاف الكاش الإجمالي للبرنامج.
    """
    
    STATIC_DASHBOARD_PREFIX = "dashboard_static_v5"

    @classmethod
    def get_dashboard_key(cls, meter_id: str, target_date: date) -> str:
        """توليد مفتاح الكاش الفريد للوحة التحكم الخاصة بعداد معين وتاريخ محدد"""
        date_str = target_date.strftime('%Y%m%d')
        return f"{cls.STATIC_DASHBOARD_PREFIX}_{meter_id}_{date_str}"

    @classmethod
    def invalidate_meter_dashboard_cache(cls, meter_id: str, target_date: date = None) -> None:
        """تصفية الكاش الخاص بعداد محدد فقط"""
        if target_date is None:
            target_date = date.today()
        
        cache_key = cls.get_dashboard_key(meter_id, target_date)
        cache.delete(cache_key)

    @classmethod
    def invalidate_all_caches(cls) -> None:
        """تستخدم فقط في الحالات السيادية الخاصة بمدير النظام (مثل تحديث التعرفة العامة)"""
        cache.clear()