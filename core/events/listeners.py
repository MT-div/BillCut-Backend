import logging
from django.dispatch import receiver
from core.models import Notification
from core.services.push_service import PushService
from .signals import (
    anomaly_detected_signal,
    budget_limit_exceeded_signal,
    tier_limit_exceeded_signal,
)

logger = logging.getLogger(__name__)

# ==================== 1. مراقب حدث كشف الخلل والشذوذ ====================
@receiver(anomaly_detected_signal)
def handle_anomaly_detected(sender, meter, forecast, **kwargs):
    """
    مراقب يتولى إجراءات الآثار الجانبية عند كشف شذوذ في الاستهلاك
    """
    title = "تحذير: عطل كهربائي محتمل!"
    message = f"تنبيه: تجاوز استهلاكك الفعلي بالأمس التنبؤ اليومي بمقدار {forecast.deviationAmountKWh} ك.و.س. يرجى التحقق من سلامة الأجهزة."

    # 1. إنشاء سجل التنبيه الداخلي في قواعد البيانات
    Notification.objects.create(
        meter=meter, title=title, message=message, type="ANOMALY", isRead=False
    )

    # 2. إرسال إشعار Push الخارجي للهاتف إذا كانت التفضيلات مفعلة
    for pref in meter.user_preferences.all():
        if hasattr(pref.user, 'notification_settings') and pref.user.notification_settings.anomalyPushEnabled:
            PushService.send_push_notification(pref.user, title, message)


# ==================== 2. مراقب حدث تقييم الشريحة والدعم ====================
@receiver(tier_limit_exceeded_signal)
def handle_tier_limit_exceeded(sender, meter, is_exceeded, yesterday_actual, allowed_target, new_target, **kwargs):
    """
    مراقب يتولى إجراءات تقييم الشريحة والتعرفة
    """
    if is_exceeded:
        title = "تنبيه: تجاوز معدل الشريحة"
        message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء في الدعم (المعدل المتاح كان {allowed_target} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual} ك.و.س). معدلك اليومي الجديد للأيام المتبقية أصبح {new_target} ك.و.س."
    else:
        title = "أحسنت: التزام بالدعم"
        message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق الشريحة المدعومة (المعدل المتاح كان {allowed_target} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual} ك.و.س). معدلك اليومي المتاح للأيام المتبقية هو {new_target} ك.و.س."

    # 1. حفظ التنبيه في الداتابيز
    Notification.objects.create(
        meter=meter, title=title, message=message, type="TIER", isRead=False
    )

    # 2. إرسال الـ Push الخارجي
    for pref in meter.user_preferences.all():
        if hasattr(pref.user, 'notification_settings') and pref.user.notification_settings.tierPushEnabled:
            PushService.send_push_notification(pref.user, title, message)


# ==================== 3. مراقب حدث تقييم الميزانية الشخصية ====================
@receiver(budget_limit_exceeded_signal)
def handle_budget_limit_exceeded(sender, meter, is_exceeded, yesterday_actual, allowed_target, new_target, **kwargs):
    """
    مراقب يتولى إجراءات تقييم ميزانية المستهلك
    """
    if is_exceeded:
        title = "تنبيه: تجاوز معدل الميزانية"
        message = f"انتبه: لقد تجاوزت بالأمس معدل الاستهلاك اليومي المتاح للبقاء ضمن ميزانيتك المحددة (المعدل المتاح كان {allowed_target} ك.و.س، بينما استهلاكك الفعلي كان {yesterday_actual} ك.و.س). معدلك اليومي الجديد المتاح للميزانية هو {new_target} ك.و.س."
    else:
        title = "أحسنت: التزام بالميزانية"
        message = f"رائع! حافظت بالأمس على استهلاكك اليومي ضمن نطاق ميزانيتك الشخصية المستهدفة (المعدل المتاح كان {allowed_target} ك.و.س، واستهلاكك الفعلي كان {yesterday_actual} ك.و.س). معدلك اليومي المتاح للالتزام بالميزانية هو {new_target} ك.و.س."

    # 1. حفظ التنبيه في الداتابيز
    Notification.objects.create(
        meter=meter, title=title, message=message, type="BUDGET", isRead=False
    )

    # 2. إرسال الـ Push الخارجي
    for pref in meter.user_preferences.all():
        if hasattr(pref.user, 'notification_settings') and pref.user.notification_settings.budgetPushEnabled:
            PushService.send_push_notification(pref.user, title, message)