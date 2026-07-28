from datetime import date
from django.core.management.base import BaseCommand
from core.models import TariffVersion, TariffTier


class Command(BaseCommand):
    help = 'يزرع ويحقن تعرفة الشرائح الكهربائية السورية المعتمدة لعام 2025 في قاعدة البيانات تلقائياً'

    def handle(self, *args, **kwargs):
        # تم إلغاء أسطر التحديث القديمة لـ isActive لعدم الحاجة لها برمجياً بعد الآن

        # إنشاء إصدار تعرفة جديد ومحدد بتاريخ نفاذ 1 تشرين الثاني 2025
        tariff_version = TariffVersion.objects.create(
            effectiveDate=date(2025, 11, 1)
        )

        # إنشاء الشريحة الأولى المعتمدة لعام 2025: من 0 إلى 300 ك.و.س بسعر 600 ل.س
        TariffTier.objects.create(
            tariffVersion=tariff_version,
            tierNumber=1,
            startKWh=0.00,
            endKWh=300.00,
            pricePerKWh=600.00
        )

        # إنشاء الشريحة الثانية المعتمدة لعام 2025: ما فوق 300 ك.و.س بسعر 1400 ل.س
        TariffTier.objects.create(
            tariffVersion=tariff_version,
            tierNumber=2,
            startKWh=300.01,
            endKWh=None, 
            pricePerKWh=1400.00
        )

        self.stdout.write(self.style.SUCCESS('تم زرع وحقن تعرفة الشرائح السورية لعام 2025 بنجاح!'))