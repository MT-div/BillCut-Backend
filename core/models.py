from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# 1. كلاس المستخدم المخصص الممتد من كلاس دجانغو الأساسي (Custom User Model)
class User(AbstractUser):
    fullName = models.CharField(max_length=255)
    phoneNumber = models.CharField(max_length=15, unique=True)
    role = models.CharField(max_length=20, choices=[('ADMIN', 'Admin'), ('RESIDENT', 'Resident')], default='RESIDENT')
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.fullName} ({self.role})"

# 2. كلاس تفضيلات الإشعارات المرتبط بالمستهلك علاقة 1:1 (Composition)
class NotificationSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_settings')
    budgetPushEnabled = models.BooleanField(default=True)
    tierPushEnabled = models.BooleanField(default=True)
    anomalyPushEnabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Settings for {self.user.username}"

# 3. كلاس العداد الذكي
class Meter(models.Model):
    meterId = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registerDate = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Meter ID: {self.meterId}"

# 4. كلاس التفضيلات والارتباط الوسيط (Many-to-Many Bridge Table)
class UserMeterPreference(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meter_preferences')
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='user_preferences')
    alias = models.CharField(max_length=100)
    isDefault = models.BooleanField(default=False)
    assignedDate = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'meter') # يمنع تكرار ربط نفس العداد للمستخدم نفسه

    def __str__(self):
        return f"{self.user.username} - {self.alias}"

# 5. كلاس الميزانية المرتبط بالعداد 1:1 (Composition)
class Budget(models.Model):
    meter = models.OneToOneField(Meter, on_delete=models.CASCADE, related_name='budget')
    targetBudgetSYP = models.DecimalField(max_digits=12, decimal_places=2)
    equivalentLimitKWh = models.DecimalField(max_digits=10, decimal_places=2)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Budget for {self.meter.meterId} - Limit: {self.equivalentLimitKWh} kWh"

# 6. كلاس قراءات الاستهلاك التراكمية (Composition)
class ConsumptionReading(models.Model):
    readingId = models.BigAutoField(primary_key=True)
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='readings')
    cumulativeWh = models.DecimalField(max_digits=15, decimal_places=2)
    timestamp = models.DateTimeField(default=timezone.now) # تعديل لمنع التجاوز القسري للتاريخ

    def __str__(self):
        return f"Reading {self.readingId} for Meter {self.meter.meterId}"

# 7. كلاس التنبؤ اليومي والشذوذ (Composition)
class DailyForecast(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='daily_forecasts')
    forecastDate = models.DateField()
    predictedConsumptionKWh = models.DecimalField(max_digits=10, decimal_places=2)
    actualConsumptionKWh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    isAnomalous = models.BooleanField(default=False)
    deviationAmountKWh = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('meter', 'forecastDate')

    def __str__(self):
        return f"Forecast on {self.forecastDate} - Anomaly: {self.isAnomalous}"

# 8. كلاس التنبؤ الشهري لدورة الفوترة (Composition)
class MonthlyForecast(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='monthly_forecasts')
    cycleStartDate = models.DateField()
    predictedMonth1KWh = models.DecimalField(max_digits=10, decimal_places=2)
    predictedMonth2KWh = models.DecimalField(max_digits=10, decimal_places=2)
    actualMonth1KWh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expectedBillSYP = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ('meter', 'cycleStartDate')

    def __str__(self):
        return f"Cycle starting {self.cycleStartDate} - Expected Bill: {self.expectedBillSYP} SYP"

# 9. كلاس أرشفة الإشعارات الداخلية (Composition)
class Notification(models.Model):
    notificationId = models.BigAutoField(primary_key=True)
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    type = models.CharField(max_length=30) # (ANOMALY, BUDGET_NOTICE, TIER_NOTICE)
    isRead = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now) # تعديل لمرونة الإشعارات

    def __str__(self):
        return f"Notification {self.notificationId}: {self.title}"

# 10. كلاس نسخة وإصدار التعرفة الحكومية

class TariffVersion(models.Model):
    versionId = models.BigAutoField(primary_key=True)
    effectiveDate = models.DateField() # الاعتماد الكلي على تاريخ السريان والنفاذ

    def __str__(self):
        return f"Tariff Version {self.versionId} (Effective: {self.effectiveDate})"
# 11. كلاس الشرائح الفردية التابعة لإصدار التعرفة (Composition)
class TariffTier(models.Model):
    tierId = models.BigAutoField(primary_key=True)
    tariffVersion = models.ForeignKey(TariffVersion, on_delete=models.CASCADE, related_name='tiers')
    tierNumber = models.IntegerField()
    startKWh = models.DecimalField(max_digits=10, decimal_places=2)
    endKWh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) # الشريحة الأخيرة تترك Null للتعبير عن "ما فوق"
    pricePerKWh = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('tariffVersion', 'tierNumber')

    def __str__(self):
        return f"Tier {self.tierNumber} in Version {self.tariffVersion.versionId} - Price: {self.pricePerKWh} SYP"