from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum

from core.models import Meter, DailyForecast, MonthlyForecast, DailyConsumptionSummary
from core.ai_models.monthly_model import predict_monthly_consumption
from core.ai_models.daily_model import predict_daily_consumption
from core.services.tariff_service import TariffService

class AnalyticsService:

    @classmethod
    def get_analytics_data(cls, meter_id: str, simulated_date_str: str = None) -> dict:
        meter = Meter.objects.get(pk=meter_id)

        if simulated_date_str:
            current_date = datetime.strptime(simulated_date_str, "%Y-%m-%d").date()
        else:
            current_date = date.today()

        # 1. تجميع الاستهلاك الشهري الفعلي لآخر 12 شهراً مباشرة من DailyConsumptionSummary
        monthly_history = []
        historical_consumptions_for_ai = []

        for i in range(12, 0, -1):
            first_day_of_month = (current_date - timedelta(days=i*30)).replace(day=1)
            next_month = first_day_of_month + timedelta(days=32)
            last_day_of_month = next_month.replace(day=1) - timedelta(days=1)

            m_sum = DailyConsumptionSummary.objects.filter(
                meter=meter,
                date__gte=first_day_of_month,
                date__lte=last_day_of_month
            ).aggregate(total=Sum('totalKWh'))['total']

            m_consumption_kwh = round(m_sum or Decimal('0.00'), 2)

            monthly_history.append({
                "monthName": first_day_of_month.strftime("%B %Y"),
                "consumptionKWh": m_consumption_kwh
            })
            historical_consumptions_for_ai.append(m_consumption_kwh)

        # 2. التنبؤ الشهري
        base_start_date = date(2025, 5, 1)
        delta_days = (current_date - base_start_date).days
        cycle_number = delta_days // 60
        cycle_start_date = base_start_date + timedelta(days=cycle_number * 60)

        try:
            monthly_forecast = MonthlyForecast.objects.get(meter=meter, cycleStartDate=cycle_start_date)
        except ObjectDoesNotExist:
            p1, p2 = predict_monthly_consumption(historical_consumptions_for_ai)
            expected_bill = TariffService.calculate_syrian_cost(p1 + p2)
            
            monthly_forecast = MonthlyForecast.objects.create(
                meter=meter,
                cycleStartDate=cycle_start_date,
                predictedMonth1KWh=p1,
                predictedMonth2KWh=p2,
                expectedBillSYP=expected_bill
            )

        # 3. سجل الـ 15 يوماً الأخيرة مباشرة وسريعاً من DailyConsumptionSummary
        fifteen_days_ago = current_date - timedelta(days=14)
        
        # استعلام واحد لجلب التنبؤات والملخصات اليومية
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
            "monthlyHistory": monthly_history,
            "currentCycleForecast": {
                "predictedMonth1KWh": round(monthly_forecast.predictedMonth1KWh, 2),
                "predictedMonth2KWh": round(monthly_forecast.predictedMonth2KWh, 2),
                "expectedBillSYP": int(monthly_forecast.expectedBillSYP)
            },
            "dailyHistory": daily_history
        }