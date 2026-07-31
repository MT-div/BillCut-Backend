from decimal import Decimal
from datetime import datetime, date
from django.utils.timezone import make_aware
from django.db import transaction
from django.db.models import F
from core.models import Meter, ConsumptionReading, DailyConsumptionSummary
from core.adapters.adapter_factory import IngestionAdapterFactory
from core.services.cache_service import CacheService

class IngestionService:

    @staticmethod
    def process_live_reading(meter_id: str, payload: dict, timestamp_dt: datetime, hardware_type: str = None) -> ConsumptionReading:
        """
        1. يحفظ القراءة اللحظية في ConsumptionReading.
        2. يراكم ويحدث استهلاك اليوم حياً بضربة ذرة ذكية في DailyConsumptionSummary.
        """
        meter = Meter.objects.get(pk=meter_id)
        last_reading = ConsumptionReading.objects.filter(meter=meter).order_by('timestamp').last()

        # 1. تحويل الحمولة إلى DTO موحد عبر محول العتاد
        adapter = IngestionAdapterFactory.get_adapter(payload, hardware_type)
        standard_dto = adapter.parse_payload(payload, last_reading, timestamp_dt)

        # 2. حساب فارق الاستهلاك الجديد بالكيلوواط/ساعة (Delta KWh)
        delta_wh = Decimal('0.00')
        if last_reading:
            delta_wh = standard_dto.cumulativeWh - last_reading.cumulativeWh
            if delta_wh < Decimal('0.00'):
                delta_wh = Decimal('0.00')
        
        delta_kwh = round(delta_wh / Decimal('1000.00'), 4)

        with transaction.atomic():
            # أ. حفظ القراءة المباشرة
            reading = ConsumptionReading.objects.create(
                meter=meter,
                cumulativeWh=standard_dto.cumulativeWh,
                timestamp=standard_dto.timestamp
            )

            # ب. التحديث التراكمي اللحظي بسطر اليوم في DailyConsumptionSummary
            reading_date = timestamp_dt.date()
            summary_obj, created = DailyConsumptionSummary.objects.get_or_create(
                meter=meter,
                date=reading_date,
                defaults={'totalKWh': Decimal('0.00')}
            )

            if delta_kwh > Decimal('0.00'):
                # استخدام F() Expression لمنع التضارب وضمان التحديث الذري
                DailyConsumptionSummary.objects.filter(pk=summary_obj.summaryId).update(
                    totalKWh=F('totalKWh') + delta_kwh
                )

        return reading

    @staticmethod
    def process_bulk_backfill(meter_id: str, readings_data: list) -> int:
        """
        يقوم بحقن القراءات التاريخية وتأجير حساب إجمالي الأيام المكتملة فوراً لجدول DailyConsumptionSummary.
        """
        meter = Meter.objects.get(pk=meter_id)
        readings_to_create = []
        daily_totals = {} # قاموس تجميع الأيام مؤقتاً

        with transaction.atomic():
            ConsumptionReading.objects.filter(meter=meter).delete()
            DailyConsumptionSummary.objects.filter(meter=meter).delete()
            CacheService.invalidate_meter_dashboard_cache(meter_id)

            prev_wh = Decimal('0.00')
            for item in readings_data:
                ts = datetime.fromtimestamp(item['timestamp'])
                current_wh = Decimal(str(item['cumulativeWh']))
                
                readings_to_create.append(
                    ConsumptionReading(
                        meter=meter,
                        cumulativeWh=current_wh,
                        timestamp=make_aware(ts)
                    )
                )

                # حساب التراكم اليومي للحقن التاريخي
                day_key = ts.date()
                if day_key not in daily_totals:
                    daily_totals[day_key] = Decimal('0.00')
                
                if prev_wh > Decimal('0.00') and current_wh > prev_wh:
                    delta_kwh = (current_wh - prev_wh) / Decimal('1000.00')
                    daily_totals[day_key] += delta_kwh
                
                prev_wh = current_wh

            # 1. إنشاء القراءات اللحظية
            ConsumptionReading.objects.bulk_create(readings_to_create)

            # 2. إنشاء ملخصات الأيام المجمعة تاريخياً دفعة واحدة
            summaries_to_create = [
                DailyConsumptionSummary(
                    meter=meter,
                    date=d_date,
                    totalKWh=round(d_kwh, 2)
                ) for d_date, d_kwh in daily_totals.items()
            ]
            DailyConsumptionSummary.objects.bulk_create(summaries_to_create)

        return len(readings_to_create)