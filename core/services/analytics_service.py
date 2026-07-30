from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist
from core.models import Meter, ConsumptionReading, DailyForecast, MonthlyForecast
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

        # =========================================================
        # 1. حساب وتجميع الاستهلاك الفعلي لآخر 12 شهراً سابقة (kWh)
        # =========================================================
        monthly_history = []
        historical_consumptions_for_ai = []

        for i in range(12, 0, -1):
            first_day_of_month = (current_date - timedelta(days=i*30)).replace(day=1)
            next_month = first_day_of_month + timedelta(days=32)
            last_day_of_month = next_month.replace(day=1) - timedelta(days=1)

            start_dt = make_aware(datetime.combine(first_day_of_month, datetime.min.time()))
            end_dt = make_aware(datetime.combine(last_day_of_month, datetime.max.time()))

            start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=start_dt).order_by('timestamp').first()
            end_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=end_dt).order_by('timestamp').last()

            m_consumption_kwh = Decimal('0.00')
            if start_reading and end_reading:
                m_consumption_wh = end_reading.cumulativeWh - start_reading.cumulativeWh
                m_consumption_kwh = round(m_consumption_wh / Decimal('1000.00'), 2)

            monthly_history.append({
                "monthName": first_day_of_month.strftime("%B %Y"),
                "consumptionKWh": round(m_consumption_kwh, 2)
            })
            historical_consumptions_for_ai.append(m_consumption_kwh)

        # =========================================================
        # 2. حساب وعرض التنبؤ الشهري للدورة الكهربائية الحالية
        # =========================================================
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

        # =========================================================
        # 3. تحسين الأداء: تجميع التنبؤات اليومية للـ 15 يوماً في استعلام واحد (Bulk Fetch)
        # =========================================================
        fifteen_days_ago = current_date - timedelta(days=14)
        
        # استعلام واحد فقط بدلاً من 15 استعلاماً منفصلاً
        existing_forecasts = DailyForecast.objects.filter(
            meter=meter,
            forecastDate__gte=fifteen_days_ago,
            forecastDate__lte=current_date
        )
        # تحويل النتائج إلى قاموس سريع البحث في الذاكرة Dictionary Lookup (O(1) Time Complexity)
        forecasts_map = {f.forecastDate: f for f in existing_forecasts}

        daily_history = []
        forecasts_to_update = []
        forecasts_to_create = []

        for i in range(14, -1, -1):
            target_date = current_date - timedelta(days=i)
            target_start_dt = make_aware(datetime.combine(target_date, datetime.min.time()))
            target_end_dt = make_aware(datetime.combine(target_date, datetime.max.time()))

            day_start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=target_start_dt).order_by('timestamp').first()
            day_end_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=target_end_dt).order_by('timestamp').last()

            day_actual_kwh = Decimal('0.00')
            if day_start_reading and day_end_reading:
                day_wh = day_end_reading.cumulativeWh - day_start_reading.cumulativeWh
                day_actual_kwh = round(day_wh / Decimal('1000.00'), 2)

            # البحث في الذاكرة المخبئية بدلاً من ضرب الداتابيز لكل يوم
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
                "actualKWh": round(daily_forecast.actualConsumptionKWh, 2),
                "predictedKWh": round(daily_forecast.predictedConsumptionKWh, 2),
                "isAnomalous": daily_forecast.isAnomalous,
                "deviationKWh": round(daily_forecast.deviationAmountKWh, 2)
                 })
        # حفظ التعديلات والإضافات الجديدة بضربة واحدة في قاعدة البيانات (Bulk Save)
        if forecasts_to_update:
            DailyForecast.objects.bulk_update(
                forecasts_to_update, 
                ['actualConsumptionKWh', 'deviationAmountKWh', 'isAnomalous']
            )
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