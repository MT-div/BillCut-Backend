from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.db.models import Sum

from core.models import Meter, DailyForecast, MonthlyForecast, DailyConsumptionSummary
from core.ai_models.daily_model import predict_daily_consumption
from core.services.task_service import TaskService
from core.services.cache_service import CacheService

class AnalyticsService:

    @classmethod
    def get_analytics_data(cls, meter_id: str, simulated_date_str: str = None) -> dict:
        meter = Meter.objects.get(pk=meter_id)

        if simulated_date_str:
            current_date = datetime.strptime(simulated_date_str, "%Y-%m-%d").date()
        else:
            current_date = date.today()

        year = current_date.year
        month = current_date.month

        # ---------------------------------------------------------------------
        # 1. قراءة البيانات التاريخية والتنبؤية الثابتة لليوم من الكاش (Cache Lookup)
        # ---------------------------------------------------------------------
        cache_key_analytics = CacheService.get_analytics_key(meter_id, current_date)
        analytics_static = cache.get(cache_key_analytics)

        if not analytics_static:
            # أ. حساب السجل التاريخي لآخر 12 شهراً تقويمياً من DailyConsumptionSummary
            monthly_history = []
            for i in range(12, 0, -1):
                m_start, m_end = TaskService.get_exact_prior_month_range(current_date, i)

                m_sum = DailyConsumptionSummary.objects.filter(
                    meter=meter, date__gte=m_start, date__lte=m_end
                ).aggregate(total=Sum('totalKWh'))['total']

                m_consumption_kwh = round(m_sum or Decimal('0.00'), 2)

                monthly_history.append({
                    "monthName": m_start.strftime("%B %Y"),
                    "consumptionKWh": m_consumption_kwh
                })

            # ب. جلب التنبؤ الشهري الموحد المحدث من TaskService
            if month in [1, 2]:
                cycle_start_date = date(year, 1, 1)
            elif month in [3, 4]:
                cycle_start_date = date(year, 3, 1)
            elif month in [5, 6]:
                cycle_start_date = date(year, 5, 1)
            elif month in [7, 8]:
                cycle_start_date = date(year, 7, 1)
            elif month in [9, 10]:
                cycle_start_date = date(year, 9, 1)
            else:
                cycle_start_date = date(year, 11, 1)

            try:
                monthly_forecast = MonthlyForecast.objects.get(meter=meter, cycleStartDate=cycle_start_date)
            except ObjectDoesNotExist:
                monthly_forecast = TaskService.run_monthly_cycle_prediction(meter_id, current_date)

            analytics_static = {
                "monthlyHistory": monthly_history,
                "currentCycleForecast": {
                    "totalCycleConsumptionKWh": round(monthly_forecast.total_cycle_consumption_kwh, 2),
                    "expectedBillSYP": int(monthly_forecast.expectedBillSYP)
                }
            }
            # حفظ السجل التاريخي والتنبؤ الكاش لمدة 24 ساعة
            cache.set(cache_key_analytics, analytics_static, timeout=86400)

        # ---------------------------------------------------------------------
        # 2. سجل الـ 15 يوماً الأخيرة الشبه حي المباشر
        # ---------------------------------------------------------------------
        fifteen_days_ago = current_date - timedelta(days=14)
        
        existing_forecasts = DailyForecast.objects.filter(
            meter=meter, forecastDate__gte=fifteen_days_ago, forecastDate__lte=current_date
        )
        forecasts_map = {f.forecastDate: f for f in existing_forecasts}

        existing_summaries = DailyConsumptionSummary.objects.filter(
            meter=meter, date__gte=fifteen_days_ago, date__lte=current_date
        )
        summaries_map = {s.date: s.totalKWh for s in existing_summaries}

        daily_history = []
        forecasts_to_update = []
        forecasts_to_create = []

        for i in range(14, -1, -1):
            target_date = current_date - timedelta(days=i)
            day_actual_kwh = round(summaries_map.get(target_date, Decimal('0.00')), 2)

            daily_forecast = forecasts_map.get(target_date)

            if daily_forecast:
                if daily_forecast.actualConsumptionKWh != day_actual_kwh:
                    daily_forecast.actualConsumptionKWh = day_actual_kwh
                    deviation = day_actual_kwh - daily_forecast.predictedConsumptionKWh
                    daily_forecast.deviationAmountKWh = max(Decimal('0.00'), deviation)
                    if daily_forecast.predictedConsumptionKWh > 0 and (deviation / daily_forecast.predictedConsumptionKWh) > Decimal('0.40'):
                        daily_forecast.isAnomalous = True
                    forecasts_to_update.append(daily_forecast)
            else:
                mock_history = [Decimal('12.50')]
                pred_daily = predict_daily_consumption(mock_history)
                deviation = day_actual_kwh - pred_daily
                is_anomalous = pred_daily > 0 and (deviation / pred_daily) > Decimal('0.40')

                daily_forecast = DailyForecast(
                    meter=meter,
                    forecastDate=target_date,
                    predictedConsumptionKWh=pred_daily,
                    actualConsumptionKWh=day_actual_kwh,
                    isAnomalous=is_anomalous,
                    deviationAmountKWh=max(Decimal('0.00'), deviation)
                )
                forecasts_to_create.append(daily_forecast)

            daily_history.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "actualKWh": daily_forecast.actualConsumptionKWh,
                "predictedKWh": daily_forecast.predictedConsumptionKWh,
                "isAnomalous": daily_forecast.isAnomalous,
                "deviationKWh": daily_forecast.deviationAmountKWh
            })

        if forecasts_to_update:
            DailyForecast.objects.bulk_update(forecasts_to_update, ['actualConsumptionKWh', 'deviationAmountKWh', 'isAnomalous'])
        if forecasts_to_create:
            DailyForecast.objects.bulk_create(forecasts_to_create)

        return {
            "meterId": meter_id,
            "monthlyHistory": analytics_static["monthlyHistory"],
            "currentCycleForecast": analytics_static["currentCycleForecast"],
            "dailyHistory": daily_history
        }