from datetime import date
from core.models import TariffVersion, TariffTier
from django.db import transaction

class TariffService:

    @staticmethod
    def create_new_tariff(effective_date: date, tiers_data: list) -> TariffVersion:
        # استخدام معالجة معزولة لضمان حماية المعطيات
        with transaction.atomic():
            # تعطيل جميع إصدارات التعرفة السابقة
            TariffVersion.objects.all().update(isActive=False)
            
            # إنشاء إصدار التعرفة الجديد والنشط
            new_version = TariffVersion.objects.create(
                effectiveDate=effective_date,
                isActive=True
            )
            
            # بناء وحفظ الشرائح التابعة للإصدار الجديد
            tiers_to_create = []
            for item in tiers_data:
                tiers_to_create.append(
                    TariffTier(
                        tariffVersion=new_version,
                        tierNumber=item['tierNumber'],
                        startKWh=item['startKWh'],
                        endKWh=item['endKWh'],
                        pricePerKWh=item['pricePerKWh']
                    )
                )
            
            TariffTier.objects.bulk_create(tiers_to_create)
            return new_version