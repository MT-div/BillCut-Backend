from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils.timezone import make_aware
from datetime import datetime

# استيراد النماذج عند الحاجة فقط للاستعلامات البسيطة
from .models import Notification, NotificationSettings, User, Meter

# استيراد عقود البيانات (الـ DTOs)
from .serializers import (
    LoginSerializer, UserCreationSerializer, ProfileUpdateSerializer, 
    BudgetSerializer, DashboardResponseSerializer, ConsumptionUpdateSerializer, 
    BulkIngestionSerializer, AnalyticsResponseSerializer, NotificationSerializer, 
    NotificationSettingsUpdateSerializer, UserMeterPreferenceUpdateSerializer, 
    AssignMeterSerializer, UnassignMeterSerializer, TariffVersionCreateSerializer
)

# استيراد جميع الخدمات البرمجية المعزولة (The Service Layer)
from core.services.user_service import UserService
from core.services.meter_service import MeterService
from core.services.association_service import AssociationService
from core.services.tariff_service import TariffService
from core.services.budget_service import BudgetService
from core.services.dashboard_service import DashboardService
from core.services.analytics_service import AnalyticsService
from core.services.ingestion_service import IngestionService


# ==================== 1. واجهات التحقق والمستخدم والملف الشخصي ====================

class LoginAPIView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = authenticate(username=serializer.validated_data['username'], password=serializer.validated_data['password'])
            if user:
                return Response({
                    "status": "success",
                    "message": "تم تسجيل الدخول بنجاح.",
                    "user": {"id": user.id, "username": user.username, "fullName": user.fullName, "role": user.role}
                }, status=status.HTTP_200_OK)
            return Response({"status": "error", "message": "اسم المستخدم أو كلمة المرور غير صحيحة."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileUpdateAPIView(APIView):
    def post(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        if serializer.is_valid():
            username_to_update = request.data.get('username')
            try:
                user = User.objects.get(username=username_to_update)
            except User.DoesNotExist:
                return Response({"message": "المستخدم غير موجود."}, status=status.HTTP_404_NOT_FOUND)

            # تحقق أمني
            if not user.check_password(serializer.validated_data['currentPassword']):
                return Response({"message": "كلمة المرور الحالية غير صحيحة."}, status=status.HTTP_401_UNAUTHORIZED)

            # تفويض خدمة التعديل لطبقة الخدمات
            UserService.update_profile(user.id, serializer.validated_data['newPhone'], serializer.validated_data.get('newPassword'))
            return Response({"status": "success", "message": "تم تحديث بيانات الملف الشخصي بنجاح."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationSettingsAPIView(APIView):
    def get(self, request, user_id):
        try:
            settings = NotificationSettings.objects.get(user_id=user_id)
            serializer = NotificationSettingsUpdateSerializer(settings)
            return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)
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
            return Response({"status": "success", "message": "تم حفظ تفضيلات الإشعارات بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 2. واجهات الـ Dashboard والتحليلات والعدادات والـ Budget ====================

class MeterDashboardAPIView(APIView):
    def get(self, request, meter_id):
        simulated_date = request.query_params.get('simulated_date', None)
        try:
            dashboard_data = DashboardService.get_dashboard_data(meter_id, simulated_date)
            serializer = DashboardResponseSerializer(dashboard_data)
            return Response({"status": "success", "message": "تم استرداد بيانات لوحة المراقبة بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": f"حدث خطأ أثناء معالجة البيانات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MeterAnalyticsAPIView(APIView):
    def get(self, request, meter_id):
        simulated_date = request.query_params.get('simulated_date', None)
        try:
            analytics_data = AnalyticsService.get_analytics_data(meter_id, simulated_date)
            serializer = AnalyticsResponseSerializer(analytics_data)
            return Response({"status": "success", "message": "تم استرداد الرسوم البيانية بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": f"تعذر جلب البيانات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationLogAPIView(APIView):
    def get(self, request, meter_id):
        try:
            notifications = Notification.objects.filter(meter_id=meter_id).order_by('-timestamp')
            Notification.objects.filter(meter_id=meter_id, isRead=False).update(isRead=True)
            serializer = NotificationSerializer(notifications, many=True)
            return Response({"status": "success", "message": "تم استرداد السجل وتحديث القراءة.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": f"خطأ أثناء استرجاع التنبيهات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserMeterPreferenceAPIView(APIView):
    def put(self, request, preference_id):
        serializer = UserMeterPreferenceUpdateSerializer(data=request.data, partial=True)
        if serializer.is_valid():
            try:
                # تفويض خدمة التفضيلات المخصصة لطبقة الخدمات
                pref = MeterService.update_user_meter_preference(
                    preference_id, 
                    serializer.validated_data.get('alias'), 
                    serializer.validated_data.get('isDefault')
                )
                return Response({"status": "success", "message": "تم تحديث تفضيلات العداد بنجاح.", "data": UserMeterPreferenceUpdateSerializer(pref).data}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"message": f"خطأ داخلي: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetBudgetAPIView(APIView):
    def post(self, request, meter_id):
        serializer = BudgetSerializer(data=request.data)
        if serializer.is_valid():
            try:
                budget = BudgetService.set_or_update_budget(meter_id, serializer.validated_data['targetBudgetSYP'])
                return Response({"status": "success", "message": "تم تحديث الميزانية بنجاح.", "data": {"meterId": meter_id, "targetBudgetSYP": budget.targetBudgetSYP, "equivalentLimitKWh": budget.equivalentLimitKWh}}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "message": f"خطأ أثناء معالجة الطلب: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 3. واجهات إنترنت الأشياء واستقبال الاستهلاك للعداد الذكي ====================

class ConsumptionUpdateAPIView(APIView):
    def post(self, request, meter_id):
        serializer = ConsumptionUpdateSerializer(data=request.data)
        if serializer.is_valid():
            dt = make_aware(datetime.fromtimestamp(serializer.validated_data['timestamp']))
            try:
                reading = IngestionService.process_live_reading(meter_id, serializer.validated_data['watts'], dt)
                return Response({"status": "success", "message": "تم استلام القراءة اللحظية وتراكمها بنجاح.", "data": {"readingId": reading.readingId, "cumulativeWh": reading.cumulativeWh, "timestamp": reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")}}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "message": f"خطأ برمي أثناء الاستقبال: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BulkIngestionAPIView(APIView):
    def post(self, request, meter_id):
        serializer = BulkIngestionSerializer(data=request.data)
        if serializer.is_valid():
            try:
                records_created = IngestionService.process_bulk_backfill(meter_id, serializer.validated_data['readings'])
                return Response({"status": "success", "message": f"تم تهيئة وحقن {records_created} قراءة تاريخية بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "message": f"تعذر إتمام الحقن: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 4. واجهات الإدارة لمدير النظام (Admin CRUDs) ====================

class AdminCreateUserAPIView(APIView):
    def post(self, request):
        serializer = UserCreationSerializer(data=request.data)
        if serializer.is_valid():
            user, temp_password = UserService.create_resident_user(serializer.validated_data['fullName'], serializer.validated_data['phoneNumber'])
            return Response({"status": "success", "message": "تم إنشاء الحساب بنجاح.", "data": {"username": user.username, "fullName": user.fullName, "phoneNumber": user.phoneNumber, "temporaryPassword": temp_password}}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminUserDetailAPIView(APIView):
    def put(self, request, user_id):
        try:
            user = UserService.update_user_account(user_id, request.data.get('fullName'), request.data.get('phoneNumber'))
            return Response({"status": "success", "message": "تم تحديث حساب المستخدم بنجاح.", "data": {"userId": user.id, "fullName": user.fullName, "phoneNumber": user.phoneNumber}}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"عطل أثناء التحديث: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, user_id):
        try:
            UserService.delete_user_account(user_id)
            return Response({"status": "success", "message": "تم حذف حساب المستخدم وجميع ارتباطاته بنجاح."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"تعذر الحذف: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)


class AdminMeterListCreateAPIView(APIView):
    def post(self, request):
        meter_id_raw = request.data.get('meterId', None)
        if not meter_id_raw:
            return Response({"message": "يجب تزويد المعرّف الفيزيائي للعداد (UUID/MAC)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            meter = MeterService.add_new_meter(meter_id_raw)
            return Response({"status": "success", "message": "تم تسجيل العداد بنجاح.", "data": {"meterId": meter.meterId, "registerDate": meter.registerDate}}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"message": f"تعذر الإضافة: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class AdminMeterDetailAPIView(APIView):
    def delete(self, request, meter_id):
        try:
            MeterService.delete_meter(meter_id)
            return Response({"status": "success", "message": "تم حذف العداد الفيزيائي وجميع قراءاته نهائياً."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"العداد غير موجود: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)


class AdminMeterAssociationAPIView(APIView):
    def post(self, request):
        serializer = AssignMeterSerializer(data=request.data)
        if serializer.is_valid():
            try:
                pref = AssociationService.assign_meter_to_user(serializer.validated_data['meterId'], serializer.validated_data['userId'], serializer.validated_data['alias'])
                return Response({"status": "success", "message": "تم إسناد العداد للمستخدم بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminMeterUnassignmentAPIView(APIView):
    def post(self, request):
        serializer = UnassignMeterSerializer(data=request.data)
        if serializer.is_valid():
            try:
                AssociationService.unassign_meter_from_user(serializer.validated_data['meterId'], serializer.validated_data['userId'])
                return Response({"status": "success", "message": "تم إلغاء إسناد العداد بنجاح."}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"message": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminTariffUpdateAPIView(APIView):
    def post(self, request):
        serializer = TariffVersionCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                version = TariffService.create_new_tariff(serializer.validated_data['effectiveDate'], serializer.validated_data['tiers'])
                return Response({"status": "success", "message": f"تم تفعيل إصدار التعرفة الجديدة لعام {version.effectiveDate.year} بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"message": f"تعذر التحديث: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

# أضف هذا الكود في نهاية ملف core/views.py لتمثيل واجهة محاكاة عمليات منتصف الليل يدوياً

from core.services.task_service import TaskService

class AdminTriggerDailyTasksAPIView(APIView):
    def post(self, request, meter_id):
        # استقبال تاريخ اليوم المراد تشغيل محاكاة منتصف الليل له (مثل: "2026-07-23")
        target_date_str = request.data.get('date', None)
        if not target_date_str:
            return Response({"message": "يرجى تحديد تاريخ المحاكاة المستهدف."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            # 1. تشغيل التنبؤ اليومي وكشف خلل الأمس تلقائياً
            forecast = TaskService.run_daily_prediction_and_anomaly_detection(meter_id, target_date)
            # 2. تشغيل توليد الإشعارات التكيفية اليومية
            TaskService.run_daily_adaptive_notifications(meter_id, target_date)
            
            return Response({
                "status": "success",
                "message": f"تمت محاكاة وتشغيل مهام منتصف الليل بنجاح للتاريخ {target_date_str}.",
                "data": {
                    "isAnomalousDetected": forecast.isAnomalous,
                    "deviationKWh": forecast.deviationAmountKWh
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"خطأ تشغيلي: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)