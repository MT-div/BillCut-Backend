from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils.timezone import make_aware
from datetime import datetime
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken # استيراد محرك توليد الـ Tokens

# استيراد كلاسات الصلاحية المخصصة التي برمجناها
from .permissions import IsAdminUserOnly, IsResidentUserOnly

# استيراد النماذج والموديلات
from .models import Notification, NotificationSettings, User, Meter, UserMeterPreference

# استيراد عقود البيانات (الـ DTOs)
from .serializers import (
    LoginSerializer, PasswordUpdateSerializer, PhoneUpdateSerializer, UserCreationSerializer, ProfileUpdateSerializer, 
    BudgetSerializer, DashboardResponseSerializer, ConsumptionUpdateSerializer, 
    BulkIngestionSerializer, AnalyticsResponseSerializer, NotificationSerializer, 
    NotificationSettingsUpdateSerializer, UserMeterPreferenceUpdateSerializer, 
    AssignMeterSerializer, UnassignMeterSerializer, TariffVersionCreateSerializer
)

# استيراد الخدمات البرمجية المعزولة (The Service Layer)
from core.services.user_service import UserService
from core.services.meter_service import MeterService
from core.services.association_service import AssociationService
from core.services.tariff_service import TariffService
from core.services.budget_service import BudgetService
from core.services.dashboard_service import DashboardService
from core.services.analytics_service import AnalyticsService
from core.services.ingestion_service import IngestionService


# ==================== 1. واجهات التحقق والمستخدم والملف الشخصي ====================


# ابحث عن كلاس LoginAPIView في ملف core/views.py واستبدله كالتالي لإرجاع قائمة عدادات المستخدم ديناميكياً:

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = authenticate(username=serializer.validated_data['username'], password=serializer.validated_data['password'])
            if user:
                refresh = RefreshToken.for_user(user)
                refresh['role'] = user.role
                refresh['fullName'] = user.fullName

                # 1. جلب العداد الافتراضي للمستخدم
                default_pref = UserMeterPreference.objects.filter(user=user, isDefault=True).first()
                default_meter_id = str(default_pref.meter.meterId) if default_pref else None

                # 2. جلب جميع العدادات المرتبطة بحساب هذا المستخدم ديناميكياً لتغذية مبدل العدادات
                user_prefs = UserMeterPreference.objects.filter(user=user)
                meters_list = [
                    {
                        "preferenceId": p.id,
                        "meterId": str(p.meter.meterId),
                        "alias": p.alias,
                        "isDefault": p.isDefault
                    } for p in user_prefs
                ]

                return Response({
                    "status": "success",
                    "message": "تم تسجيل الدخول وتوليد الـ Tokens بنجاح.",
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "fullName": user.fullName,
                        "role": user.role,
                        "defaultMeterId": default_meter_id,
                        "meters": meters_list  # إرسال قائمة العدادات التفضيلية ديناميكياً
                    }
                }, status=status.HTTP_200_OK)
            return Response({"status": "error", "message": "اسم المستخدم أو كلمة المرور غير صحيحة."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class ProfileUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated] # حماية إلزامية بتسجيل الدخول

    def post(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        if serializer.is_valid():
            # أفضل ممارسة برمجية (Best Practice): جلب المستخدم الحالي تلقائياً من الـ Token لضمان الأمان المطلق
            user = request.user 

            # تحقق أمني من كلمة المرور الحالية
            if not user.check_password(serializer.validated_data['currentPassword']):
                return Response({"message": "كلمة المرور الحالية غير صحيحة."}, status=status.HTTP_401_UNAUTHORIZED)

            UserService.update_profile(user.id, serializer.validated_data['newPhone'], serializer.validated_data.get('newPassword'))
            return Response({"status": "success", "message": "تم تحديث بيانات الملف الشخصي بنجاح."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class NotificationSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly] # تفتح للمستهلكين المنزليين المسجلين فقط

    def get(self, request, user_id):
        # التحقق من أن المستخدم يطلب إعدادات حسابه هو فقط من الـ Token
        if request.user.id != user_id:
            return Response({"message": "عذراً، ليس لديك صلاحية تعديل حسابات مستخدمين آخرين."}, status=status.HTTP_403_FORBIDDEN)

        try:
            settings = NotificationSettings.objects.get(user_id=user_id)
            serializer = NotificationSettingsUpdateSerializer(settings)
            return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)
        except NotificationSettings.DoesNotExist:
            return Response({"message": "الإعدادات غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, user_id):
        if request.user.id != user_id:
            return Response({"message": "عذراً، ليس لديك صلاحية تعديل حسابات مستخدمين آخرين."}, status=status.HTTP_403_FORBIDDEN)

        try:
            settings = NotificationSettings.objects.get(user_id=user_id)
        except NotificationSettings.DoesNotExist:
            return Response({"message": "الإعدادات غير موجودة."}, status=status.HTTP_4404_NOT_FOUND)

        serializer = NotificationSettingsUpdateSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"status": "success", "message": "تم حفظ تفضيلات الإشعارات بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 2. واجهات الـ Dashboard والتحليلات والعدادات والـ Budget ====================

class MeterDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly] # حماية المستهلك

    def get(self, request, meter_id):
        # التحقق الأمني الثنائي: هل العداد المطلوب مسند ومرتبط فعلياً بحساب المستخدم الحالي المشفّر بالـ Token؟
        if not UserMeterPreference.objects.filter(user=request.user, meter_id=meter_id).exists():
            return Response({"status": "error", "message": "عذراً، ليس لديك الصلاحية الأمنية للوصول لبيانات هذا العداد الكهربائي."}, status=status.HTTP_403_FORBIDDEN)

        simulated_date = request.query_params.get('simulated_date', None)
        try:
            dashboard_data = DashboardService.get_dashboard_data(meter_id, simulated_date)
            serializer = DashboardResponseSerializer(dashboard_data)
            return Response({"status": "success", "message": "تم استرداد بيانات لوحة المراقبة بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": f"حدث خطأ أثناء معالجة البيانات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MeterAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly]

    def get(self, request, meter_id):
        if not UserMeterPreference.objects.filter(user=request.user, meter_id=meter_id).exists():
            return Response({"status": "error", "message": "عذراً، ليس لديك الصلاحية الأمنية للوصول لبيانات هذا العداد الكهربائي."}, status=status.HTTP_403_FORBIDDEN)

        simulated_date = request.query_params.get('simulated_date', None)
        try:
            analytics_data = AnalyticsService.get_analytics_data(meter_id, simulated_date)
            serializer = AnalyticsResponseSerializer(analytics_data)
            return Response({"status": "success", "message": "تم استرداد الرسوم البيانية بنجاح.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": f"تعذر جلب البيانات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



from rest_framework.pagination import LimitOffsetPagination # استيراد مكتبة الترقيم القياسية


class NotificationLogAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly]

    def get(self, request): # إلغاء معرّف العداد من الرابط ليعتمد كلياً على جلسة المستخدم الموحدة
        try:
            # 1. جلب قائمة بمعرفات جميع العدادات المرتبطة بحساب المستخدم الحالي الموثق بالتوكن
            user_meters = UserMeterPreference.objects.filter(user=request.user).values_list('meter_id', flat=True)
            
            # 2. جلب جميع الإشعارات التابعة لكافة عداداته مرتبة زمنياً من الأحدث للأقدم
            queryset = Notification.objects.filter(meter_id__in=user_meters).order_by('-timestamp')
            
            # 3. تطبيق الترقيم والتحميل التدريجي (Pagination)
            paginator = LimitOffsetPagination()
            paginator.default_limit = 10
            page = paginator.paginate_queryset(queryset, request, view=self)
            
            if page is not None:
                # تحديث حالة المقروئية فقط للإشعارات المعروضة في الصفحة الحالية
                unread_ids = [n.notificationId for n in page if not n.isRead]
                if unread_ids:
                    Notification.objects.filter(notificationId__in=unread_ids).update(isRead=True)
                
                # نمرر الـ request كـ context لـ Serializer لتأصيل استرجاع الاسم المستعار بدقة
                serializer = NotificationSerializer(page, many=True, context={'request': request})
                return paginator.get_paginated_response(serializer.data)

            serializer = NotificationSerializer(queryset, many=True, context={'request': request})
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"خطأ أثناء استرجاع التنبيهات: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class UserMeterPreferenceAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly]

    def put(self, request, preference_id):
        serializer = UserMeterPreferenceUpdateSerializer(data=request.data, partial=True)
        if serializer.is_valid():
            try:
                # التحقق الأمني من أن سجل التفضيل ينتمي للمستخدم الحالي نفسه
                pref_check = UserMeterPreference.objects.get(pk=preference_id)
                if pref_check.user != request.user:
                    return Response({"message": "عذراً، ليس لديك صلاحية تعديل تفضيلات عداد لمستخدم آخر."}, status=status.HTTP_403_FORBIDDEN)

                pref = MeterService.update_user_meter_preference(
                    preference_id, 
                    serializer.validated_data.get('alias'), 
                    serializer.validated_data.get('isDefault')
                )
                return Response({"status": "success", "message": "تم تحديث تفضيلات العداد بنجاح.", "data": UserMeterPreferenceUpdateSerializer(pref).data}, status=status.HTTP_200_OK)
            except UserMeterPreference.DoesNotExist:
                return Response({"message": "السجل غير موجود."}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({"message": f"خطأ داخلي: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetBudgetAPIView(APIView):
    permission_classes = [IsAuthenticated, IsResidentUserOnly]

    def post(self, request, meter_id):
        if not UserMeterPreference.objects.filter(user=request.user, meter_id=meter_id).exists():
            return Response({"status": "error", "message": "عذراً، ليس لديك الصلاحية الأمنية للوصول لبيانات هذا العداد الكهربائي."}, status=status.HTTP_403_FORBIDDEN)

        serializer = BudgetSerializer(data=request.data)
        if serializer.is_valid():
            try:
                budget = BudgetService.set_or_update_budget(meter_id, serializer.validated_data['targetBudgetSYP'])
                return Response({"status": "success", "message": "تم تحديث الميزانية بنجاح.", "data": {"meterId": meter_id, "targetBudgetSYP": budget.targetBudgetSYP, "equivalentLimitKWh": budget.equivalentLimitKWh}}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "message": f"خطأ أثناء معالجة الطلب: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 3. واجهات إنترنت الأشياء (مفتوحة حالياً للتبسيط) ====================

class ConsumptionUpdateAPIView(APIView):
    permission_classes = [AllowAny] # مفتوحة حالياً للتبسيط بانتظام العتاد المادي

    def post(self, request, meter_id):
        serializer = ConsumptionUpdateSerializer(data=request.data)
        if serializer.is_valid():
            dt = make_aware(datetime.fromtimestamp(serializer.validated_data['timestamp']))
            try:
                reading = IngestionService.process_live_reading(meter_id, serializer.validated_data['watts'], dt)
                return Response({"status": "success", "message": "تم استلام القراءة اللحظية وتراكمها بنجاح.", "data": {"readingId": reading.readingId, "cumulativeWh": reading.cumulativeWh, "timestamp": reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")}}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "message": f"خطأ برمجي أثناء الاستقبال: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BulkIngestionAPIView(APIView):
    permission_classes = [AllowAny] # مفتوحة للحقن التأسيسي الأول للمحاكي

    def post(self, request, meter_id):
        serializer = BulkIngestionSerializer(data=request.data)
        if serializer.is_valid():
            try:
                records_created = IngestionService.process_bulk_backfill(meter_id, serializer.validated_data['readings'])
                return Response({"status": "success", "message": f"تم تهيئة وحقن {records_created} قراءة تاريخية بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "message": f"تعذر إتمام الحقن: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 4. واجهات الإدارة لمدير النظام (Admin Users Only) ====================

class AdminCreateUserAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly] # حظر وحماية للأدمن المسجل فقط

    def post(self, request):
        serializer = UserCreationSerializer(data=request.data)
        if serializer.is_valid():
            user, temp_password = UserService.create_resident_user(serializer.validated_data['fullName'], serializer.validated_data['phoneNumber'])
            return Response({"status": "success", "message": "تم إنشاء الحساب بنجاح.", "data": {"username": user.username, "fullName": user.fullName, "phoneNumber": user.phoneNumber, "temporaryPassword": temp_password}}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def delete(self, request, meter_id):
        try:
            MeterService.delete_meter(meter_id)
            return Response({"status": "success", "message": "تم حذف العداد الفيزيائي وجميع قراءاته نهائياً."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"العداد غير موجود: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)


class AdminMeterAssociationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def post(self, request):
        serializer = TariffVersionCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                version = TariffService.create_new_tariff(serializer.validated_data['effectiveDate'], serializer.validated_data['tiers'])
                return Response({"status": "success", "message": f"تم تفعيل إصدار التعرفة الجديدة لعام {version.effectiveDate.year} بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"message": f"تعذر التحديث: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class AdminTriggerDailyTasksAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def post(self, request, meter_id):
        target_date_str = request.data.get('date', None)
        if not target_date_str:
            return Response({"message": "يرجى تحديد تاريخ المحاكاة المستهدف."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            from core.services.task_service import TaskService
            
            # 1. تشغيل التنبؤ اليومي وكشف خلل الأمس وحساب قيمته الفعلية بدقة
            forecast = TaskService.run_daily_prediction_and_anomaly_detection(meter_id, target_date)
            
            # 2. تمرير القيمة الفعلية المستنتجة بدقة كمعامل ذكي لحل التداخل الحسابي
            TaskService.run_daily_adaptive_notifications(meter_id, target_date, forecast.actualConsumptionKWh)
            
            return Response({
                "status": "success",
                "message": f"تمت محاكاة وتشغيل مهام منتصف الليل بنجاح للتاريخ {target_date_str}.",
                "data": {
                    "isAnomalousDetected": forecast.isAnomalous,
                    "deviationKWh": float(forecast.deviationAmountKWh),
                    "yesterdayActualKWh": float(forecast.actualConsumptionKWh) # إرجاع القيمة للتأكيد البصري للفحص
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": f"خطأ تشغيلي: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

from rest_framework.throttling import UserRateThrottle


class SensitiveActionThrottle(UserRateThrottle):
    """
    Throttle مخصص للعمليات الحساسة أمنياً (تغيير هاتف / كلمة مرور)
    يمنع محاولات القوة الغاشمة (brute force) على check_password.
    تأكد من إضافة "sensitive_action" لإعدادات DEFAULT_THROTTLE_RATES في settings.py
    مثال: "sensitive_action": "5/min"
    """
    scope = "sensitive_action"



class PhoneUpdateAPIView(APIView):
    """
    Endpoint مستقل تماماً لتحديث رقم الهاتف فقط.
    كان سابقاً مدمجاً مع تحديث كلمة المرور بنفس الـ serializer وهذا كان
    يسبب تعارضاً في متطلبات الحقول (validation) بين حالتين مختلفتين منطقياً.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveActionThrottle]

    def post(self, request):
        serializer = PhoneUpdateSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user

            if not user.check_password(
                serializer.validated_data["currentPassword"]
            ):
                return Response(
                    {
                        "status": "error",
                        "message": "كلمة المرور الحالية غير صحيحة.",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            UserService.update_phone(
                user.id, serializer.validated_data["newPhone"]
            )
            return Response(
                {
                    "status": "success",
                    "message": "تم تحديث رقم الهاتف بنجاح.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordUpdateAPIView(APIView):
    """
    Endpoint مستقل تماماً لتحديث كلمة المرور فقط.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveActionThrottle]

    def post(self, request):
        serializer = PasswordUpdateSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user

            if not user.check_password(
                serializer.validated_data["currentPassword"]
            ):
                return Response(
                    {
                        "status": "error",
                        "message": "كلمة المرور الحالية غير صحيحة.",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # تحقق مطابقة كلمة المرور الجديدة وتأكيدها على مستوى الخادم أيضاً
            # (لا يكفي التحقق في الفرونت إند فقط)
            if (
                serializer.validated_data["newPassword"]
                != serializer.validated_data["confirmPassword"]
            ):
                return Response(
                    {
                        "status": "error",
                        "message": "كلمة المرور الجديدة وتأكيدها غير متطابقين.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            UserService.update_password(
                user.id, serializer.validated_data["newPassword"]
            )
            return Response(
                {
                    "status": "success",
                    "message": "تم تحديث كلمة المرور بنجاح.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)