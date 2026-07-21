import os
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import Meter, ConsumptionReading

class Command(BaseCommand):
    help = 'يقرأ ملف channel_1.dat ويقوم بضغط وحقن البيانات التاريخية بدقة (15 دقيقة) لفترة سنتين (من 5-2025 إلى 5-2027)'

    def handle(self, *args, **kwargs):
        file_path = os.path.join('core', 'data', 'channel_1.dat')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"الملف غير موجود في المسار: {file_path}"))
            return

        self.stdout.write("جاري إنشاء العداد التجريبي والبدء بمعالجة وضغط البيانات...")

        # 1. إنشاء أو جلب العداد التجريبي بالمعرف الثابت
        test_meter_uuid = "11111111-1111-1111-1111-111111111111"
        meter, created = Meter.objects.get_or_create(meterId=test_meter_uuid)
        
        # مسح أي قراءات قديمة لتجنب تضارب البيانات
        ConsumptionReading.objects.filter(meter=meter).delete()

        # 2. إعدادات الطوابع الزمنية وإزاحتها تاريخياً لتبدأ من 1 أيار 2025
        # التوقيت الفعلي لأول قراءة بالملف: 1352500095 (9 تشرين الثاني 2012)
        # التوقيت الجديد لبدء البيانات: 1 أيار 2025 (Unix timestamp: 1746057600)
        original_start_ts = 1352500095
        target_start_ts = 1746057600
        time_offset = target_start_ts - original_start_ts

        # تحديد تاريخ نهاية السنتين بدقة: 1 أيار 2027 (تاريخ النهاية بعد سنتين)
        end_date_limit = datetime(2027, 5, 1, 0, 0, 0)

        cumulative_wh = Decimal('0.00')
        interval_data = {} # لتجميع القراءات في فترات الـ 15 دقيقة

        self.stdout.write("جاري تجميع وضغط القراءات الـ 6 ثوانية إلى فترات ربع ساعية (15 دقيقة)...")
        
        with open(file_path, 'r') as file:
            for line in file:
                parts = line.strip().split()
                if len(parts) != 2:
                    continue
                
                orig_ts = int(parts[0])
                watts = Decimal(parts[1])

                # حساب التوقيت الجديد بعد الإزاحة لعام 2025
                shifted_ts = orig_ts + time_offset
                dt = datetime.fromtimestamp(shifted_ts)

                # التوقف عن القراءة فوراً إذا تجاوزنا حد السنتين (1 أيار 2027) لضمان دقة وحجم البيانات
                if dt >= end_date_limit:
                    break

                # تقريب الوقت الحركي للـ 15 دقيقة الأقرب لتجميع البيانات داخلها
                # مثال: قراءة 12:04 وقراءة 12:11 يتم تجميعهما معاً تحت كتلة الـ 12:15
                minute_block = (dt.minute // 15) * 15
                rounded_dt = dt.replace(minute=minute_block, second=0, microsecond=0)

                # حساب الطاقة المستهلكة في الـ 6 ثوانٍ بالواط ساعي Wh
                energy_wh = watts * Decimal('6') / Decimal('3600')

                if rounded_dt not in interval_data:
                    interval_data[rounded_dt] = Decimal('0.00')
                interval_data[rounded_dt] += energy_wh

        self.stdout.write("جاري حقن القراءات الربع ساعية سحابياً في قاعدة البيانات...")

        # 3. فرز وحفظ البيانات التراكمية في قاعدة البيانات بالتسلسل الزمني الدقيق
        readings_to_create = []
        sorted_timestamps = sorted(interval_data.keys())

        for ts in sorted_timestamps:
            cumulative_wh += interval_data[ts]
            
            readings_to_create.append(
                ConsumptionReading(
                    meter=meter,
                    cumulativeWh=cumulative_wh,
                    timestamp=ts
                )
            )

        # حقن البيانات المجمعة دفعة واحدة (Bulk Create)
        ConsumptionReading.objects.bulk_create(readings_to_create)

        self.stdout.write(self.style.SUCCESS(
            f"تم بنجاح حقن {len(readings_to_create)} قراءة ربع ساعية تراكمية للعداد {test_meter_uuid}!"
        ))