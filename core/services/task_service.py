from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist

from core.models import (
    Meter, DailyForecast, MonthlyForecast, Notification, 
    Budget, TariffVersion, ConsumptionReading
)
from core.ai_models.daily_model import predict_daily_consumption
from core.ai_models.monthly_model import predict_monthly_consumption
from core.services.tariff_service import TariffService


class TaskService:

    @classmethod
    def run_daily_prediction_and_anomaly_detection(cls, meter_id: str, target_date: date) -> DailyForecast:
        """
        [UC_8] تشغيل محرك التنبؤ اليومي للغد وكشف شذوذ الأمس عند منتصف الليل
        """
        meter = Meter.objects.get(pk=meter_id)
        yesterday_date = target_date - timedelta(days=1)
        day_before_yesterday_date = yesterday_date - timedelta(days=1)

        yesterday_end_dt = make_aware(datetime.combine(yesterday_date, datetime.max.time()))
        day_before_yesterday_end_dt = make_aware(datetime.combine(day_before_yesterday_date, datetime.max.time()))

        start_reading = meter.readings.filter(timestamp__lte=day_before_yesterday_end_dt).order_by('timestamp').last()
        end_reading = meter.readings.filter(timestamp__lte=yesterday_end_dt).order_by('timestamp').last()

        yesterday_actual_kwh = Decimal('0.00')
        if start_reading and end_reading:
            yesterday_actual_wh = end_reading.cumulativeWh - start_reading.cumulativeWh
            yesterday_actual_kwh = round(yesterday_actual_wh / Decimal('1000.00'), 2)

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
            Notification.objects.create(
                meter=meter,
                title="تحذير: عطل كهربائي محتمل!",
                message=f"تنبيه: تجاوز استهلاكك الفعلي بالأمس التنبؤ اليومي بمقدار {forecast.deviationAmountKWh} ك.و.س. يرجى التحقق من سلامة الأجهزة.",
                type="ANOMALY",
                isRead=False
            )

        forecast.save()
        return forecast

    @classmethod
    def run_daily_adaptive_notifications(cls, meter_id: str, target_date: date, yesterday_actual_kwh: Decimal) -> None:
        """
        [UC_10] توليد وإرسال الإشعارات التكيفية اليومية بشكل معزول ومباشر من الداتابيز
        دون الاعتماد على خدمة واجهات الـ Dashboard.
        """
        meter = Meter.objects.get(pk=meter_id)

        # 1. حساب حدود الدورة الكهربائية الثنائية تاريخياً باستخدام calendar.isleap الاحترافي
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

        # 2. حساب استهلاك الدورة التراكمي المباشر حتى تاريخ اليوم
        cycle_start_dt = make_aware(datetime.combine(cycle_start_date, datetime.min.time()))
        target_end_dt = make_aware(datetime.combine(target_date, datetime.max.time()))

        start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=cycle_start_dt).order_by('timestamp').first()
        latest_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=target_end_dt).order_by('timestamp').last()

        cycle_consumption = Decimal('0.00')
        if start_reading and latest_reading:
            consumption_wh = latest_reading.cumulativeWh - start_reading.cumulativeWh
            cycle_consumption = round(consumption_wh / Decimal('1000.00'), 2)

        consumption_before_yesterday = cycle_consumption - yesterday_actual_kwh

        # 3. جلب حد الشريحة المدعومة بشكل مباشر
        try:
            active_version = TariffVersion.objects.filter(effectiveDate__lte=target_date).order_by('-effectiveDate').first()
            tier1 = active_version.tiers.filter(tierNumber=1).first() if active_version else None
            support_limit = Decimal(str(tier1.endKWh)) if tier1 and tier1.endKWh else Decimal('300.00')
        except Exception:
            support_limit = Decimal('300.00')

        # 4. جلب ميزانية العداد بشكل مباشر
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

        # ==================== أولاً: إشعار الشريحة والدعم (TIER) ====================
        allowed_sub_yesterday = round((support_limit - consumption_before_yesterday) / yesterday_div_days, 2)
        if allowed_sub_yesterday < 0:
            allowed_sub_yesterday = Decimal('0.00')

        if yesterday_actual_kwh > allowed_sub_yesterday:
            title = "تنبيه: تجاوز معدل الشريحة"
            message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء في الدعم (المعدل المتاح كان {allowed_sub_yesterday} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي الجديد للأيام المتبقية أصبح {avg_sub_target_kwh} ك.و.س."
            msg_type = "TIER"
        else:
            title = "أحسنت: التزام بالدعم"
            message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق الشريحة المدعومة (المعدل المتاح كان {allowed_sub_yesterday} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي المتاح للأيام المتبقية هو {avg_sub_target_kwh} ك.و.س."
            msg_type = "TIER"

        Notification.objects.create(
            meter=meter,
            title=title,
            message=message,
            type=msg_type,
            isRead=False
        )

        # ==================== ثانياً: إشعار الميزانية الشخصية (BUDGET) ====================
        if budget_limit > 0:
            allowed_budget_yesterday = round((budget_limit - consumption_before_yesterday) / yesterday_div_days, 2)
            if allowed_budget_yesterday < 0:
                allowed_budget_yesterday = Decimal('0.00')

            if yesterday_actual_kwh > allowed_budget_yesterday:
                b_title = "تنبيه: تجاوز معدل الميزانية"
                b_message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء ضمن ميزانيتك المحددة (المعدل المتاح كان {allowed_budget_yesterday} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي الجديد المتاح للميزانية هو {avg_budget_target_kwh} ك.و.س."
                b_msg_type = "BUDGET"
            else:
                b_title = "أحسنت: التزام بالميزانية"
                b_message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق ميزانيتك الشخصية المستهدفة (المعدل المتاح كان {allowed_budget_yesterday} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي المتاح للالتزام بالميزانية هو {avg_budget_target_kwh} ك.و.س."
                b_msg_type = "BUDGET"

            Notification.objects.create(
                meter=meter,
                title=b_title,
                message=b_message,
                type=b_msg_type,
                isRead=False
            )