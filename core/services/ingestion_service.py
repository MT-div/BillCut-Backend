from decimal import Decimal
from datetime import datetime
from django.utils.timezone import make_aware
from django.core.cache import cache
from core.models import Meter, ConsumptionReading
from django.db import transaction

class IngestionService:

    @staticmethod
    def process_live_reading(meter_id: str, watts: Decimal, timestamp_dt: datetime) -> ConsumptionReading:
        """
        تستقبل قراءة الواط اللحظية، تحسب فارق الوقت بالثواني، تراكم الاستهلاك برمجياً، وتحفظ القراءة الجديدة.
        """
        meter = Meter.objects.get(pk=meter_id)
        last_reading = ConsumptionReading.objects.filter(meter=meter).order_by('timestamp').last()

        if not last_reading:
            cumulative_wh = Decimal('0.00')
        else:
            delta_t_seconds = Decimal(str((timestamp_dt - last_reading.timestamp).total_seconds()))
            if delta_t_seconds < 0:
                delta_t_seconds = Decimal('0.00')

            energy_wh = watts * (delta_t_seconds / Decimal('3600.00'))
            cumulative_wh = last_reading.cumulativeWh + energy_wh

        # تعديل التقريب ليكون بخانتين عشريتين فقط لتتوافق مع قاعدة البيانات
        reading = ConsumptionReading.objects.create(
            meter=meter,
            cumulativeWh=round(cumulative_wh, 2),
            timestamp=timestamp_dt
        )
        return reading

    @staticmethod
    def process_bulk_backfill(meter_id: str, readings_data: list) -> int:
        meter = Meter.objects.get(pk=meter_id)
        readings_to_create = []

        with transaction.atomic():
            ConsumptionReading.objects.filter(meter=meter).delete()
            cache.clear()

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