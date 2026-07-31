from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
from django.utils.timezone import make_aware
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum

from core.models import Meter, Budget, DailyForecast, MonthlyForecast, TariffVersion, DailyConsumptionSummary
from core.services.tariff_service import TariffService
from core.services.cache_service import CacheService

class DashboardService:

    @classmethod
    def get_dashboard_data(cls, meter_id: str, simulated_date_str: str = None) -> dict:
        meter = Meter.objects.get(pk=meter_id)

        if simulated_date_str:
            current_date = datetime.strptime(simulated_date_str, "%Y-%m-%d").date()
        else:
            current_date = date.today()

        year = current_date.year
        month = current_date.month

        # 1. تحديد حدود الدورة الفوترية
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

        days_passed = (current_date - cycle_start_date).days + 1
        total_cycle_days = (cycle_end_date - cycle_start_date).days + 1
        days_remaining = total_cycle_days - days_passed
        yesterday_date = current_date - timedelta(days=1)

        # 2. السرعة الفائقة: حساب استهلاك الدورة التراكمي المباشر بحركة واحدة من DailyConsumptionSummary
        cycle_sum = DailyConsumptionSummary.objects.filter(
            meter=meter,
            date__gte=cycle_start_date,
            date__lte=current_date
        ).aggregate(total=Sum('totalKWh'))['total']

        cycle_consumption_kwh = round(cycle_sum or Decimal('0.00'), 2)
        accumulated_cost_syp = TariffService.calculate_syrian_cost(cycle_consumption_kwh, current_date)

        # الكاش للبيانات الثابتة
        cache_key_static = CacheService.get_dashboard_key(meter_id, current_date)
        static_data = cache.get(cache_key_static)

        if not static_data:
            # استهلاك الأيام المنقضية حتى الأمس المكتمل مباشرة
            yesterday_sum = DailyConsumptionSummary.objects.filter(
                meter=meter,
                date__gte=cycle_start_date,
                date__lte=yesterday_date
            ).aggregate(total=Sum('totalKWh'))['total']
            yesterday_consumption_kwh = round(yesterday_sum or Decimal('0.00'), 2)

            remaining_days_with_today = days_remaining + 1
            div_days = Decimal(str(remaining_days_with_today))

            try:
                active_version = TariffVersion.objects.filter(effectiveDate__lte=current_date).order_by('-effectiveDate').first()
                tier1 = active_version.tiers.filter(tierNumber=1).first() if active_version else None
                support_limit = Decimal(str(tier1.endKWh)) if tier1 and tier1.endKWh else Decimal('300.00')
            except Exception:
                support_limit = Decimal('300.00')

            target_budget_syp = 0
            budget_limit = Decimal('0.00')
            try:
                budget = Budget.objects.get(meter=meter)
                budget_limit = budget.equivalentLimitKWh
                target_budget_syp = int(budget.targetBudgetSYP)
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

            static_data = {
                "cycleProgressDays": days_passed,
                "cycleRemainingDays": days_remaining,
                "cycleStartDate": cycle_start_date.strftime("%Y-%m-%d"),
                "cycleEndDate": cycle_end_date.strftime("%Y-%m-%d"),
                "supportLimitKWh": float(support_limit),
                "budgetLimitKWh": float(budget_limit),
                "targetBudgetSYP": target_budget_syp,
                "predictedBillSYP": int(predicted_bill_syp),
                "predictedCycleConsumptionKWh": float(predicted_cycle_kwh),
                "todayPredictedKWh": float(today_predicted_kwh),
                "avgSubTargetKWh": float(avg_sub_target_kwh),
                "avgBudgetTargetKWh": float(avg_budget_target_kwh)
            }
            cache.set(cache_key_static, static_data, timeout=86400)

        # 3. جلب استهلاك اليوم الفعلي المباشر سحرياً من DailyConsumptionSummary
        today_summary = DailyConsumptionSummary.objects.filter(meter=meter, date=current_date).first()
        today_actual_kwh = round(today_summary.totalKWh, 2) if today_summary else Decimal('0.00')

        return {
            "meterId": meter_id,
            "simulatedDate": current_date.strftime("%Y-%m-%d"),
            "cycleProgressDays": static_data['cycleProgressDays'],
            "cycleRemainingDays": static_data['cycleRemainingDays'],
            "cycleStartDate": static_data['cycleStartDate'],
            "cycleEndDate": static_data['cycleEndDate'],
            "supportLimitKWh": static_data['supportLimitKWh'],
            "budgetLimitKWh": static_data['budgetLimitKWh'],
            "targetBudgetSYP": static_data['targetBudgetSYP'],
            "cycleActualConsumptionKWh": float(cycle_consumption_kwh),
            "accumulatedCostSYP": int(accumulated_cost_syp),
            "predictedBillSYP": static_data['predictedBillSYP'],
            "predictedCycleConsumptionKWh": static_data['predictedCycleConsumptionKWh'],
            "todayActualKWh": float(today_actual_kwh),
            "todayPredictedKWh": static_data['todayPredictedKWh'],
            "avgSubTargetKWh": static_data['avgSubTargetKWh'],
            "avgBudgetTargetKWh": static_data['avgBudgetTargetKWh']
        }