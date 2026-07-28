# افتح ملف core/services/tariff_service.py واستبدل كوده بالكامل كالتالي ليكون مبسطاً ومتناسقاً:

from datetime import date
from core.models import TariffVersion, TariffTier
from django.db import transaction

class TariffService:

    @staticmethod
    def create_new_tariff(effective_date: date, tiers_data: list) -> TariffVersion:
        with transaction.atomic():
            # تم إلغاء كود تحديث isActive القديم لعدم الحاجة له بعد الآن
            
            # إنشاء إصدار التعرفة الجديد وحفظ تاريخ نفاذه
            new_version = TariffVersion.objects.create(
                effectiveDate=effective_date
            )
            
            # بناء وحفظ الشرائح التابعة له
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