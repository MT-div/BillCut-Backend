from rest_framework import serializers
from .models import User, Meter, UserMeterPreference, Budget, NotificationSettings

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

# أضف هذا الكود في نهاية ملف core/serializers.py تماماً لتوثيق الـ DTO الخاص بالـ Dashboard

class DashboardResponseSerializer(serializers.Serializer):
    meterId = serializers.UUIDField()
    simulatedDate = serializers.DateField()
    cycleProgressDays = serializers.IntegerField()
    cycleRemainingDays = serializers.IntegerField()
    cycleStartDate = serializers.DateField()
    cycleEndDate = serializers.DateField()
    cycleActualConsumptionKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    accumulatedCostSYP = serializers.DecimalField(max_digits=12, decimal_places=2)
    predictedBillSYP = serializers.DecimalField(max_digits=12, decimal_places=2)
    todayActualKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    todayPredictedKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    avgSubTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2)
    avgBudgetTargetKWh = serializers.DecimalField(max_digits=10, decimal_places=2)

# أضف هذا الأكواد في نهاية ملف core/serializers.py لتوثيق الـ DTOs الجدد لاستقبال الاستهلاك والحقن

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