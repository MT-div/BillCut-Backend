from datetime import datetime 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils.timezone import make_aware

# بقية الكود كما هو تماماً دون أي تغيير...

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
    

# أضف هذا الكود في نهاية ملف core/views.py تماماً لبرمجة متحكم الـ Dashboard

from core.services.dashboard_service import DashboardService
from .serializers import DashboardResponseSerializer


# أضف هذا الأكواد في نهاية ملف core/views.py لبرمجة متحكمات الواجهات البرمجية لإنترنت الأشياء والـ Dashboard

from django.utils.timezone import make_aware
from core.services.ingestion_service import IngestionService
from .serializers import ConsumptionUpdateSerializer, BulkIngestionSerializer, DashboardResponseSerializer

# 1. واجهة استقبال قراءة العداد بالواط اللحظي والتراكم التلقائي (Live Ingestion API)
class ConsumptionUpdateAPIView(APIView):
    def post(self, request, meter_id):
        serializer = ConsumptionUpdateSerializer(data=request.data)
        if serializer.is_valid():
            watts = serializer.validated_data['watts']
            timestamp_raw = serializer.validated_data['timestamp']
            
            # تحويل الطابع الزمني وتأصيل منطق المنطقة الزمنية لدجانغو
            dt = make_aware(datetime.fromtimestamp(timestamp_raw))
            
            try:
                # استدعاء خدمة استقبال وحساب وتراكم الاستهلاك
                reading = IngestionService.process_live_reading(meter_id, watts, dt)
                return Response({
                    "status": "success",
                    "message": "تم استلام قراءة الواط اللحظية وتراكمها بنجاح.",
                    "data": {
                        "readingId": reading.readingId,
                        "cumulativeWh": reading.cumulativeWh,
                        "timestamp": reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": f"خطأ برمي أثناء استقبال البيانات: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 2. واجهة الحقن والتهيئة الجماعية التراكمية التاريخية للعداد (Bulk Import API)
class BulkIngestionAPIView(APIView):
    def post(self, request, meter_id):
        serializer = BulkIngestionSerializer(data=request.data)
        if serializer.is_valid():
            readings_data = serializer.validated_data['readings']
            
            try:
                # استدعاء خدمة معالجة وحقن البيانات الجماعية المجمعة (O(1) Transaction)
                records_created = IngestionService.process_bulk_backfill(meter_id, readings_data)
                return Response({
                    "status": "success",
                    "message": f"تم تهيئة وحقن {records_created} قراءة تاريخية مجمعة للعداد بنجاح."
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": f"تعذر إتمام الحقن الجماعي: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 3. واجهة الـ Dashboard التفاعلية واللحظية المحدثة بنظام الكاش السريع
class MeterDashboardAPIView(APIView):
    def get(self, request, meter_id):
        simulated_date = request.query_params.get('simulated_date', None)
        
        try:
            # استدعاء الخدمة الحسابية اللحظية والذكية للحساب بالاستعانة بالكاش
            dashboard_data = DashboardService.get_dashboard_data(meter_id, simulated_date)
            serializer = DashboardResponseSerializer(dashboard_data)
            return Response({
                "status": "success",
                "message": "تم استرداد بيانات لوحة المراقبة بنجاح باستخدام ذاكرة الكاش السريعة.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"حدث خطأ أثناء تجميع البيانات: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


from core.services.analytics_service import AnalyticsService
from .serializers import (
    AnalyticsResponseSerializer, 
    NotificationSerializer, 
    NotificationSettingsUpdateSerializer
)
from .models import Notification, NotificationSettings, User

# 1. واجهة التحليلات والتنبؤ والخلل الموحدة (View Analytics API)
class MeterAnalyticsAPIView(APIView):
    def get(self, request, meter_id):
        simulated_date = request.query_params.get('simulated_date', None)
        try:
            # استدعاء الخدمة البيانية الموحدة لحساب وعرض المخططات
            analytics_data = AnalyticsService.get_analytics_data(meter_id, simulated_date)
            serializer = AnalyticsResponseSerializer(analytics_data)
            return Response({
                "status": "success",
                "message": "تم استرداد بيانات التحليلات والرسوم البيانية بنجاح.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"تعذر جلب بيانات التحليلات: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 2. واجهة مركز الإشعارات وتصفير القراءة التلقائي الجماعي (Notification Center API)
class NotificationLogAPIView(APIView):
    def get(self, request, meter_id):
        try:
            # جلب كافة الإشعارات للعداد المذكور مرتبة من الأحدث للأقدم
            notifications = Notification.objects.filter(meter_id=meter_id).order_by('-timestamp')
            
            # محاكاة التحديث الجماعي التراكمي (تصفير المقروئية لـ True بطلب واحد)
            Notification.objects.filter(meter_id=meter_id, isRead=False).update(isRead=True)
            
            serializer = NotificationSerializer(notifications, many=True)
            return Response({
                "status": "success",
                "message": "تم استرداد سجل الإشعارات الداخلي وتعيين حالتها كـ مقروءة.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"خطأ أثناء استرجاع التنبيهات: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 3. واجهة قراءة وتعديل تفضيلات الإشعارات للمستهلك (Notification Settings API)
class NotificationSettingsAPIView(APIView):
    def get(self, request, user_id):
        try:
            settings = NotificationSettings.objects.get(user_id=user_id)
            serializer = NotificationSettingsUpdateSerializer(settings)
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except NotificationSettings.DoesNotExist:
            return Response({"message": "الإعدادات غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, user_id):
        try:
            settings = NotificationSettings.objects.get(user_id=user_id)
        except NotificationSettings.DoesNotExist:
            return Response({"message": "الإعدادات غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

        serializer = NotificationSettingsUpdateSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "status": "success",
                "message": "تم حفظ تفضيلات وتصفية الإشعارات بنجاح.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)