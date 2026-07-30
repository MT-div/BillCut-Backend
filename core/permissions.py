from django.conf import settings
from rest_framework.permissions import BasePermission

# 1. صلاحية خاصة تفتح الواجهات لمدراء النظام النشطين فقط (Admin Only)
class IsAdminUserOnly(BasePermission):
    def has_permission(self, request, view):
        # التحقق من أن المستخدم مسجل دخوله ويحمل صلاحية ADMIN في حسابه
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'ADMIN'
        )

# 2. صلاحية خاصة تفتح الواجهات للمستهلكين المنزليين النشطين فقط (Resident Only)
class IsResidentUserOnly(BasePermission):
    def has_permission(self, request, view):
        # التحقق من أن المستخدم مسجل دخوله ويحمل صلاحية RESIDENT في حسابه
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'RESIDENT'
        )
    


class HasMeterApiKey(BasePermission):
    def has_permission(self, request, view):
        # 1. قراءة الهيدر بمرونة عالية (Case-Insensitive)
        api_key = (
            request.headers.get('X-Meter-Api-Key') or 
            request.headers.get('x-meter-api-key') or 
            request.META.get('HTTP_X_METER_API_KEY')
        )
        
        expected_key = getattr(settings, 'METER_API_KEY', None)
        
        if not api_key or not expected_key:
            return False

        # 2. مطابقة المفتاحين بعد إزالة أي مسافات مخفية
        return api_key.strip() == str(expected_key).strip()