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
from .models import Meter, Notification, NotificationSettings, User

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
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)\
        


# أضف هذه الأكواد في نهاية ملف core/views.py لإغلاق وبرمجة كامل الـ APIs المتبقية للنظام

from core.models import UserMeterPreference, TariffVersion, TariffTier
from .serializers import (
    UserMeterPreferenceUpdateSerializer, 
    AssignMeterSerializer, 
    UnassignMeterSerializer, 
    TariffVersionCreateSerializer
)

# ==================== أولاً: واجهات المشترك (Resident User) ====================

# 1. واجهة إدارة وتخصيص العدادات الخاصة بالمشترك (UC_3)
class UserMeterPreferenceAPIView(APIView):
    def put(self, request, preference_id):
        try:
            pref = UserMeterPreference.objects.get(pk=preference_id)
        except UserMeterPreference.DoesNotExist:
            return Response({"message": "سجل ارتباط العداد غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserMeterPreferenceUpdateSerializer(pref, data=request.data, partial=True)
        if serializer.is_valid():
            # إذا حدد المستخدم هذا العداد كافتراضي، نقوم بإلغاء الافتراضي عن العدادات الأخرى له
            if serializer.validated_data.get('isDefault', False):
                UserMeterPreference.objects.filter(user=pref.user).update(isDefault=False)
                
            serializer.save()
            return Response({
                "status": "success",
                "message": "تم تحديث تفضيلات العداد بنجاح.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== ثانياً: واجهات الإدارة لمدير النظام (Admin) ====================

# 2. واجهة تعديل وحذف حساب مستخدم من قبل الأدمن (UC_13)
class AdminUserDetailAPIView(APIView):
    def put(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id, role='RESIDENT')
        except User.DoesNotExist:
            return Response({"message": "المستخدم غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # تعديل الاسم الكامل أو الهاتف
        fullName = request.data.get('fullName', user.fullName)
        phoneNumber = request.data.get('phoneNumber', user.phoneNumber)
        
        # التأكد من عدم تكرار الهاتف
        if User.objects.filter(phoneNumber=phoneNumber).exclude(pk=user_id).exists():
            return Response({"message": "رقم الهاتف هذا مسجل مسبقاً لمستخدم آخر."}, status=status.HTTP_400_BAD_REQUEST)

        user.fullName = fullName
        user.phoneNumber = phoneNumber
        user.save()
        
        return Response({
            "status": "success",
            "message": "تم تحديث بيانات حساب المستخدم بنجاح."
        }, status=status.HTTP_200_OK)

    def delete(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id, role='RESIDENT')
            user.delete() # الحذف المتتالي لـ Django سيقوم بمسح تفضيلاته وتأمين الحذف النظيف
            return Response({
                "status": "success",
                "message": "تم حذف حساب المستخدم وجميع ارتباطاته بنجاح من النظام."
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"message": "المستخدم غير موجود."}, status=status.HTTP_404_NOT_FOUND)


# 3. واجهة إضافة وإدارة وحذف العدادات الفيزيائية من قبل الأدمن (UC_14)
class AdminMeterListCreateAPIView(APIView):
    def post(self, request):
        # إضافة عداد فيزيائي جديد للنظام
        meter_id_raw = request.data.get('meterId', None)
        if not meter_id_raw:
            return Response({"message": "يجب تزويد المعرّف الفيزيائي للعداد (UUID/MAC)."}, status=status.HTTP_400_BAD_REQUEST)
        
        if Meter.objects.filter(pk=meter_id_raw).exists():
            return Response({"message": "خطأ: هذا العداد مسجل مسبقاً كجهاز نشط."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meter = Meter.objects.create(meterId=meter_id_raw)
            return Response({
                "status": "success",
                "message": "تم تسجيل العداد الفيزيائي الجديد بنجاح في النظام.",
                "data": {"meterId": meter.meterId, "registerDate": meter.registerDate}
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"message": f"تعذر الإضافة: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminMeterDetailAPIView(APIView):
    def delete(self, request, meter_id):
        # حذف عداد بالكامل ومسح قراءاته (تركيب وجودي)
        try:
            meter = Meter.objects.get(pk=meter_id)
            meter.delete()
            return Response({
                "status": "success",
                "message": "تم حذف العداد الفيزيائي وجميع سجلاته وقراءاته وتنبؤاته نهائياً من النظام."
            }, status=status.HTTP_200_OK)
        except Meter.DoesNotExist:
            return Response({"message": "العداد غير موجود."}, status=status.HTTP_404_NOT_FOUND)


# 4. واجهة إسناد وإلغاء إسناد العدادات للمستخدمين (UC_16)
class AdminMeterAssociationAPIView(APIView):
    def post(self, request):
        # إسناد العداد لمستخدم
        serializer = AssignMeterSerializer(data=request.data)
        if serializer.is_valid():
            u_id = serializer.validated_data['userId']
            m_id = serializer.validated_data['meterId']
            alias = serializer.validated_data['alias']
            
            try:
                user = User.objects.get(pk=u_id, role='RESIDENT')
                meter = Meter.objects.get(pk=m_id)
            except (User.DoesNotExist, Meter.DoesNotExist):
                return Response({"message": "المستخدم أو العداد غير موجود في سجلات النظام."}, status=status.HTTP_404_NOT_FOUND)

            # منع تكرار الإسناد
            pref, created = UserMeterPreference.objects.get_or_create(
                user=user,
                meter=meter,
                defaults={'alias': alias, 'isDefault': False}
            )
            
            if not created:
                return Response({"message": "هذا العداد مسند بالفعل لهذا المستخدم مسبقاً."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                "status": "success",
                "message": "تم إسناد العداد للمستخدم المختار بنجاح في النظام."
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminMeterUnassignmentAPIView(APIView):
    def post(self, request):
        # إلغاء إسناد عداد عن مستخدم
        serializer = UnassignMeterSerializer(data=request.data)
        if serializer.is_valid():
            u_id = serializer.validated_data['userId']
            m_id = serializer.validated_data['meterId']
            
            try:
                pref = UserMeterPreference.objects.get(user_id=u_id, meter_id=m_id)
                pref.delete()
                return Response({
                    "status": "success",
                    "message": "تم إلغاء إسناد العداد عن حساب المستخدم بنجاح."
                }, status=status.HTTP_200_OK)
            except UserMeterPreference.DoesNotExist:
                return Response({"message": "سجل الارتباط غير موجود مسبقاً."}, status=status.HTTP_404_NOT_FOUND)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 5. واجهة تحديث وإصدار تسعيرة الشرائح الحكومية ديناميكياً من الويب (UC_15)
class AdminTariffUpdateAPIView(APIView):
    def post(self, request):
        serializer = TariffVersionCreateSerializer(data=request.data)
        if serializer.is_valid():
            eff_date = serializer.validated_data['effectiveDate']
            tiers_data = serializer.validated_data['tiers']
            
            # تعطيل جميع إصدارات التعرفة السابقة
            TariffVersion.objects.all().update(isActive=False)
            
            # إنشاء إصدار تعرفة نشط وجديد
            new_version = TariffVersion.objects.create(
                effectiveDate=eff_date,
                isActive=True
            )
            
            # إنشاء وحفظ الشرائح التابعة للإصدار الجديد
            tiers_to_create = []
            for item in tiers_data:
                tiers_to_create.append(
                    TariffTier(
                        tariffVersion=new_version,
                        tierNumber=item['tierNumber'],
                        startKWh=item['startKWh'],
                        endKWh=item['endKWh'],
                        pricePerKWh=item['pricePerKWh']
                    )
                )
            
            TariffTier.objects.bulk_create(tiers_to_create)
            
            return Response({
                "status": "success",
                "message": f"تم إصدار وتفعيل نسخة التعرفة الجديدة لعام {eff_date.year} بنجاح مع {len(tiers_to_create)} شرائح ديناميكية."
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)