from django.urls import path
from .views import (
    AdminMeterAssociationAPIView,
    AdminMeterDetailAPIView,
    AdminMeterListCreateAPIView,
    AdminMeterUnassignmentAPIView,
    AdminStatsAPIView,
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
    SetBudgetAPIView,
    UserMeterPreferenceAPIView,
    PasswordUpdateAPIView,
    PhoneUpdateAPIView
)
from rest_framework_simplejwt.views import TokenRefreshView



urlpatterns = [
    # 1. روابط التحقق والمستندات الشخصية للمستخدم والملف الشخصي
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
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
    
    # 4. روابط إدارة حسابات المستخدمين والـ CRUD لمدير النظام (Admin)
    path('admin/users/create/', AdminCreateUserAPIView.as_view(), name='api_admin_create_user'),
    path('admin/users/<int:user_id>/', AdminUserDetailAPIView.as_view(), name='api_admin_user_detail'),
    
    # 5. روابط إدارة العدادات والـ CRUD للأجهزة لمدير النظام (Admin)
    path('admin/meters/create/', AdminMeterListCreateAPIView.as_view(), name='api_admin_meter_create'),
    path('admin/meters/<uuid:meter_id>/', AdminMeterDetailAPIView.as_view(), name='api_admin_meter_detail'),
    
    # 6. روابط إسناد وحوكمة العدادات لمدير النظام (Admin)
    path('admin/meters/assign/', AdminMeterAssociationAPIView.as_view(), name='api_admin_meter_assign'),
    path('admin/meters/unassign/', AdminMeterUnassignmentAPIView.as_view(), name='api_admin_meter_unassign'),
    
    # 7. روابط إدارة وتحديث وإصدار التعرفة الكهربائية لمدير النظام (Admin)
    path('admin/tariff/update/', AdminTariffUpdateAPIView.as_view(), name='api_admin_tariff_update'),
    path('admin/system/trigger_daily_tasks/<uuid:meter_id>/', AdminTriggerDailyTasksAPIView.as_view(), name='api_admin_trigger_tasks'),

    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('admin/stats/', AdminStatsAPIView.as_view(), name='api_admin_stats'),

]