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