from rest_framework import serializers
from .models import Notification, TariffTier, TariffVersion, User, Meter, UserMeterPreference, Budget, NotificationSettings

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
# 16. DTO الخاص باسترجاع وعرض بيانات العداد الفيزيائي للأدمن (UC_14)
class MeterSerializer(serializers.ModelSerializer):
    associatedUsers = serializers.SerializerMethodField() # حقل ديناميكي لجلب المشتركين المرتبطين بالجهاز

    class Meta:
        model = Meter
        fields = ['meterId', 'registerDate', 'associatedUsers']

    def get_associatedUsers(self, obj):
        # جلب جميع تفضيلات وارتباطات المشتركين المرتبطين بهذا العداد الفيزيائي وتمريرها
        prefs = UserMeterPreference.objects.filter(meter=obj)
        return [
            {
                "preferenceId": p.id,
                "userId": p.user.id,
                "fullName": p.user.fullName,
                "phoneNumber": p.user.phoneNumber,
                "alias": p.alias
            } for p in prefs
        ]
# 6. DTO الخاص بضبط وحفظ الميزانية المالية بالليرة السورية
class BudgetSerializer(serializers.Serializer):
    targetBudgetSYP = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False, min_value=1.0)






class DashboardResponseSerializer(serializers.Serializer):
    meterId = serializers.UUIDField()
    simulatedDate = serializers.DateField()
    cycleProgressDays = serializers.IntegerField()
    cycleRemainingDays = serializers.IntegerField()
    cycleStartDate = serializers.DateField()
    cycleEndDate = serializers.DateField()
    supportLimitKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    budgetLimitKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    cycleActualConsumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    accumulatedCostSYP = serializers.IntegerField()
    predictedBillSYP = serializers.IntegerField()
    predictedCycleConsumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    targetBudgetSYP = serializers.IntegerField() # الحقل المالي المفقود لإنهاء الـ NaN
    todayActualKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    todayPredictedKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    avgSubTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    avgBudgetTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)# 7. DTO الخاص باستقبال قراءة العداد بالواط اللحظي والتوقيت
class ConsumptionUpdateSerializer(serializers.Serializer):
    watts = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, min_value=0.0)
    timestamp = serializers.IntegerField() # نمرره كطابع زمني رقمي (Unix Timestamp) لمرونة المحاكاة والدارة

# 8. DTO الخاص بالحقن الجماعي التراكمي التاريخي للعداد (Bulk Ingestion)
class BulkIngestionItemSerializer(serializers.Serializer):
    timestamp = serializers.IntegerField()
    cumulativeWh = serializers.DecimalField(max_digits=15, decimal_places=2, coerce_to_string=False, min_value=0.0)

class BulkIngestionSerializer(serializers.Serializer):
    readings = serializers.ListField(
        child=BulkIngestionItemSerializer(),
        allow_empty=False
    )



class MonthlyHistoryItemSerializer(serializers.Serializer):
    monthName = serializers.CharField()
    consumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

class CycleForecastSerializer(serializers.Serializer):
    predictedMonth1KWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    predictedMonth2KWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    expectedBillSYP = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)

class DailyHistoryItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    actualKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    predictedKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    isAnomalous = serializers.BooleanField()
    deviationKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

class AnalyticsResponseSerializer(serializers.Serializer):
    meterId = serializers.UUIDField()
    monthlyHistory = serializers.ListField(child=MonthlyHistoryItemSerializer())
    currentCycleForecast = CycleForecastSerializer()
    dailyHistory = serializers.ListField(child=DailyHistoryItemSerializer())

# 10. DTO الخاص باسترجاع وعرض قائمة الإشعارات لمركز التنبيهات

class NotificationSerializer(serializers.ModelSerializer):
    meterAlias = serializers.SerializerMethodField() # الحقل التفضيل الديناميكي الجديد

    class Meta:
        model = Notification
        fields = ['notificationId', 'title', 'message', 'type', 'isRead', 'timestamp', 'meterAlias']

    def get_meterAlias(self, obj):
        # قراءة المستخدم الموثق بـ Token الطلب وجلب الاسم المستعار المخصص منه للعداد
        request = self.context.get('request')
        if request and request.user:
            pref = UserMeterPreference.objects.filter(user=request.user, meter=obj.meter).first()
            return pref.alias if pref else "عداد غير معروف"
        return "عداد غير معروف"
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
    startKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, min_value=0.0)
    endKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, required=False, allow_null=True)
    pricePerKWh = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, min_value=0.0)

class TariffVersionCreateSerializer(serializers.Serializer):
    effectiveDate = serializers.DateField(required=True)
    tiers = serializers.ListField(child=TariffTierInputSerializer(), allow_empty=False)



class PhoneUpdateSerializer(serializers.Serializer):
    newPhone = serializers.CharField(max_length=20)
    currentPassword = serializers.CharField(write_only=True)
 
    def validate_newPhone(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("رقم الهاتف مطلوب.")
        # مثال بسيط للتحقق من صيغة الرقم - عدّل النمط حسب صيغ الأرقام المدعومة محلياً
        # if not cleaned.replace("+", "").isdigit():
        #     raise serializers.ValidationError("صيغة رقم الهاتف غير صحيحة.")
        return cleaned
 
 
class PasswordUpdateSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(write_only=True)
    newPassword = serializers.CharField(write_only=True, min_length=8)
    confirmPassword = serializers.CharField(write_only=True)
 
 
class TariffTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffTier
        fields = ['tierId', 'tierNumber', 'startKWh', 'endKWh', 'pricePerKWh']

class TariffVersionSerializer(serializers.ModelSerializer):
    tiers = TariffTierSerializer(many=True, read_only=True) # جلب الشرائح التابعة للإصدار ديناميكياً

    class Meta:
        model = TariffVersion
        fields = ['versionId', 'effectiveDate', 'tiers']