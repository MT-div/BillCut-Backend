from decimal import Decimal
from django.db.models import Avg
from core.models import AnomalyThreshold, DailyConsumptionSummary

class ThresholdScalingService:

    @classmethod
    def calculate_system_average_kwh(cls) -> Decimal:
        """حساب متوسط الاستهلاك اليومي الإقليمي تلقائياً من كامل سجلات النظام"""
        avg_val = DailyConsumptionSummary.objects.aggregate(avg=Avg('totalKWh'))['avg']
        return round(Decimal(str(avg_val or '23.16')), 2)

    @classmethod
    def update_anomaly_threshold(cls, custom_target_mean: Decimal = None, region_name: str = None) -> AnomalyThreshold:
        """
        تطبيق معادلة التكيّف التناسبة (Scale-Invariant Domain Adaptation):
        Threshold_Target = baseThreshold * (targetMean / baseMean)
        """
        # 1. جلب قيم القاعدة الحالية
        active_obj = AnomalyThreshold.objects.filter(isActive=True).order_by('-updatedAt').first()
        base_mean = active_obj.baseMeanKWh if active_obj else Decimal('10.25')
        base_threshold = active_obj.baseThresholdKWh if active_obj else Decimal('7.00')

        # 2. تحديد متوسط المنطقة (إما الممرر يدوياً كـ Override أو المحسوب تلقائياً من بيانات النظام)
        if custom_target_mean is not None and custom_target_mean > Decimal('0.00'):
            target_mean = custom_target_mean
        else:
            target_mean = cls.calculate_system_average_kwh()

        # 3. تطبيق معادلة الملاءمة التناسبية
        calculated_threshold = round(base_threshold * (target_mean / base_mean), 2)

        # 4. إلغاء تفعيل العتبات القديمة وتنشيط العتبة الجديدة
        AnomalyThreshold.objects.filter(isActive=True).update(isActive=False)

        new_threshold = AnomalyThreshold.objects.create(
            targetRegionName=region_name or "المنطقة المحلية / سوريا",
            baseMeanKWh=base_mean,
            baseThresholdKWh=base_threshold,
            targetRegionMeanKWh=target_mean,
            calculatedThresholdKWh=calculated_threshold,
            isActive=True
        )
        return new_threshold