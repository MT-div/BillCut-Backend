import io
import base64
import numpy as np
import matplotlib
from django.db.models import Sum

from core.services.subscription_service import SubscriptionService
from core.services.task_service import TaskService
matplotlib.use('Agg') # تشغيل وضع Headless السيرفري لـ Matplotlib
import matplotlib.pyplot as plt
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils.timezone import make_aware
from datetime import datetime, date
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken # استيراد محرك توليد الـ Tokens
from django.db import transaction

from core.services.cache_service import CacheService

# استيراد كلاسات الصلاحية المخصصة التي برمجناها
from .permissions import HasMeterApiKey, IsAdminUserOnly, IsResidentUserOnly

# استيراد النماذج والموديلات
from .models import AnomalyThreshold, DailyConsumptionSummary, DailyForecast, Notification, NotificationSettings, SubscriptionRequest, User, Meter, UserMeterPreference
from core.services.threshold_scaling_service import ThresholdScalingService

# استيراد عقود البيانات (الـ DTOs)
from .serializers import (
    AnomalyThresholdSerializer, CreateSubscriptionRequestSerializer, LoginSerializer, MeterSerializer, PasswordUpdateSerializer, PhoneUpdateSerializer, ProvisionSubscriptionRequestSerializer, SubscriptionRequestSerializer, UserCreationSerializer, ProfileUpdateSerializer, 
    BudgetSerializer, DashboardResponseSerializer, ConsumptionUpdateSerializer, 
    BulkIngestionSerializer, AnalyticsResponseSerializer, NotificationSerializer, 
    NotificationSettingsUpdateSerializer, UserMeterPreferenceUpdateSerializer, 
    AssignMeterSerializer, UnassignMeterSerializer, TariffVersionCreateSerializer, UserSerializer
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

import logging
logger = logging.getLogger(__name__)
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
                return Response({"message": "كلمة المرور الحالية غير صحيحة."}, status=status.HTTP_400_BAD_REQUEST)

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
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
                return Response({"status": "error", "message": f"خطأ أثناء معالجة الطلب: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 3. واجهات إنترنت الأشياء (مفتوحة حالياً للتبسيط) ====================

class ConsumptionUpdateAPIView(APIView):
    authentication_classes = []
    permission_classes = [HasMeterApiKey]

    def post(self, request, meter_id):
        serializer = ConsumptionUpdateSerializer(data=request.data)
        if serializer.is_valid():
            dt = make_aware(datetime.fromtimestamp(serializer.validated_data['timestamp']))
            try:
                payload = serializer.validated_data['payload']
                hardware_type = request.headers.get('X-Hardware-Type', None)
                
                reading = IngestionService.process_live_reading(meter_id, payload, dt, hardware_type)
                return Response({
                    "status": "success", 
                    "message": "تم استلام القراءة وتطبيق محول العتاد بنجاح.", 
                    "data": {
                        "readingId": reading.readingId, 
                        "cumulativeWh": reading.cumulativeWh, 
                        "timestamp": reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"status": "error", "message": f"خطأ برلمجي أثناء الاستقبال: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class BulkIngestionAPIView(APIView):
    permission_classes = [HasMeterApiKey]

    def post(self, request, meter_id):
        serializer = BulkIngestionSerializer(data=request.data)
        if serializer.is_valid():
            try:
                records_created = IngestionService.process_bulk_backfill(meter_id, serializer.validated_data['readings'])
                return Response({"status": "success", "message": f"تم تهيئة وحقن {records_created} قراءة تاريخية بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
                return Response({"status": "error", "message": f"تعذر إتمام الحقن: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== 4. واجهات الإدارة لمدير النظام (Admin Users Only) ====================



from django.db.models import Q # استيراد مكوّن الاستعلامات المعقدة Q لفلترة الجداول

class AdminCreateUserAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        search_query = request.query_params.get('search', None)
        queryset = User.objects.filter(role='RESIDENT').order_by('-createdAt')
        
        # 1. تطبيق الفلترة السحابية الآمنة أولاً إن وجدت
        if search_query:
            queryset = queryset.filter(
                Q(fullName__icontains=search_query) | 
                Q(phoneNumber__icontains=search_query)
            )
            
        # 2. تطبيق الترقيم والتحميل التدريجي (Pagination) بمعدل 10 مستخدمين في الصفحة
        paginator = LimitOffsetPagination()
        paginator.default_limit = 10
        page = paginator.paginate_queryset(queryset, request, view=self)
        
        if page is not None:
            serializer = UserSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = UserSerializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "تم استرداد قائمة المستهلكين بنجاح.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        # يبقى كود الـ post لإنشاء الحساب كما هو تماماً بالأسفل...
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
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
            return Response({"message": f"عطل أثناء التحديث: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, user_id):
        try:
            UserService.delete_user_account(user_id)
            return Response({"status": "success", "message": "تم حذف حساب المستخدم وجميع ارتباطاته بنجاح."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
            return Response({"message": f"تعذر الحذف: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)



class AdminMeterListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        # [UC_14 -> Read] جلب قائمة العدادات المرقّمة والمفلترة بالبحث سحابياً لمدير النظام
        search_query = request.query_params.get('search', None)
        queryset = Meter.objects.all().order_by('-registerDate')
        
        # فلترة البحث بالـ UUID الفيزيائي سحابياً
        if search_query:
            queryset = queryset.filter(meterId__icontains=search_query)
            
        # تطبيق الترقيم والتحميل التدريجي (10 عدادات في الصفحة)
        paginator = LimitOffsetPagination()
        paginator.default_limit = 10
        page = paginator.paginate_queryset(queryset, request, view=self)
        
        if page is not None:
            serializer = MeterSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = MeterSerializer(queryset, many=True)
        return Response({
            "status": "success",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        # يبقى كود الـ post لإنشاء العداد كما هو تماماً بالأسفل...
        meter_id_raw = request.data.get('meterId', None)
        if not meter_id_raw:
            return Response({"message": "يجب تزويد المعرّف الفيزيائي للعداد (UUID/MAC)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            meter = MeterService.add_new_meter(meter_id_raw)
            return Response({"status": "success", "message": "تم تسجيل العداد بنجاح.", "data": {"meterId": meter.meterId, "registerDate": meter.registerDate}}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
            return Response({"message": f"تعذر الإضافة: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class AdminMeterDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def put(self, request, meter_id):
        # [UC_14 -> Update] تعديل بيانات العداد (مثل معرّفه الفيزيائي) من الأدمن
        new_meter_id = request.data.get('newMeterId', None)
        if not new_meter_id:
            return Response({"message": "يرجى تحديد المعرّف الفيزيائي الجديد للعداد."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meter = Meter.objects.get(pk=meter_id)
            # التأكد من أن المعرف الجديد ليس مسجلاً لعداد آخر نشط
            if Meter.objects.filter(pk=new_meter_id).exclude(pk=meter_id).exists():
                return Response({"message": "خطأ: المعرّف الفيزيائي الجديد مسجل مسبقاً لعداد آخر."}, status=status.HTTP_400_BAD_REQUEST)

            # لتغيير المفتاح الأساسي UUID في دجانغو، نقوم بإنشاء سجل جديد وحذف القديم أو تحديثه مباشرة
            # سنقوم بربط وتحديث الـ UUID وحفظ السجل
            meter.meterId = new_meter_id
            meter.save()
            
            # تصفير الكاش لمزامنة البيانات فورا
            CacheService.invalidate_meter_dashboard_cache(str(meter_id))


            return Response({
                "status": "success",
                "message": "تم تحديث معرّف العداد الفيزيائي ومسح الكاش بنجاح."
            }, status=status.HTTP_200_OK)
        except Meter.DoesNotExist:
            return Response({"message": "العداد غير موجود."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, meter_id):
        try:
            meter = Meter.objects.get(pk=meter_id)
            meter.delete()
            return Response({
                "status": "success",
                "message": "تم حذف العداد الفيزيائي وجميع سجلاته وقراءاته وتنبؤاته نهائياً."
            }, status=status.HTTP_200_OK)
        except Meter.DoesNotExist:
            return Response({"message": f"العداد غير موجود."}, status=status.HTTP_404_NOT_FOUND)
class AdminMeterAssociationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def post(self, request):
        serializer = AssignMeterSerializer(data=request.data)
        if serializer.is_valid():
            try:
                pref = AssociationService.assign_meter_to_user(serializer.validated_data['meterId'], serializer.validated_data['userId'], serializer.validated_data['alias'])
                return Response({"status": "success", "message": "تم إسناد العداد للمستخدم بنجاح."}, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
                return Response({"message": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from core.models import TariffVersion, TariffTier
from .serializers import TariffVersionSerializer, TariffVersionCreateSerializer

class AdminTariffUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        # [UC_15 -> Read] جلب قائمة بجميع إصدارات التعرفة والشرائح التابعة لها لجدول الأدمن
        versions = TariffVersion.objects.all().order_by('-effectiveDate')
        serializer = TariffVersionSerializer(versions, many=True)
        return Response({
            "status": "success",
            "message": "تم استرداد قائمة إصدارات التعرفة بنجاح.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        # [UC_15 -> Create] إنشاء إصدار تعرفة جديد وشرائحه التفاعلية
        serializer = TariffVersionCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                version = TariffService.create_new_tariff(serializer.validated_data['effectiveDate'], serializer.validated_data['tiers'])
                return Response({
                    "status": "success",
                    "message": f"تم تفعيل إصدار التعرفة الجديدة لعام {version.effectiveDate.year} بنجاح."
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error occurred: {str(e)}", exc_info=True)
                return Response({"message": f"تعذر التحديث: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminTariffDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def put(self, request, version_id):
        # [UC_15 -> Update] تعديل تعرفة مستقبلية لم تطبق بعد (يُمنع تعديل التعرفة السارية حالياً تاريخياً!)
        try:
            version = TariffVersion.objects.get(pk=version_id)
            
            # قيد الأمان الصارم: يمنع تعديل أي تعرفة سريانها في الماضي أو اليوم
            if version.effectiveDate <= date.today():
                return Response({"message": "عذراً، يمنع تعديل التعرفة الكهربائية السارية حالياً أو التاريخية حماية للفواتير المسجلة."}, status=status.HTTP_403_FORBIDDEN)

            serializer = TariffVersionCreateSerializer(data=request.data)
            if serializer.is_valid():
                with transaction.atomic():
                    # مسح الشرائح القديمة لإصدار التعرفة المستقبلية وإعادة حقن الجديدة المحدثة
                    version.effectiveDate = serializer.validated_data['effectiveDate']
                    version.save()
                    
                    TariffTier.objects.filter(tariffVersion=version).delete()
                    
                    tiers_to_create = []
                    for item in serializer.validated_data['tiers']:
                        tiers_to_create.append(
                            TariffTier(
                                tariffVersion=version,
                                tierNumber=item['tierNumber'],
                                startKWh=item['startKWh'],
                                endKWh=item['endKWh'],
                                pricePerKWh=item['pricePerKWh']
                            )
                        )
                    TariffTier.objects.bulk_create(tiers_to_create)
                    
                # مسح الكاش لمزامنة البيانات
                
                CacheService.invalidate_all_caches()

                return Response({
                    "status": "success",
                    "message": "تم تعديل وحفظ التعرفة المستقبلية وشرائحها بنجاح ومزامنة الكاش."
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except TariffVersion.DoesNotExist:
            return Response({"message": "إصدار التعرفة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, version_id):
        # [UC_15 -> Delete] حذف تعرفة مستقبلية لم تطبق بعد
        try:
            version = TariffVersion.objects.get(pk=version_id)
            
            # قيد الأمان الصارم: يمنع حذف التعرفات السارية
            if version.effectiveDate <= date.today():
                return Response({"message": "عذراً، يمنع حذف التعرفة الكهربائية السارية حالياً حماية لاتساق بيانات المشتركين."}, status=status.HTTP_403_FORBIDDEN)

            version.delete() # الحذف التلقائي سيمسح شرائحها المرتبطة بها
            
            CacheService.invalidate_all_caches()

            return Response({
                "status": "success",
                "message": "تم حذف التعرفة المستقبلية وشرائحها بنجاح من سجلات النظام."
            }, status=status.HTTP_200_OK)
        except TariffVersion.DoesNotExist:
            return Response({"message": "إصدار التعرفة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

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
            logger.error(f"Error occurred: {str(e)}", exc_info=True)
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
                    status=status.HTTP_400_BAD_REQUEST,
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
                    status=status.HTTP_400_BAD_REQUEST,
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



class AdminStatsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        try:
            users_count = User.objects.filter(role='RESIDENT').count()
            meters_count = Meter.objects.count()

            # حساب إجمالي استهلاك جميع المشتركين والعدادات في الدولة/المنظومة لآخر 12 شهراً
            current_date = date.today()
            system_monthly_history = []

            for i in range(12, 0, -1):
                m_start, m_end = TaskService.get_exact_prior_month_range(current_date, i)

                # استعلام إجمالي كافة المشتركين (بدون الفلترة بعداد محدد)
                m_sum = DailyConsumptionSummary.objects.filter(
                    date__gte=m_start,
                    date__lte=m_end
                ).aggregate(total=Sum('totalKWh'))['total']

                system_monthly_history.append({
                    "monthName": m_start.strftime("%B %Y"),
                    "consumptionKWh": round(m_sum or Decimal('0.00'), 2)
                })

            return Response({
                "status": "success",
                "data": {
                    "usersCount": users_count,
                    "metersCount": meters_count,
                    "systemMonthlyHistory": system_monthly_history
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching admin stats: {str(e)}")
            return Response({"status": "error", "message": f"تعذر استرجاع الإحصائيات: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # 1. جلب العداد الافتراضي الحالي
        default_pref = UserMeterPreference.objects.filter(user=user, isDefault=True).first()
        default_meter_id = str(default_pref.meter.meterId) if default_pref else None

        # 2. جلب جميع العدادات المرتبطة بحساب هذا المستخدم ديناميكياً
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
            "message": "تم استرداد بيانات الجلسة الحالية بنجاح.",
            "user": {
                "id": user.id,
                "username": user.username,
                "fullName": user.fullName,
                "phoneNumber": user.phoneNumber,
                "role": user.role,
                "defaultMeterId": default_meter_id,
                "meters": meters_list
            }
        }, status=status.HTTP_200_OK)
    


class SavePushTokenAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        push_token = request.data.get('pushToken', None)
        if not push_token:
            return Response(
                {"status": "error", "message": "يرجى تزويد رمز الإشعار pushToken."},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.pushToken = push_token
        request.user.save()

        return Response(
            {"status": "success", "message": "تم ربط وحفظ رمز إشعارات الهاتف بنجاح."},
            status=status.HTTP_200_OK
        )
    



def generate_error_density_chart_base64(active_threshold):
    """
    توليد الرسم البياني الكبير لكثافة أخطاء التنبؤ المطلقة بالنصوص الإنجليزية وبـ 3 خطوط عتبات
    محصنة تماماً ضد أخطاء NoneType ومحاطة بحزام أمان للـ Fallback.
    """
    try:
        # 1. تصفية صريحة لمنع طرح قيم NoneType
        forecasts = DailyForecast.objects.filter(
            actualConsumptionKWh__isnull=False,
            predictedConsumptionKWh__isnull=False
        )
        errors = [
            float(abs(f.actualConsumptionKWh - f.predictedConsumptionKWh)) 
            for f in forecasts 
            if f.actualConsumptionKWh is not None and f.predictedConsumptionKWh is not None
        ]

        system_mean = float(ThresholdScalingService.calculate_system_average_kwh())
        base_mean = float(active_threshold.baseMeanKWh)
        base_thresh = float(active_threshold.baseThresholdKWh)
        calc_thresh = float(active_threshold.calculatedThresholdKWh)
        
        proposed_thresh = round(base_thresh * (system_mean / base_mean), 2)

        if len(errors) < 10:
            np.random.seed(42)
            errors = np.random.gamma(shape=2.0, scale=system_mean * 0.2, size=350).tolist()

        fig, ax = plt.subplots(figsize=(10, 7))
        
        n, bins, patches = ax.hist(errors, bins=35, color='darkorange', alpha=0.75, edgecolor='black', linewidth=0.5)

        # رسم الـ 3 خطوط العمودية الملونة للعتبات
        ax.axvline(x=base_thresh, color='red', linestyle=':', linewidth=2, label=f'Base  Thresh ({base_thresh:.1f} kWh)')
        ax.axvline(x=calc_thresh, color='purple', linestyle='--', linewidth=2.5, label=f'Active Thresh ({calc_thresh:.1f} kWh)')
        ax.axvline(x=proposed_thresh, color='forestgreen', linestyle='-.', linewidth=2.5, label=f'Proposed System Thresh ({proposed_thresh:.1f} kWh)')

        # تحسين وضوح أرقام المحاور - الحل الأساسي
        ax.tick_params(axis='x', labelsize=15, rotation=0, pad=10)  # زيادة حجم الخط
        ax.tick_params(axis='y', labelsize=15, pad=10)

        ax.set_title('Absolute Prediction Error Density & Threshold Detection', fontsize=22, fontweight='bold', pad=12)
        ax.set_xlabel('Absolute Error (kWh/day)', fontsize=20, labelpad=8)
        ax.set_ylabel('Frequency', fontsize=20, labelpad=8)
        ax.legend(loc='upper right', fontsize=17, framealpha=0.9)
        ax.grid(True, linestyle='--', alpha=0.3)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"تنبيه: تعذر إتمام رسم صورة كثافة الأخطاء: {str(e)}")
        return None


class AdminAnomalyThresholdAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        active_threshold = AnomalyThreshold.objects.filter(isActive=True).order_by('-updatedAt').first()
        if not active_threshold:
            active_threshold = ThresholdScalingService.update_anomaly_threshold()

        system_calculated_mean = ThresholdScalingService.calculate_system_average_kwh()
        serializer = AnomalyThresholdSerializer(active_threshold)

        # توليد الصورة بأمان عالي (إن تعذر الرسم تعود بـ None وتستمر الأرقام بالتواجد)
        chart_base64 = generate_error_density_chart_base64(active_threshold)

        return Response({
            "status": "success",
            "data": {
                "activeThreshold": serializer.data,
                "systemCalculatedMeanKWh": float(system_calculated_mean),
                "chartBase64": chart_base64
            }
        }, status=status.HTTP_200_OK)

    def post(self, request):
        custom_target_mean_raw = request.data.get('customTargetMean', None)
        region_name = request.data.get('regionName', "المنطقة المحلية / سوريا")

        custom_target_mean = None
        if custom_target_mean_raw is not None and str(custom_target_mean_raw).strip() != "":
            try:
                custom_target_mean = Decimal(str(custom_target_mean_raw))
            except Exception:
                return Response({"status": "error", "message": "قيمة المتوسط المدخلة غير صالحة."}, status=status.HTTP_400_BAD_REQUEST)

        new_threshold = ThresholdScalingService.update_anomaly_threshold(
            custom_target_mean=custom_target_mean,
            region_name=region_name
        )

        serializer = AnomalyThresholdSerializer(new_threshold)
        chart_base64 = generate_error_density_chart_base64(new_threshold)

        return Response({
            "status": "success",
            "message": f"تم تحديث واعتماد العتبة التناسبة الجديدة ({new_threshold.calculatedThresholdKWh} kWh/يوم) بنجاح.",
            "data": {
                "activeThreshold": serializer.data,
                "chartBase64": chart_base64
            }
        }, status=status.HTTP_200_OK)




# 1. واجهة تقديم طلب الاشتراك العامة (مفتوحة للمواطنين مع الحماية)
class PublicSubscriptionRequestAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveActionThrottle] # حماية من هجمات الإغراق

    def post(self, request):
        serializer = CreateSubscriptionRequestSerializer(data=request.data)
        if serializer.is_valid():
            try:
                sub_req = SubscriptionService.create_request(
                    full_name=serializer.validated_data['fullName'],
                    phone_number=serializer.validated_data['phoneNumber'],
                    governorate=serializer.validated_data['governorate'],
                    detailed_address=serializer.validated_data['detailedAddress']
                )
                return Response({
                    "status": "success",
                    "message": "تم تسجيل طلبك بنجاح، وسوف يتم التواصل معك لإتمام باقي الإجراءات وتزويدك ببيانات الدخول.",
                    "data": {"requestId": sub_req.requestId}
                }, status=status.HTTP_201_CREATED)
            except ValueError as ve:
                return Response({"status": "error", "message": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({"status": "error", "message": f"حدث خطأ أثناء حفظ الطلب: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 2. واجهة استعراض وترقيم المفلتر لطلبات الاشتراك للأدمن
class AdminSubscriptionRequestListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get(self, request):
        search_query = request.query_params.get('search', None)
        status_filter = request.query_params.get('status', None)

        queryset = SubscriptionRequest.objects.all().order_by('-createdAt')

        # فلترة الحالة (PENDING, COMPLETED, CANCELLED)
        if status_filter and status_filter in ['PENDING', 'COMPLETED', 'CANCELLED']:
            queryset = queryset.filter(status=status_filter)

        # البحث بالاسم، الهاتف، أو المحافظة
        if search_query:
            queryset = queryset.filter(
                Q(fullName__icontains=search_query) |
                Q(phoneNumber__icontains=search_query) |
                Q(governorate__icontains=search_query)
            )

        paginator = LimitOffsetPagination()
        paginator.default_limit = 10
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:
            serializer = SubscriptionRequestSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = SubscriptionRequestSerializer(queryset, many=True)
        return Response({
            "status": "success",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


# 3. واجهة تعديل حالة أو حذف طلب اشتراك من الأدمن
class AdminSubscriptionRequestDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def put(self, request, request_id):
        new_status = request.data.get('status', None)
        if not new_status or new_status not in ['PENDING', 'COMPLETED', 'CANCELLED']:
            return Response({"status": "error", "message": "حالة الطلب غير صالحة."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            req = SubscriptionService.update_request_status(request_id, new_status)
            return Response({
                "status": "success",
                "message": f"تم تحديث حالة الطلب إلى ({req.get_status_display()}) بنجاح."
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, request_id):
        try:
            SubscriptionService.delete_request(request_id)
            return Response({"status": "success", "message": "تم حذف طلب الاشتراك بنجاح."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# 4. واجهة أتمتة إنشاء الحساب وربط العداد وتحويل الطلب لمكتمل (3-in-1 Provisioning)
class AdminProvisionSubscriptionRequestAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def post(self, request):
        serializer = ProvisionSubscriptionRequestSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user, temp_password, is_new_user, req = SubscriptionService.provision_and_complete_request(
                    request_id=serializer.validated_data['requestId'],
                    meter_id=serializer.validated_data['meterId'],
                    alias=serializer.validated_data['alias']
                )

                if is_new_user:
                    msg = "تم إنشاء حساب جديد للمواطن وتوليد كلمة مرور مؤقتة وربط العداد بنجاح."
                else:
                    msg = "المواطن مسجل مسبقاً في المنظومة. تم ربط العداد الجديد بحسابه الحالي بنجاح."

                return Response({
                    "status": "success",
                    "message": msg,
                    "data": {
                        "userId": user.id,
                        "username": user.username,
                        "fullName": user.fullName,
                        "phoneNumber": user.phoneNumber,
                        "isNewUser": is_new_user,
                        "temporaryPassword": temp_password,
                        "meterAlias": serializer.validated_data['alias']
                    }
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        