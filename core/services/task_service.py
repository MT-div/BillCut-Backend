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
        day_before_yesterday_date = yesterday_date - timedelta(days=1)

        # حساب الحدود الزمنية الواعية لـ SQLite بالتوقيت الكامل الفعلي
        yesterday_end_dt = make_aware(datetime.combine(yesterday_date, datetime.max.time()))
        day_before_yesterday_end_dt = make_aware(datetime.combine(day_before_yesterday_date, datetime.max.time()))
        
        # تطبيق الطريقة الرياضية المثالية للـ Dashboard:
        # نطرح قراءة إغلاق أمس التراكمية من قراءة إغلاق قبل أمس لحساب صافي استهلاك الأمس المغلق بالكامل
        start_reading = meter.readings.filter(timestamp__lte=day_before_yesterday_end_dt).order_by('timestamp').last()
        end_reading = meter.readings.filter(timestamp__lte=yesterday_end_dt).order_by('timestamp').last()

        yesterday_actual_kwh = Decimal('0.00')
        if start_reading and end_reading:
            yesterday_actual_wh = end_reading.cumulativeWh - start_reading.cumulativeWh
            yesterday_actual_kwh = round(yesterday_actual_wh / Decimal('1000.00'), 2)

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
        [UC_10] توليد وإرسال الإشعارات التكيفية اليومية بناءً على استهلاك الأمس المكتمل والممرر كمعامل ذكي
        """
        meter = Meter.objects.get(pk=meter_id)
        
        # جلب تفاصيل لوحة التحكم الحالية للوصول للمتوسطات والأرقام المحدثة لليوم الحالي
        dashboard_data = DashboardService.get_dashboard_data(meter_id, target_date.strftime("%Y-%m-%d"))
        
        # 1. استخراج المتغيرات الأساسية لإعادة بناء وفحص أرقام أمس رياضياً
        cycle_consumption = Decimal(str(dashboard_data['cycleActualConsumptionKWh'])) # استهلاك الدورة الحالي شامل أمس
        remaining_days = int(dashboard_data['cycleRemainingDays']) # الأيام المتبقية لليوم وما بعده
        
        support_limit = Decimal(str(dashboard_data['supportLimitKWh']))
        budget_limit = Decimal(str(dashboard_data['budgetLimitKWh']))

        # حساب الاستهلاك التراكمي للدورة حتى بداية أمس (قبل إضافة استهلاك أمس الممرر الفعلي)
        consumption_before_yesterday = cycle_consumption - yesterday_actual_kwh
        
        # الأيام المتبقية التي كانت متاحة لأمس لتقسيم الميزانية عليها بالتساوي (بما فيها يوم أمس نفسه)
        yesterday_div_days = Decimal(str(remaining_days + 1))

        # ==================== أولاً: معالجة واحتساب إشعار الدعم والشرائح (TIER) ====================
        allowed_sub_yesterday = round((support_limit - consumption_before_yesterday) / yesterday_div_days, 2)
        if allowed_sub_yesterday < 0:
            allowed_sub_yesterday = Decimal('0.00')

        # الفحص المقارن بدقة لأمس (المقارنة بالاستهلاك الفعلي لليوم المنقضي الممرر)
        if yesterday_actual_kwh > allowed_sub_yesterday:
            title = "تنبيه: تجاوز معدل الشريحة"
            message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء في الدعم (المعدل المتاح كان {allowed_sub_yesterday} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي الجديد للأيام المتبقية أصبح {dashboard_data['avgSubTargetKWh']} ك.و.س."
            msg_type = "TIER"
        else:
            title = "أحسنت: التزام بالدعم"
            message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق الشريحة المدعومة (المعدل المتاح كان {allowed_sub_yesterday} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي المتاح للأيام المتبقية هو {dashboard_data['avgSubTargetKWh']} ك.و.س."
            msg_type = "TIER"

        Notification.objects.create(
            meter=meter,
            title=title,
            message=message,
            type=msg_type,
            isRead=False
        )

        # ==================== ثانياً: معالجة واحتساب إشعار الميزانية الشخصية (BUDGET) ====================
        if budget_limit > 0:
            allowed_budget_yesterday = round((budget_limit - consumption_before_yesterday) / yesterday_div_days, 2)
            if allowed_budget_yesterday < 0:
                allowed_budget_yesterday = Decimal('0.00')

            if yesterday_actual_kwh > allowed_budget_yesterday:
                b_title = "تنبيه: تجاوز معدل الميزانية"
                b_message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء ضمن ميزانيتك المحددة (المعدل المتاح كان {allowed_budget_yesterday} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي الجديد المتاح للميزانية هو {dashboard_data['avgBudgetTargetKWh']} ك.و.س."
                b_msg_type = "BUDGET"
            else:
                b_title = "أحسنت: التزام بالميزانية"
                b_message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق ميزانيتك الشخصية المستهدفة (المعدل المتاح كان {allowed_budget_yesterday} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual_kwh} ك.و.س). معدلك اليومي المتاح للالتزام بالميزانية هو {dashboard_data['avgBudgetTargetKWh']} ك.و.س."
                b_msg_type = "BUDGET"

            Notification.objects.create(
                meter=meter,
                title=b_title,
                message=b_message,
                type=b_msg_type,
                isRead=False
            )