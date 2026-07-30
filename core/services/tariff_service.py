from decimal import Decimal
from datetime import date
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from core.models import TariffVersion, TariffTier

class TariffService:

    @classmethod
    def calculate_syrian_cost(cls, consumption_kwh: Decimal, current_date: date = None) -> Decimal:
        """
        محرك الفوترة المركزي: يحسب التكلفة بالليرة السورية للاستهلاك 
        بناءً على إصدار التعرفة الكهربائية السارية في التاريخ المحدد ديناميكياً.
        """
        if current_date is None:
            current_date = date.today()
            
        try:
            active_version = TariffVersion.objects.filter(
                effectiveDate__lte=current_date
            ).order_by('-effectiveDate').first()
            
            if active_version is None:
                raise ObjectDoesNotExist()

            tiers = active_version.tiers.order_by('tierNumber')
        except ObjectDoesNotExist:
            # الخطة الاحتياطية في حال عدم وجود تعرفة مدخلة
            if consumption_kwh <= Decimal('300.00'):
                return consumption_kwh * Decimal('600.00')
            else:
                return (Decimal('300.00') * Decimal('600.00')) + ((consumption_kwh - Decimal('300.00')) * Decimal('1400.00'))

        remaining_kwh = consumption_kwh
        total_cost = Decimal('0.00')

        for tier in tiers:
            price = Decimal(str(tier.pricePerKWh))
            if tier.endKWh is not None:
                start = Decimal(str(tier.startKWh))
                end = Decimal(str(tier.endKWh))
                tier_range = end - start

                if remaining_kwh > tier_range:
                    total_cost += tier_range * price
                    remaining_kwh -= tier_range
                else:
                    total_cost += remaining_kwh * price
                    remaining_kwh = Decimal('0.00')
                    break
            else:
                total_cost += remaining_kwh * price
                remaining_kwh = Decimal('0.00')
                break

        return round(total_cost, 2)

    @staticmethod
    def create_new_tariff(effective_date: date, tiers_data: list) -> TariffVersion:
        with transaction.atomic():
            new_version = TariffVersion.objects.create(
                effectiveDate=effective_date
            )
            
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