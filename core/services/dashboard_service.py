from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from core.models import Meter, ConsumptionReading, Budget, DailyForecast, MonthlyForecast, TariffVersion

class DashboardService:

    @staticmethod
    def calculate_syrian_cost(consumption_kwh: Decimal) -> Decimal:
        try:
            active_version = TariffVersion.objects.get(isActive=True)
            tiers = active_version.tiers.order_by('tierNumber')
        except ObjectDoesNotExist:
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

    @classmethod
    def get_dashboard_data(cls, meter_id: str, simulated_date_str: str = None) -> dict:
        meter = Meter.objects.get(pk=meter_id)

        if simulated_date_str:
            current_date = datetime.strptime(simulated_date_str, "%Y-%m-%d").date()
        else:
            current_date = date.today()

        year = current_date.year
        month = current_date.month

        # صياغة الدورات السورية الثابتة
        if month in [1, 2]:
            cycle_start_date = date(year, 1, 1)
            is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            cycle_end_date = date(year, 2, 29 if is_leap else 28)
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

        days_passed = (current_date - cycle_start_date).days + 1
        total_cycle_days = (cycle_end_date - cycle_start_date).days + 1
        days_remaining = total_cycle_days - days_passed
        yesterday_date = current_date - timedelta(days=1)

        cycle_start_dt = make_aware(datetime.combine(cycle_start_date, datetime.min.time()))
        yesterday_end_dt = make_aware(datetime.combine(yesterday_date, datetime.max.time()))
        current_end_dt = make_aware(datetime.combine(current_date, datetime.max.time()))

        start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=cycle_start_dt).order_by('timestamp').first()
        latest_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=current_end_dt).order_by('timestamp').last()

        cycle_consumption_kwh = Decimal('0.00')
        if start_reading and latest_reading:
            consumption_wh = latest_reading.cumulativeWh - start_reading.cumulativeWh
            cycle_consumption_kwh = round(consumption_wh / Decimal('1000.00'), 2)

        accumulated_cost_syp = cls.calculate_syrian_cost(cycle_consumption_kwh)

        # الكاش للبيانات الثابتة
        cache_key_static = f"dashboard_static_v4_{meter_id}_{current_date.strftime('%Y%m%d')}"
        static_data = cache.get(cache_key_static)

        if not static_data:
            yesterday_end_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=yesterday_end_dt).order_by('timestamp').last()
            yesterday_consumption_kwh = Decimal('0.00')
            yesterday_end_wh = Decimal('0.00')
            
            if yesterday_end_reading:
                yesterday_end_wh = yesterday_end_reading.cumulativeWh
                if start_reading:
                    y_consumption_wh = yesterday_end_wh - start_reading.cumulativeWh
                    yesterday_consumption_kwh = round(y_consumption_wh / Decimal('1000.00'), 2)

            remaining_days_with_today = days_remaining + 1
            div_days = Decimal(str(remaining_days_with_today))

            try:
                active_version = TariffVersion.objects.get(isActive=True)
                tier1 = active_version.tiers.filter(tierNumber=1).first()
                support_limit = Decimal(str(tier1.endKWh)) if tier1 else Decimal('300.00')
            except ObjectDoesNotExist:
                support_limit = Decimal('300.00')

            # استرجاع الميزانية المالية بالليرة السورية لحل مشكلة الـ NaN
            target_budget_syp = 0
            budget_limit = Decimal('0.00')
            try:
                budget = Budget.objects.get(meter=meter)
                budget_limit = budget.equivalentLimitKWh
                target_budget_syp = int(budget.targetBudgetSYP) # تحويل لـ Integer
                avg_budget_target_kwh = round((budget.equivalentLimitKWh - yesterday_consumption_kwh) / div_days, 2)
                if avg_budget_target_kwh < 0:
                    avg_budget_target_kwh = Decimal('0.00')
            except ObjectDoesNotExist:
                avg_budget_target_kwh = Decimal('0.00')

            try:
                monthly_forecast = MonthlyForecast.objects.get(meter=meter, cycleStartDate=cycle_start_date)
                predicted_bill_syp = monthly_forecast.expectedBillSYP
                predicted_cycle_kwh = monthly_forecast.predictedMonth1KWh + monthly_forecast.predictedMonth2KWh
            except ObjectDoesNotExist:
                predicted_bill_syp = accumulated_cost_syp * (Decimal(str(total_cycle_days)) / Decimal(str(days_passed))) if days_passed > 0 else Decimal('0.00')
                predicted_cycle_kwh = Decimal('445.90')

            today_predicted_kwh = Decimal('0.00')
            try:
                daily_forecast = DailyForecast.objects.get(meter=meter, forecastDate=current_date)
                today_predicted_kwh = daily_forecast.predictedConsumptionKWh
            except ObjectDoesNotExist:
                today_predicted_kwh = Decimal('12.50')

            
            avg_sub_target_kwh = round((support_limit - yesterday_consumption_kwh) / div_days, 2)
            if avg_sub_target_kwh < 0:
                avg_sub_target_kwh = Decimal('0.00')

            avg_budget_target_kwh = Decimal('0.00')
            try:
                budget = Budget.objects.get(meter=meter)
                avg_budget_target_kwh = round((budget.equivalentLimitKWh - yesterday_consumption_kwh) / div_days, 2)
                if avg_budget_target_kwh < 0:
                    avg_budget_target_kwh = Decimal('0.00')
            except ObjectDoesNotExist:
                pass
            static_data = {
                "cycleProgressDays": days_passed,
                "cycleRemainingDays": days_remaining,
                "cycleStartDate": cycle_start_date.strftime("%Y-%m-%d"),
                "cycleEndDate": cycle_end_date.strftime("%Y-%m-%d"),
                "supportLimitKWh": float(support_limit),
                "budgetLimitKWh": float(budget_limit),
                "targetBudgetSYP": target_budget_syp, # إضافة القيمة المالية لحل الـ NaN
                "startReadingWh": float(start_reading.cumulativeWh) if start_reading else 0.0,
                "yesterdayEndReadingWh": float(yesterday_end_wh),
                "predictedBillSYP": int(predicted_bill_syp),
                "predictedCycleConsumptionKWh": float(predicted_cycle_kwh),
                "todayPredictedKWh": float(today_predicted_kwh),
                "avgSubTargetKWh": float(avg_sub_target_kwh),
                "avgBudgetTargetKWh": float(avg_budget_target_kwh)
            }
            cache.set(cache_key_static, static_data, timeout=86400)

        # 4. حساب الاستهلاك الحالي المتغير حياً
        today_actual_kwh = Decimal('0.00')
        if latest_reading:
            yesterday_end_wh = Decimal(str(static_data['yesterdayEndReadingWh']))
            if yesterday_end_wh == Decimal('0.00') and start_reading:
                yesterday_end_wh = start_reading.cumulativeWh
            
            today_wh = latest_reading.cumulativeWh - yesterday_end_wh
            today_actual_kwh = round(today_wh / Decimal('1000.00'), 2)

        return {
            "meterId": meter_id,
            "simulatedDate": current_date.strftime("%Y-%m-%d"),
            "cycleProgressDays": static_data['cycleProgressDays'],
            "cycleRemainingDays": static_data['cycleRemainingDays'],
            "cycleStartDate": static_data['cycleStartDate'],
            "cycleEndDate": static_data['cycleEndDate'],
            "supportLimitKWh": static_data['supportLimitKWh'],
            "budgetLimitKWh": static_data['budgetLimitKWh'],
            "targetBudgetSYP": static_data['targetBudgetSYP'], # إرجاع القيمة البرمجية لإنهاء الـ NaN
            "cycleActualConsumptionKWh": float(cycle_consumption_kwh),
            "accumulatedCostSYP": int(accumulated_cost_syp),
            "predictedBillSYP": static_data['predictedBillSYP'],
            "predictedCycleConsumptionKWh": static_data['predictedCycleConsumptionKWh'],
            "todayActualKWh": float(today_actual_kwh),
            "todayPredictedKWh": static_data['todayPredictedKWh'],
            "avgSubTargetKWh": static_data['avgSubTargetKWh'],
            "avgBudgetTargetKWh": static_data['avgBudgetTargetKWh']
        }