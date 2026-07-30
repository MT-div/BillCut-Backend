import requests
import logging

logger = logging.getLogger(__name__)

class PushService:
    """
    خدمة معزولة لإرسال إشعارات الدفع الخارجية (Push Notifications) 
    عبر سيرفرات Expo الرسمية.
    """
    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

    @classmethod
    def send_push_notification(cls, user, title: str, body: str, data: dict = None) -> bool:
        # التحقق من امتلاك المستخدم لـ pushToken صالح ينتمي لـ Expo
        if not user.pushToken or not user.pushToken.startswith("ExponentPushToken"):
            return False

        payload = {
            "to": user.pushToken,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {},
            "priority": "high",
        }

        try:
            response = requests.post(cls.EXPO_PUSH_URL, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info(f"تم إرسال إشعار Push بنجاح للمستخدم {user.username}")
                return True
            else:
                logger.error(f"فشل إرسال Push: {response.text}")
                return False
        except Exception as e:
            logger.error(f"خطأ أثناء الاتصال بسيرفر Expo Push: {str(e)}")
            return False