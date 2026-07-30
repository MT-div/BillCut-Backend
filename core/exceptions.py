from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    مُعالج الاستثناءات المركزي الموحد للنظام:
    يقوم باعتراض جميع الأخطاء الصادرة من DRF أو الـ Validation أو السيرفر،
    ويغلفها بنمط موحد يفهمه الفرونت إند (Expo) بنسبة 100%:
    {"status": "error", "message": "نص الخطأ"}
    """
    # 1. استدعاء معالج الاستثناءات الافتراضي لـ DRF للحصول على الاستجابة الأولية
    response = exception_handler(exc, context)

    # 2. في حال كان الخطأ صادر من DRF (مثل ValidationError, PermissionDenied, NotFound...)
    if response is not None:
        customized_response = {"status": "error"}
        
        # استخراج رسالة الخطأ وتحويل القواميس/المصفوفات إلى نص مفهوم للمواطن
        if isinstance(response.data, dict):
            # إذا كان الخطأ عبارة عن قاموس حقول (Validation Errors)
            errors = []
            for field, error_list in response.data.items():
                if isinstance(error_list, list):
                    errors.append(f"{' '.join(error_list)}")
                else:
                    errors.append(f"{error_list}")
            customized_response["message"] = " ".join(errors) if errors else "حدث خطأ في المدخلات."
        elif isinstance(response.data, list):
            customized_response["message"] = " ".join(response.data)
        else:
            customized_response["message"] = str(response.data)

        response.data = customized_response
        return response

    # 3. في حال كان الخطأ غير متوقع في السيرفر (Unhandled 500 Server Error)
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return Response(
        {
            "status": "error",
            "message": "حدث خطأ غير متوقع في السيرفر. يرجى المحاولة لاحقاً."
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )