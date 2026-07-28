from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from core.models import Meter, Budget, TariffVersion

class BudgetService:
    
    @staticmethod
    def calculate_equivalent_kwh(amount_syp: Decimal) -> Decimal:
        from datetime import date
        from django.core.exceptions import ObjectDoesNotExist # استيراد الاستثناء

        try:
            active_version = TariffVersion.objects.filter(
                effectiveDate__lte=date.today()
            ).order_by('-effectiveDate').first()
            
            # حزام أمان حرج جداً: إذا كانت النتيجة فارغة، نطلق الاستثناء يدوياً ليدخل في بلوك الـ except الاحتياطي
            if active_version is None:
                raise ObjectDoesNotExist()

            tiers = active_version.tiers.order_by('tierNumber')
        except ObjectDoesNotExist:
            # في حال عدم وجود تعرفة مدخلة، نطبق القيمة الافتراضية لعام 2025 كحزام أمان
            if amount_syp <= Decimal('180000.00'):
                return amount_syp / Decimal('600.00')
            else:
                return Decimal('300.00') + ((amount_syp - Decimal('180000.00')) / Decimal('1400.00'))

        remaining_budget = amount_syp
        total_kwh = Decimal('0.00')

        for tier in tiers:
            price = Decimal(str(tier.pricePerKWh))
            
            if tier.endKWh is not None:
                start = Decimal(str(tier.startKWh))
                end = Decimal(str(tier.endKWh))
                tier_range = end - start
                max_tier_cost = tier_range * price

                if remaining_budget > max_tier_cost:
                    total_kwh += tier_range
                    remaining_budget -= max_tier_cost
                else:
                    total_kwh += remaining_budget / price
                    remaining_budget = Decimal('0.00')
                    break
            else:
                total_kwh += remaining_budget / price
                remaining_budget = Decimal('0.00')
                break

        return round(total_kwh, 2)
    @classmethod
    def set_or_update_budget(cls, meter_id: str, target_budget: Decimal) -> Budget:
        meter = Meter.objects.get(pk=meter_id)
        equivalent_limit = cls.calculate_equivalent_kwh(target_budget)

        budget, created = Budget.objects.update_or_create(
            meter=meter,
            defaults={
                'targetBudgetSYP': target_budget,
                'equivalentLimitKWh': equivalent_limit
            }
        )
        
        # حل مشكلة جمود الكاش: تصفير الكاش السريع فوراً لإجبار السيرفر على إعادة الحساب اللحظي المحدث للـ Dashboard
        from django.core.cache import cache
        cache.clear()
        
        return budget