from decimal import Decimal
from datetime import datetime
from django.utils.timezone import make_aware
from django.core.cache import cache
from django.db import transaction
from core.models import Meter, ConsumptionReading
from core.adapters.adapter_factory import IngestionAdapterFactory
from core.services.cache_service import CacheService

class IngestionService:

    @staticmethod
    def process_live_reading(meter_id: str, payload: dict, timestamp_dt: datetime, hardware_type: str = None) -> ConsumptionReading:
        """
        تستقبل حمولة البيانات بأية صيغة، تختار المحول المناسب حياً (Adapter Pattern)،
        وتسجل القراءة بنظافة عالية في قواعد البيانات.
        """
        meter = Meter.objects.get(pk=meter_id)
        last_reading = ConsumptionReading.objects.filter(meter=meter).order_by('timestamp').last()

        # 1. اختيار المحول المناسب تلقائياً عبر المصنع وتحويل الحمولة لـ DTO موحد
        adapter = IngestionAdapterFactory.get_adapter(payload, hardware_type)
        standard_dto = adapter.parse_payload(payload, last_reading, timestamp_dt)

        # 2. الحفظ النظيف في قاعدة البيانات
        reading = ConsumptionReading.objects.create(
            meter=meter,
            cumulativeWh=standard_dto.cumulativeWh,
            timestamp=standard_dto.timestamp
        )
        return reading

    @staticmethod
    def process_bulk_backfill(meter_id: str, readings_data: list) -> int:
        meter = Meter.objects.get(pk=meter_id)
        readings_to_create = []

        with transaction.atomic():
            ConsumptionReading.objects.filter(meter=meter).delete()
            CacheService.invalidate_meter_dashboard_cache(meter_id)

            for item in readings_data:
                ts = datetime.fromtimestamp(item['timestamp'])
                readings_to_create.append(
                    ConsumptionReading(
                        meter=meter,
                        cumulativeWh=Decimal(str(item['cumulativeWh'])),
                        timestamp=make_aware(ts)
                    )
                )
            
            ConsumptionReading.objects.bulk_create(readings_to_create)
            
        return len(readings_to_create)