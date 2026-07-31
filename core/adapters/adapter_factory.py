from .base_adapter import BaseIngestionAdapter
from .concrete_adapters import InstantWattsAdapter, DirectKWhAdapter, VoltAmpereAdapter

class IngestionAdapterFactory:
    """
    مصنع اختيار المحول (Adapter Factory / Dispatcher)
    يفحص طبيعة الحمولة المرسلة أو نوع الجهاز ويختار المحول المناسب لها تلقائياً.
    """
    @classmethod
    def get_adapter(cls, payload: dict, hardware_type: str = None) -> BaseIngestionAdapter:
        if hardware_type == 'DIRECT_KWH' or 'kwh' in payload or 'cumulativeKWh' in payload:
            return DirectKWhAdapter()
        elif hardware_type == 'VOLT_AMP' or ('voltage' in payload and 'current' in payload):
            return VoltAmpereAdapter()
        else:
            # الخيار الافتراضي: العدادات اللحظية بالواط
            return InstantWattsAdapter()