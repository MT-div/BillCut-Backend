from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from core.models import Meter, Budget, TariffVersion

class BudgetService:
    
    @staticmethod
    def calculate_equivalent_kwh(amount_syp: Decimal) -> Decimal:
        """
        خوارزمية التعرفة العكسية الديناميكية المبتكرة:
        تقرأ الشرائح المفعلة حالياً من قاعدة البيانات وتحسب الكيلوواط المعادل للميزانية المحددة.
        """
        try:
            # جلب إصدار التعرفة الفعال حالياً في قاعدة البيانات
            active_version = TariffVersion.objects.get(isActive=True)
            # جلب الشرائح التابعة له مرتبة من الأدنى للأعلى
            tiers = active_version.tiers.all().order_name = active_version.tiers.order_by('tierNumber')
        except ObjectDoesNotExist:
            # في حال عدم وجود تعرفة مدخلة، نطبق القيمة الافتراضية لعام 2025 كحزام أمان
            # الشريحة الأولى: حتى 300 ك.و.س بسعر 600 ل.س، وما فوق بسعر 1400 ل.س
            if amount_syp <= Decimal('180000.00'):
                return amount_syp / Decimal('600.00')
            else:
                return Decimal('300.00') + ((amount_syp - Decimal('180000.00')) / Decimal('1400.00'))

        remaining_budget = amount_syp
        total_kwh = Decimal('0.00')

        for tier in tiers:
            price = Decimal(str(tier.pricePerKWh))
            
            # إذا لم تكن هذه هي الشريحة الأخيرة (لها حد أعلى محدد)
            if tier.endKWh is not None:
                start = Decimal(str(tier.startKWh))
                end = Decimal(str(tier.endKWh))
                tier_range = end - start
                max_tier_cost = tier_range * price

                # إذا كانت الميزانية المتبقية تكفي لتغطية كامل الشريحة الحالية
                if remaining_budget > max_tier_cost:
                    total_kwh += tier_range
                    remaining_budget -= max_tier_cost
                else:
                    # إذا كانت الميزانية المتبقية تنتهي ضمن حدود الشريحة الحالية
                    total_kwh += remaining_budget / price
                    remaining_budget = Decimal('0.00')
                    break
            else:
                # الشريحة الأخيرة المفتوحة (ما فوق)
                total_kwh += remaining_budget / price
                remaining_budget = Decimal('0.00')
                break

        return round(total_kwh, 2)

    @classmethod
    def set_or_update_budget(cls, meter_id: str, target_budget: Decimal) -> Budget:
        """
        خدمة حفظ وتحديث ميزانية العداد وحساب استهلاكه المعادل
        """
        meter = Meter.objects.get(pk=meter_id)
        equivalent_limit = cls.calculate_equivalent_kwh(target_budget)

        # حفظ أو تحديث السجل باستخدام django update_or_create
        budget, created = Budget.objects.update_or_create(
            meter=meter,
            defaults={
                'targetBudgetSYP': target_budget,
                'equivalentLimitKWh': equivalent_limit
            }
        )
        return budget