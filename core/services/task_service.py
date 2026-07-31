from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist

from core.models import (
    DailyConsumptionSummary, Meter, DailyForecast, Budget, TariffVersion, ConsumptionReading
)
from core.ai_models.daily_model import predict_daily_consumption
from core.events.signals import (
    anomaly_detected_signal,
    budget_limit_exceeded_signal,
    tier_limit_exceeded_signal,
)

class TaskService:

    @classmethod
    def run_daily_prediction_and_anomaly_detection(cls, meter_id: str, target_date: date) -> DailyForecast:
        meter = Meter.objects.get(pk=meter_id)
        yesterday_date = target_date - timedelta(days=1)

        # قراءة استهلاك أمس المكتمل من جدول التجميع المباشر
        yesterday_summary = DailyConsumptionSummary.objects.filter(meter=meter, date=yesterday_date).first()
        yesterday_actual_kwh = round(yesterday_summary.totalKWh, 2) if yesterday_summary else Decimal('0.00')

        mock_history = [Decimal('12.50'), Decimal('14.20'), Decimal('11.80')]
        predicted_today = predict_daily_consumption(mock_history)

        forecast, created = DailyForecast.objects.update_or_create(
            meter=meter,
            forecastDate=target_date,
            defaults={
                'predictedConsumptionKWh': predicted_today,
                'actualConsumptionKWh': yesterday_actual_kwh
            }
        )

        deviation = yesterday_actual_kwh - forecast.predictedConsumptionKWh
        forecast.deviationAmountKWh = max(Decimal('0.00'), deviation)

        if forecast.predictedConsumptionKWh > 0 and (deviation / forecast.predictedConsumptionKWh) > Decimal('0.40'):
            forecast.isAnomalous = True
            forecast.save()

            anomaly_detected_signal.send(sender=cls, meter=meter, forecast=forecast)
        else:
            forecast.save()

        return forecast

    @classmethod
    def run_daily_adaptive_notifications(cls, meter_id: str, target_date: date, yesterday_actual_kwh: Decimal) -> None:
        """
        [UC_10] تقييم أرقام يوم أمس المكتمل وإطلاق أحداث الإشعارات التكيفية عبر نمط المراقب
        """
        meter = Meter.objects.get(pk=meter_id)

        # 1. حساب حدود الدورة الكهربائية الثنائية
        year = target_date.year
        month = target_date.month

        if month in [1, 2]:
            cycle_start_date = date(year, 1, 1)
            cycle_end_date = date(year, 2, 29 if calendar.isleap(year) else 28)
        elif month in [3, 4]:
            cycle_start_date = date(year, 3, 1)
            cycle_end_date = date(year, 4, 30)
        elif month in [5, 6]:
            cycle_start_date = date(year, 5, 1)
            cycle_end_date = date(year, 6, 30)
        elif month in [7, 8]:
            cycle_start_date = date(year, 7, 1)
            cycle_end_date = date(year, 8, 31)
        elif month in [9, 10]:
            cycle_start_date = date(year, 9, 1)
            cycle_end_date = date(year, 10, 31)
        else:
            cycle_start_date = date(year, 11, 1)
            cycle_end_date = date(year, 12, 31)

        total_cycle_days = (cycle_end_date - cycle_start_date).days + 1
        days_passed = (target_date - cycle_start_date).days + 1
        remaining_days = total_cycle_days - days_passed
        yesterday_div_days = Decimal(str(remaining_days + 1))

        # 2. حساب استهلاك الدورة التراكمي المباشر
        cycle_start_dt = make_aware(datetime.combine(cycle_start_date, datetime.min.time()))
        target_end_dt = make_aware(datetime.combine(target_date, datetime.max.time()))

        start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=cycle_start_dt).order_by('timestamp').first()
        latest_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=target_end_dt).order_by('timestamp').last()

        cycle_consumption = Decimal('0.00')
        if start_reading and latest_reading:
            consumption_wh = latest_reading.cumulativeWh - start_reading.cumulativeWh
            cycle_consumption = round(consumption_wh / Decimal('1000.00'), 2)

        consumption_before_yesterday = cycle_consumption - yesterday_actual_kwh

        # 3. جلب حد الشريحة المدعومة لعام/تاريخ اليوم
        try:
            active_version = TariffVersion.objects.filter(effectiveDate__lte=target_date).order_by('-effectiveDate').first()
            tier1 = active_version.tiers.filter(tierNumber=1).first() if active_version else None
            support_limit = Decimal(str(tier1.endKWh)) if tier1 and tier1.endKWh else Decimal('300.00')
        except Exception:
            support_limit = Decimal('300.00')

        # 4. جلب ميزانية العداد
        budget_limit = Decimal('0.00')
        try:
            budget = Budget.objects.get(meter=meter)
            budget_limit = budget.equivalentLimitKWh
        except ObjectDoesNotExist:
            budget_limit = Decimal('0.00')

        # 5. حساب المعدلات المتاحة للأيام المتبقية
        rem_days_dec = Decimal(str(max(1, remaining_days)))
        
        avg_sub_target_kwh = round((support_limit - cycle_consumption) / rem_days_dec, 2)
        if avg_sub_target_kwh < 0:
            avg_sub_target_kwh = Decimal('0.00')

        avg_budget_target_kwh = round((budget_limit - cycle_consumption) / rem_days_dec, 2) if budget_limit > 0 else Decimal('0.00')
        if avg_budget_target_kwh < 0:
            avg_budget_target_kwh = Decimal('0.00')

        # ==================== إطلاق إشارات نمط المراقب (Observer Pattern Signals) ====================
        
        # 1. إشارة تقييم الشريحة والدعم
        allowed_sub_yesterday = round((support_limit - consumption_before_yesterday) / yesterday_div_days, 2)
        if allowed_sub_yesterday < 0:
            allowed_sub_yesterday = Decimal('0.00')

        tier_limit_exceeded_signal.send(
            sender=cls,
            meter=meter,
            is_exceeded=(yesterday_actual_kwh > allowed_sub_yesterday),
            yesterday_actual=yesterday_actual_kwh,
            allowed_target=allowed_sub_yesterday,
            new_target=avg_sub_target_kwh
        )

        # 2. إشارة تقييم الميزانية الشخصية
        if budget_limit > 0:
            allowed_budget_yesterday = round((budget_limit - consumption_before_yesterday) / yesterday_div_days, 2)
            if allowed_budget_yesterday < 0:
                allowed_budget_yesterday = Decimal('0.00')

            budget_limit_exceeded_signal.send(
                sender=cls,
                meter=meter,
                is_exceeded=(yesterday_actual_kwh > allowed_budget_yesterday),
                yesterday_actual=yesterday_actual_kwh,
                allowed_target=allowed_budget_yesterday,
                new_target=avg_budget_target_kwh
            )