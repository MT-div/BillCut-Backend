from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils.timezone import make_aware
from core.models import Meter, DailyForecast, MonthlyForecast, Notification, NotificationSettings, UserMeterPreference
from core.ai_models.daily_model import predict_daily_consumption
from core.ai_models.monthly_model import predict_monthly_consumption
from core.services.dashboard_service import DashboardService

class TaskService:

    @classmethod
    def run_daily_prediction_and_anomaly_detection(cls, meter_id: str, target_date: date) -> DailyForecast:
        """
        [UC_8] تشغيل محرك التنبؤ اليومي للغد وكشف شذوذ الأمس عند منتصف الليل
        """
        meter = Meter.objects.get(pk=meter_id)
        yesterday_date = target_date - timedelta(days=1)

        # 1. جلب استهلاك الأمس الفعلي بدقة
        yesterday_start_dt = make_aware(datetime.combine(yesterday_date, datetime.min.time()))
        yesterday_end_dt = make_aware(datetime.combine(yesterday_date, datetime.max.time()))
        
        start_reading = meter.readings.filter(timestamp__gte=yesterday_start_dt).order_by('timestamp').first()
        end_reading = meter.readings.filter(timestamp__lte=yesterday_end_dt).order_by('timestamp').last()

        yesterday_actual_kwh = Decimal('0.00')
        if start_reading and end_reading:
            yesterday_actual_kwh = round((end_reading.cumulativeWh - start_reading.cumulativeWh) / Decimal('1000.00'), 2)

        # 2. استدعاء نموذج التنبؤ اليومي لمحاكاة استهلاك الغد (Target Date)
        mock_history = [Decimal('12.50'), Decimal('14.20'), Decimal('11.80')]
        predicted_today = predict_daily_consumption(mock_history)

        # 3. تحديث أو إنشاء سجل التنبؤ والتحقق من الشذوذ لليوم المنقضي
        forecast, created = DailyForecast.objects.update_or_create(
            meter=meter,
            forecastDate=target_date,
            defaults={
                'predictedConsumptionKWh': predicted_today,
                'actualConsumptionKWh': yesterday_actual_kwh
            }
        )

        # حساب الانحراف
        deviation = yesterday_actual_kwh - forecast.predictedConsumptionKWh
        forecast.deviationAmountKWh = max(Decimal('0.00'), deviation)

        # إذا تجاوز الاستهلاك التنبؤ بـ 40% (كشف عطل أو تسريب)
        if forecast.predictedConsumptionKWh > 0 and (deviation / forecast.predictedConsumptionKWh) > Decimal('0.40'):
            forecast.isAnomalous = True
            # [UC_8 -> UC_UrgentAnomalyAlert (Extend)] توليد إشعار عاجل فوري
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
    def run_daily_adaptive_notifications(cls, meter_id: str, target_date: date) -> None:
        """
        [UC_10] توليد وإرسال الإشعارات التكيفية اليومية بناءً على إغلاق الأمس
        """
        meter = Meter.objects.get(pk=meter_id)
        
        # جلب تفاصيل لوحة التحكم الحالية للوصول للمتوسطات والأرقام المحدثة
        dashboard_data = DashboardService.get_dashboard_data(meter_id, target_date.strftime("%Y-%m-%d"))
        
        avg_sub = Decimal(str(dashboard_data['avgSubTargetKWh']))
        actual_today = Decimal(str(dashboard_data['todayActualKWh']))
        predicted_today = Decimal(str(dashboard_data['todayPredictedKWh']))

        # صياغة وإرسال التنبيه المناسب بناءً على سلوك الاستهلاك الفعلي
        if actual_today > predicted_today:
            # تجاوز معدل الاستهلاك
            title = "تنبيه: تجاوز معدل الشريحة"
            message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي للبقاء في الدعم. معدلك اليومي الجديد هو {avg_sub} ك.و.س."
            msg_type = "TIER"
        else:
            # التزام بمعدل الشريحة
            title = "أحسنت: التزام بالدعم"
            message = f"رائع! حافظت بالأمس على استهلاكك ضمن نطاق الشريحة المدعومة. معدلك اليومي المتاح هو {avg_sub} ك.و.س."
            msg_type = "TIER"

        # حفظ التنبيه التكيفي في أرشيف الإشعارات الداخلي للمستخدم
        Notification.objects.create(
            meter=meter,
            title=title,
            message=message,
            type=msg_type,
            isRead=False
        )