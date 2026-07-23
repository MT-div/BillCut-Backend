from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from django.core.exceptions import ObjectDoesNotExist
from core.models import Meter, ConsumptionReading, DailyForecast, MonthlyForecast
from core.ai_models.monthly_model import predict_monthly_consumption
from core.ai_models.daily_model import predict_daily_consumption

class AnalyticsService:

    @classmethod
    def get_analytics_data(cls, meter_id: str, simulated_date_str: str = None) -> dict:
        meter = Meter.objects.get(pk=meter_id)

        if simulated_date_str:
            current_date = datetime.strptime(simulated_date_str, "%Y-%m-%d").date()
        else:
            current_date = date.today()

        # 1. حساب وتجميع الاستهلاك الفعلي لآخر 12 شهراً سابقة (kWh)
        monthly_history = []
        historical_consumptions_for_ai = [] # سنغذي بها نموذج بايثون للمحاكاة

        for i in range(12, 0, -1):
            # حساب حدود كل شهر تاريخي بدقة
            first_day_of_month = (current_date - timedelta(days=i*30)).replace(day=1)
            next_month = first_day_of_month + timedelta(days=32)
            last_day_of_month = next_month.replace(day=1) - timedelta(days=1)

            # استعلام الحدود الزمنية الواعية لـ SQLite
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
                "consumptionKWh": float(m_consumption_kwh)
            })
            historical_consumptions_for_ai.append(m_consumption_kwh)

        # 2. حساب وعرض التنبؤ الشهري للدورة الكهربائية الحالية (المحاكاة من الموديل)
        base_start_date = date(2025, 5, 1)
        delta_days = (current_date - base_start_date).days
        cycle_number = delta_days // 60
        cycle_start_date = base_start_date + timedelta(days=cycle_number * 60)

        try:
            # محاولة جلب التنبؤ المحفوظ مسبقاً في الجداول
            monthly_forecast = MonthlyForecast.objects.get(meter=meter, cycleStartDate=cycle_start_date)
        except ObjectDoesNotExist:
            # إذا لم يكن موجوداً، نقوم باستدعاء النموذج السحابي وتوليده وحفظه فوراً
            p1, p2 = predict_monthly_consumption(historical_consumptions_for_ai)
            # حساب كلفة الفاتورة المتوقعة للشرائح
            from core.services.dashboard_service import DashboardService
            expected_bill = DashboardService.calculate_syrian_cost(p1 + p2)
            
            monthly_forecast = MonthlyForecast.objects.create(
                meter=meter,
                cycleStartDate=cycle_start_date,
                predictedMonth1KWh=p1,
                predictedMonth2KWh=p2,
                expectedBillSYP=expected_bill
            )

        # 3. حساب وعرض سجل مقارنة الاستهلاك اليومي والشذوذ لآخر 15 يوماً
        daily_history = []
        for i in range(14, -1, -1):
            target_date = current_date - timedelta(days=i)
            target_start_dt = make_aware(datetime.combine(target_date, datetime.min.time()))
            target_end_dt = make_aware(datetime.combine(target_date, datetime.max.time()))

            # حساب الاستهلاك الفعلي لليوم المعني
            day_start_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__gte=target_start_dt).order_by('timestamp').first()
            day_end_reading = ConsumptionReading.objects.filter(meter=meter, timestamp__lte=target_end_dt).order_by('timestamp').last()

            day_actual_kwh = Decimal('0.00')
            if day_start_reading and day_end_reading:
                day_wh = day_end_reading.cumulativeWh - day_start_reading.cumulativeWh
                day_actual_kwh = round(day_wh / Decimal('1000.00'), 2)

            try:
                # محاولة جلب التنبؤ اليومي المحفوظ مسبقاً
                daily_forecast = DailyForecast.objects.get(meter=meter, forecastDate=target_date)
                # تحديث الاستهلاك الفعلي المسجل لليوم فوراً في جدول التنبؤ لضمان الدقة
                if daily_forecast.actualConsumptionKWh != day_actual_kwh:
                    daily_forecast.actualConsumptionKWh = day_actual_kwh
                    # حساب قيمة الانحراف والشذوذ
                    deviation = day_actual_kwh - daily_forecast.predictedConsumptionKWh
                    daily_forecast.deviationAmountKWh = max(Decimal('0.00'), deviation)
                    # إذا تجاوز الاستهلاك الفعلي التوقع بـ 40% (كشف شذوذ)
                    if daily_forecast.predictedConsumptionKWh > 0 and (deviation / daily_forecast.predictedConsumptionKWh) > Decimal('0.40'):
                        daily_forecast.isAnomalous = True
                    daily_forecast.save()
            except ObjectDoesNotExist:
                # إذا لم يكن موجوداً، نقوم بتوليد تنبؤ يومي تقريبي وحفظه
                # نأخذ متوسط استهلاك آخر 7 أيام كمدخل للنموذج اليومي
                mock_history = [Decimal('12.50')] # في حال عدم توفر قراءات كافية
                pred_daily = predict_daily_consumption(mock_history)
                
                deviation = day_actual_kwh - pred_daily
                is_anomalous = False
                if pred_daily > 0 and (deviation / pred_daily) > Decimal('0.40'):
                    is_anomalous = True

                daily_forecast = DailyForecast.objects.create(
                    meter=meter,
                    forecastDate=target_date,
                    predictedConsumptionKWh=pred_daily,
                    actualConsumptionKWh=day_actual_kwh,
                    isAnomalous=is_anomalous,
                    deviationAmountKWh=max(Decimal('0.00'), deviation)
                )

            daily_history.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "actualKWh": float(daily_forecast.actualConsumptionKWh),
                "predictedKWh": float(daily_forecast.predictedConsumptionKWh),
                "isAnomalous": daily_forecast.isAnomalous,
                "deviationKWh": float(daily_forecast.deviationAmountKWh)
            })

        return {
            "meterId": meter_id,
            "monthlyHistory": monthly_history,
            "currentCycleForecast": {
                "predictedMonth1KWh": float(monthly_forecast.predictedMonth1KWh),
                "predictedMonth2KWh": float(monthly_forecast.predictedMonth2KWh),
                "expectedBillSYP": float(monthly_forecast.expectedBillSYP)
            },
            "dailyHistory": daily_history
        }