from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate

# استيراد عقود البيانات (الـ DTOs)
from .serializers import (
    LoginSerializer, 
    UserCreationSerializer, 
    ProfileUpdateSerializer, 
    BudgetSerializer
)

# استيراد الخدمات البرمجية المعزولة (Services)
from core.services.auth_service import AuthService
from core.services.budget_service import BudgetService

# 1. واجهة تسجيل الدخول (Login Endpoint)
class LoginAPIView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            
            # التحقق الأمني من صحة الحساب وكلمة المرور عبر دجانغو
            user = authenticate(username=username, password=password)
            if user:
                return Response({
                    "status": "success",
                    "message": "تم تسجيل الدخول بنجاح.",
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "fullName": user.fullName,
                        "role": user.role
                    }
                }, status=status.HTTP_200_OK)
            return Response({
                "status": "error",
                "message": "اسم المستخدم أو كلمة المرور غير صحيحة."
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 2. واجهة إنشاء مستخدم جديد من قبل الأدمن (Admin Only Endpoint)
class AdminCreateUserAPIView(APIView):
    def post(self, request):
        serializer = UserCreationSerializer(data=request.data)
        if serializer.is_valid():
            full_name = serializer.validated_data['fullName']
            phone_number = serializer.validated_data['phoneNumber']
            
            # استدعاء الخدمة الأمنية لإنشاء المستخدم وتوليد كلمة المرور
            user, temp_password = AuthService.create_resident_user(full_name, phone_number)
            
            return Response({
                "status": "success",
                "message": "تم إنشاء الحساب بنجاح.",
                "data": {
                    "username": user.username,
                    "fullName": user.fullName,
                    "phoneNumber": user.phoneNumber,
                    "temporaryPassword": temp_password  # تعاد ليعرضها الأدمن للمستخدم
                }
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 3. واجهة تحديث الملف الشخصي وكلمة المرور من قبل المستخدم
class ProfileUpdateAPIView(APIView):
    def post(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        if serializer.is_valid():
            # في بيئة العمل سنأخذ المستخدم الحالي للجلسة، للتجريب سنقرأه من الطلب مؤقتاً
            # سنقوم بربط التوثيق وحماية الـ Endpoints بالـ Token لاحقاً بالتفصيل
            username_to_update = request.data.get('username')
            try:
                from core.models import User
                user = User.objects.get(username=username_to_update)
            except User.DoesNotExist:
                return Response({"message": "المستخدم غير موجود."}, status=status.HTTP_404_NOT_FOUND)

            # التحقق الأمني من كلمة المرور الحالية
            if not user.check_password(serializer.validated_data['currentPassword']):
                return Response({"message": "كلمة المرور الحالية غير صحيحة."}, status=status.HTTP_401_UNAUTHORIZED)

            # تحديث رقم الهاتف
            user.phoneNumber = serializer.validated_data['newPhone']
            
            # تحديث كلمة المرور الجديدة إن وجدت
            new_password = serializer.validated_data.get('newPassword')
            if new_password:
                user.set_password(new_password)
                
            user.save()
            return Response({
                "status": "success",
                "message": "تم تحديث بيانات الملف الشخصي بنجاح."
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 4. واجهة ضبط وتحديث ميزانية العداد وحساب الاستهلاك المعادل تلقائياً
class SetBudgetAPIView(APIView):
    def post(self, request, meter_id):
        serializer = BudgetSerializer(data=request.data)
        if serializer.is_valid():
            target_budget = serializer.validated_data['targetBudgetSYP']
            
            try:
                # استدعاء الخدمة المالية لحساب التعرفة العكسية وحفظ الميزانية
                budget = BudgetService.set_or_update_budget(meter_id, target_budget)
                return Response({
                    "status": "success",
                    "message": "تم حفظ وتحديث الميزانية بنجاح.",
                    "data": {
                        "meterId": meter_id,
                        "targetBudgetSYP": budget.targetBudgetSYP,
                        "equivalentLimitKWh": budget.equivalentLimitKWh
                    }
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": f"حدث خطأ أثناء معالجة الطلب: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)