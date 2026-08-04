from django.urls import path
from .views import (
    AdminAnomalyThresholdAPIView,
    AdminMeterAssociationAPIView,
    AdminMeterDetailAPIView,
    AdminMeterListCreateAPIView,
    AdminMeterUnassignmentAPIView,
    AdminStatsAPIView,
    AdminTariffDetailAPIView,
    AdminTariffUpdateAPIView,
    AdminTriggerDailyTasksAPIView,
    AdminUserDetailAPIView,
    BulkIngestionAPIView,
    ConsumptionUpdateAPIView,
    LoginAPIView, 
    AdminCreateUserAPIView,
    MeterAnalyticsAPIView,
    MeterDashboardAPIView,
    NotificationLogAPIView,
    NotificationSettingsAPIView, 
    ProfileUpdateAPIView,
    SavePushTokenAPIView, 
    SetBudgetAPIView,
    UserMeterPreferenceAPIView,
    PasswordUpdateAPIView,
    PhoneUpdateAPIView,
    CurrentUserAPIView
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # 1. روابط التحقق والمستندات الشخصية للمستخدم والملف الشخصي
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('auth/me/', CurrentUserAPIView.as_view(), name='api_auth_me'), # مسار الجلسة الحية
    path('user/profile/update/', ProfileUpdateAPIView.as_view(), name='api_profile_update'),
    path('user/<int:user_id>/notification_settings/', NotificationSettingsAPIView.as_view(), name='api_notification_settings'),
    path("user/phone/update/", PhoneUpdateAPIView.as_view(), name="phone-update"),
    path("user/password/update/", PasswordUpdateAPIView.as_view(), name="password-update"),
    
    # 2. روابط الـ Dashboard والتحليلات والعدادات الخاصة بالمشترك
    path('meter/<uuid:meter_id>/dashboard/', MeterDashboardAPIView.as_view(), name='api_meter_dashboard'),
    path('meter/<uuid:meter_id>/analytics/', MeterAnalyticsAPIView.as_view(), name='api_meter_analytics'),
    path('user/notifications/', NotificationLogAPIView.as_view(), name='api_notifications_log'),
    path('user/meter/preferences/<int:preference_id>/', UserMeterPreferenceAPIView.as_view(), name='api_user_meter_preference'),
    path('meter/<uuid:meter_id>/budget/set/', SetBudgetAPIView.as_view(), name='api_set_budget'),
    
    # 3. روابط إنترنت الأشياء واستقبال وحقن الاستهلاك للعداد الذكي
    path('meter/<uuid:meter_id>/consumption/update/', ConsumptionUpdateAPIView.as_view(), name='api_consumption_update'),
    path('meter/<uuid:meter_id>/consumption/bulk_backfill/', BulkIngestionAPIView.as_view(), name='api_bulk_backfill'),
    
    # 4. روابط إدارة حسابات المستخدمين لمدير النظام (Admin)
    path('admin/users/create/', AdminCreateUserAPIView.as_view(), name='api_admin_create_user'),
    path('admin/users/<int:user_id>/', AdminUserDetailAPIView.as_view(), name='api_admin_user_detail'),
    path('admin/stats/', AdminStatsAPIView.as_view(), name='api_admin_stats'),

    # 5. روابط إدارة العدادات والعتاد لمدير النظام (Admin)
    path('admin/meters/create/', AdminMeterListCreateAPIView.as_view(), name='api_admin_meter_create'),
    path('admin/meters/<uuid:meter_id>/', AdminMeterDetailAPIView.as_view(), name='api_admin_meter_detail'),
    
    # 6. روابط إسناد وحوكمة العدادات لمدير النظام (Admin)
    path('admin/meters/assign/', AdminMeterAssociationAPIView.as_view(), name='api_admin_meter_assign'),
    path('admin/meters/unassign/', AdminMeterUnassignmentAPIView.as_view(), name='api_admin_meter_unassign'),
    
    # 7. روابط إدارة وتحديث وإصدار التعرفة لمدير النظام (Admin)
    path('admin/tariff/update/', AdminTariffUpdateAPIView.as_view(), name='api_admin_tariff_update'),
    path('admin/tariff/detail/<int:version_id>/', AdminTariffDetailAPIView.as_view(), name='api_admin_tariff_detail'),
    path('admin/system/trigger_daily_tasks/<uuid:meter_id>/', AdminTriggerDailyTasksAPIView.as_view(), name='api_admin_trigger_tasks'),

    # 8. رابط تجديد صلاحية الـ JWT
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
  
    # 9. رابط حفظ الـ pushToken للمستخدم
    path('user/push_token/', SavePushTokenAPIView.as_view(), name='api_save_push_token'),

    
    path('admin/anomaly_threshold/', AdminAnomalyThresholdAPIView.as_view(), name='api_admin_anomaly_threshold'),

]