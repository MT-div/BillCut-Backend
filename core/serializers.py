from rest_framework import serializers
from .models import Notification, User, Meter, UserMeterPreference, Budget, NotificationSettings

# 1. DTO الخاص باسترجاع بيانات المستخدم الأساسية
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'fullName', 'phoneNumber', 'role', 'createdAt']

# 2. DTO الخاص بالتحقق من بيانات تسجيل الدخول
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)

# 3. DTO الخاص بإنشاء مستخدم جديد من قبل الأدمن
class UserCreationSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=255, required=True)
    phoneNumber = serializers.CharField(max_length=15, required=True)

    def validate_phoneNumber(self, value):
        if User.objects.filter(phoneNumber=value).exists():
            raise serializers.ValidationError("رقم الهاتف هذا مسجل مسبقاً لمستخدم آخر.")
        return value

# 4. DTO الخاص بتحديث بيانات الملف الشخصي وكلمة المرور
class ProfileUpdateSerializer(serializers.Serializer):
    newPhone = serializers.CharField(max_length=15, required=True)
    currentPassword = serializers.CharField(write_only=True, required=True)
    newPassword = serializers.CharField(write_only=True, required=False, allow_blank=True)
    confirmPassword = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, data):
        new_password = data.get('newPassword')
        confirm_password = data.get('confirmPassword')
        if new_password and new_password != confirm_password:
            raise serializers.ValidationError({"confirmPassword": "كلمتا المرور الجديدتان غير متطابقتين."})
        return data

# 5. DTO الخاص بإدارة وتخصيص تفضيلات العداد للمستخدم
class MeterPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMeterPreference
        fields = ['id', 'alias', 'isDefault', 'assignedDate']

# 6. DTO الخاص بضبط وحفظ الميزانية المالية بالليرة السورية
class BudgetSerializer(serializers.Serializer):
    targetBudgetSYP = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1.0)





class DashboardResponseSerializer(serializers.Serializer):
    meterId = serializers.UUIDField()
    simulatedDate = serializers.DateField()
    cycleProgressDays = serializers.IntegerField()
    cycleRemainingDays = serializers.IntegerField()
    cycleStartDate = serializers.DateField()
    cycleEndDate = serializers.DateField()
    supportLimitKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    budgetLimitKWh = serializers.DecimalField(max_digits=10, decimal_places=2) # الحقل الديناميكي الجديد المضاف
    cycleActualConsumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    accumulatedCostSYP = serializers.IntegerField()
    predictedBillSYP = serializers.IntegerField()
    predictedCycleConsumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    todayActualKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    todayPredictedKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    avgSubTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    avgBudgetTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
# 7. DTO الخاص باستقبال قراءة العداد بالواط اللحظي والتوقيت
class ConsumptionUpdateSerializer(serializers.Serializer):
    watts = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.0)
    timestamp = serializers.IntegerField() # نمرره كطابع زمني رقمي (Unix Timestamp) لمرونة المحاكاة والدارة

# 8. DTO الخاص بالحقن الجماعي التراكمي التاريخي للعداد (Bulk Ingestion)
class BulkIngestionItemSerializer(serializers.Serializer):
    timestamp = serializers.IntegerField()
    cumulativeWh = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0.0)

class BulkIngestionSerializer(serializers.Serializer):
    readings = serializers.ListField(
        child=BulkIngestionItemSerializer(),
        allow_empty=False
    )



class MonthlyHistoryItemSerializer(serializers.Serializer):
    monthName = serializers.CharField()
    consumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2)

class CycleForecastSerializer(serializers.Serializer):
    predictedMonth1KWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    predictedMonth2KWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    expectedBillSYP = serializers.DecimalField(max_digits=12, decimal_places=2)

class DailyHistoryItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    actualKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    predictedKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    isAnomalous = serializers.BooleanField()
    deviationKWh = serializers.DecimalField(max_digits=10, decimal_places=2)

class AnalyticsResponseSerializer(serializers.Serializer):
    meterId = serializers.UUIDField()
    monthlyHistory = serializers.ListField(child=MonthlyHistoryItemSerializer())
    currentCycleForecast = CycleForecastSerializer()
    dailyHistory = serializers.ListField(child=DailyHistoryItemSerializer())

# 10. DTO الخاص باسترجاع وعرض قائمة الإشعارات لمركز التنبيهات
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['notificationId', 'title', 'message', 'type', 'isRead', 'timestamp']

# 11. DTO الخاص بتحديث تفضيلات الإشعارات للمستهلك
class NotificationSettingsUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = ['budgetPushEnabled', 'tierPushEnabled', 'anomalyPushEnabled']

# 12. DTO لتحديث الاسم وتعيين العداد الافتراضي للمشترك (UC_3)
class UserMeterPreferenceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMeterPreference
        fields = ['alias', 'isDefault']
# 13. DTO لإسناد العداد لمستخدم مخصص من الأدمن (UC_16)
class AssignMeterSerializer(serializers.Serializer):
    userId = serializers.IntegerField(required=True)
    meterId = serializers.UUIDField(required=True)
    alias = serializers.CharField(max_length=100, required=True)

# 14. DTO لإلغاء إسناد العداد عن مستخدم (UC_16)
class UnassignMeterSerializer(serializers.Serializer):
    userId = serializers.IntegerField(required=True)
    meterId = serializers.UUIDField(required=True)

# 15. DTO لتحديث التعرفة وإصدار الشرائح ديناميكياً من الأدمن (UC_15)
class TariffTierInputSerializer(serializers.Serializer):
    tierNumber = serializers.IntegerField(min_value=1)
    startKWh = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.0)
    endKWh = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    pricePerKWh = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.0)

class TariffVersionCreateSerializer(serializers.Serializer):
    effectiveDate = serializers.DateField(required=True)
    tiers = serializers.ListField(child=TariffTierInputSerializer(), allow_empty=False)