from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist

from core.ai_models.monthly_model import predict_monthly_consumption
from core.models import (
    DailyConsumptionSummary, Meter, DailyForecast, Budget, MonthlyForecast, TariffVersion, ConsumptionReading
)
from core.ai_models.daily_model import predict_daily_consumption
from core.events.signals import (
    anomaly_detected_signal,
    budget_limit_exceeded_signal,
    tier_limit_exceeded_signal,
)
from core.services.tariff_service import TariffService
from django.db.models import Sum

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

    @classmethod
    def get_exact_prior_month_range(cls, base_date: date, months_back: int) -> tuple:
        """
        دالة مساعدة تقويمية دقيقة: تحسب تاريخ بداية ونهاية الشهر بالضبط عند الرجوع للخلف.
        تتفاضى خطأ افتراض الـ 30 يوماً وتتعامل مع شباط والسنوات الكبيسة بدقة 100%.
        """
        total_months = base_date.year * 12 + (base_date.month - 1) - months_back
        target_year = total_months // 12
        target_month = (total_months % 12) + 1

        first_day = date(target_year, target_month, 1)
        _, last_day_num = calendar.monthrange(target_year, target_month)
        last_day = date(target_year, target_month, last_day_num)

        return first_day, last_day

    @classmethod
    def run_monthly_cycle_prediction(cls, meter_id: str, target_date: date) -> MonthlyForecast:
        """
        [UC_Forecast] إدارة التنبؤ الشهري والفوترة التكيفية للدورة السورية (النسخة الدقيقة تقويمياً):
        1. تحسب حدود الدورة الشريحة الحالية بدقة (كانون1+شباط، آذار+نيسان... إلخ).
        2. تسترجع سجل الـ 13 شهراً التقويمية السابقة بدقة من DailyConsumptionSummary.
        3. تمنع الاستدعاء التكراري الزائد للموديل إذا كانت التوقعات محسوبة مسبقاً.
        4. في الشهر الأول: تتنبأ بـ P1 ثم تحقن P1 تتنبأ بـ P2.
        5. في الشهر الثاني: تسترجع A1 الفعلي المكتمل، وتحقنه لتتنبأ بـ P2 المحدث!
        """
        meter = Meter.objects.get(pk=meter_id)

        # ---------------------------------------------------------------------
        # أ. تحديد حدود الدورة الفوترية الثنائية والشهر الثاني
        # ---------------------------------------------------------------------
        year = target_date.year
        month = target_date.month

        if month in [1, 2]:
            cycle_start_date = date(year, 1, 1)
            month2_start_date = date(year, 2, 1)
            month1_end_date = date(year, 1, 31)
        elif month in [3, 4]:
            cycle_start_date = date(year, 3, 1)
            month2_start_date = date(year, 4, 1)
            month1_end_date = date(year, 3, 31)
        elif month in [5, 6]:
            cycle_start_date = date(year, 5, 1)
            month2_start_date = date(year, 6, 1)
            month1_end_date = date(year, 5, 31)
        elif month in [7, 8]:
            cycle_start_date = date(year, 7, 1)
            month2_start_date = date(year, 8, 1)
            month1_end_date = date(year, 7, 31)
        elif month in [9, 10]:
            cycle_start_date = date(year, 9, 1)
            month2_start_date = date(year, 10, 1)
            month1_end_date = date(year, 9, 30)
        else:
            cycle_start_date = date(year, 11, 1)
            month2_start_date = date(year, 12, 1)
            month1_end_date = date(year, 11, 30)

        # ---------------------------------------------------------------------
        # ب. جمع سجل الأشهر الـ 13 التقويمية السابقة بدقة من DailyConsumptionSummary
        # ---------------------------------------------------------------------
        historical_months = []
        for i in range(13, 0, -1):
            # جلب بداية ونهاية الشهر التقويمي الحقيقي قبل i شهراً
            m_start, m_end = cls.get_exact_prior_month_range(cycle_start_date, i)

            # استعلام مجموع الكيلوواط الساعي لهذا الشهر التقويمي
            m_sum = DailyConsumptionSummary.objects.filter(
                meter=meter, date__gte=m_start, date__lte=m_end
            ).aggregate(total=Sum('totalKWh'))['total']

            if m_sum is not None:
                historical_months.append(float(m_sum))

        # ---------------------------------------------------------------------
        # ج. جلب أو إنشاء سجل التنبؤ الموحد لهذه الدورة
        # ---------------------------------------------------------------------
        monthly_forecast, created = MonthlyForecast.objects.get_or_create(
            meter=meter,
            cycleStartDate=cycle_start_date,
            defaults={
                'predictedMonth1KWh': Decimal('0.00'),
                'predictedMonth2KWh': Decimal('0.00'),
                'expectedBillSYP': Decimal('0.00')
            }
        )

        # ---------------------------------------------------------------------
        # د. معالجة مرحلة الشهر الثاني (Month 2 Phase)
        # ---------------------------------------------------------------------
        if target_date >= month2_start_date:
            # تنفيذ التحديث فقط إذا لم يسبق تسجيل A1 الفعلي وتحديث P2 في هذه الدورة
            if monthly_forecast.actualMonth1KWh is None:
                # 1. استرجاع إجمالي الاستهلاك الفعلي والحقيقي المكتمل للشهر الأول كامل
                actual_m1_sum = DailyConsumptionSummary.objects.filter(
                    meter=meter, date__gte=cycle_start_date, date__lte=month1_end_date
                ).aggregate(total=Sum('totalKWh'))['total']

                actual_m1 = round(actual_m1_sum or Decimal('0.00'), 2)
                monthly_forecast.actualMonth1KWh = actual_m1

                # 2. حقن A1 الفعلي كأحدث شهر في المتسلسلة الزمنية والتنبؤ بـ P2 المحدث
                historical_plus_a1 = historical_months + [float(actual_m1)]
                p2_new = predict_monthly_consumption(historical_plus_a1)

                monthly_forecast.predictedMonth2KWh = p2_new
                
                # 3. حساب الفاتورة المحدثة كـ (A1 الفعلي + P2 التنبؤي المحدث)
                total_cycle_kwh = actual_m1 + p2_new
                monthly_forecast.expectedBillSYP = TariffService.calculate_syrian_cost(total_cycle_kwh, target_date)
                monthly_forecast.save()

        # ---------------------------------------------------------------------
        # هـ. معالجة مرحلة الشهر الأول (Month 1 Phase)
        # ---------------------------------------------------------------------
        else:
            # تنفيذ التنبؤ الأول فقط إذا لم يكن حسابه وتخزينه قد تم مسبقاً
            if monthly_forecast.predictedMonth1KWh == Decimal('0.00') or monthly_forecast.predictedMonth2KWh == Decimal('0.00'):
                # 1. التنبؤ بـ P1 للشهر الأول بناءً على سجل الأشهر الـ 13 السابقة
                p1 = predict_monthly_consumption(historical_months)
                monthly_forecast.predictedMonth1KWh = p1

                # 2. حقن P1 كشهر مفترض في المتسلسلة والتنبؤ بـ P2 للشهر الثاني تكرارياً
                historical_plus_p1 = historical_months + [float(p1)]
                p2 = predict_monthly_consumption(historical_plus_p1)
                monthly_forecast.predictedMonth2KWh = p2

                monthly_forecast.actualMonth1KWh = None
                
                # 3. حساب الفاتورة الأولية التقديرية كـ (P1 التقديري + P2 التقديري)
                total_cycle_kwh = p1 + p2
                monthly_forecast.expectedBillSYP = TariffService.calculate_syrian_cost(total_cycle_kwh, target_date)
                monthly_forecast.save()

        return monthly_forecast