from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def _extract_error_messages(data):
    """
    دالة مساعدة تفكك المصفوفات والقواميس المعقدة (مثل أخطاء SimpleJWT)
    وتستخرج كافة النصوص بأمان دون حدوث TypeError
    """
    messages = []
    if isinstance(data, dict):
        for key, val in data.items():
            # يتجاهل الكلمات الكودية الروتينية مثل code أو token_class ويركز على الفحوى
            if key in ['code', 'token_class', 'token_type']:
                continue
            messages.extend(_extract_error_messages(val))
    elif isinstance(data, list):
        for item in data:
            messages.extend(_extract_error_messages(item))
    else:
        messages.append(str(data))
    return messages

def custom_exception_handler(exc, context):
    """
    مُعالج الاستثناءات المركزي الموحد للنظام:
    تحويل جميع أخطاء DRF و SimpleJWT إلى الغلاف الموحد:
    {"status": "error", "message": "نص الخطأ"}
    """
    response = exception_handler(exc, context)

    if response is not None:
        customized_response = {"status": "error"}
        extracted_msgs = _extract_error_messages(response.data)
        
        # دمج رسائل الأخطاء المستخرجة أو وضع رسالة افتراضية
        customized_response["message"] = " ".join(extracted_msgs) if extracted_msgs else "حدث خطأ في تنفيذ الطلب."
        response.data = customized_response
        return response

    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return Response(
        {
            "status": "error",
            "message": "حدث خطأ غير متوقع في السيرفر. يرجى المحاولة لاحقاً."
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )