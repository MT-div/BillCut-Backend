from django.urls import path
from .views import (
    BulkIngestionAPIView,
    ConsumptionUpdateAPIView,
    LoginAPIView, 
    AdminCreateUserAPIView,
    MeterAnalyticsAPIView,
    MeterDashboardAPIView,
    NotificationLogAPIView,
    NotificationSettingsAPIView, 
    ProfileUpdateAPIView, 
    SetBudgetAPIView
)


urlpatterns = [
    # الروابط الجديدة المضافة للتحليلات والإشعارات والتفضيلات
    path('meter/<uuid:meter_id>/analytics/', MeterAnalyticsAPIView.as_view(), name='api_meter_analytics'),
    path('meter/<uuid:meter_id>/notifications/', NotificationLogAPIView.as_view(), name='api_notifications_log'),
    path('user/<int:user_id>/notification_settings/', NotificationSettingsAPIView.as_view(), name='api_notification_settings'),
    
    # الروابط السابقة تبقيها كما هي تماماً تحتها...
    path('meter/<uuid:meter_id>/dashboard/', MeterDashboardAPIView.as_view(), name='api_meter_dashboard'),
    path('meter/<uuid:meter_id>/consumption/update/', ConsumptionUpdateAPIView.as_view(), name='api_consumption_update'),
    path('meter/<uuid:meter_id>/consumption/bulk_backfill/', BulkIngestionAPIView.as_view(), name='api_bulk_backfill'),
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('admin/users/create/', AdminCreateUserAPIView.as_view(), name='api_admin_create_user'),
    path('user/profile/update/', ProfileUpdateAPIView.as_view(), name='api_profile_update'),
    path('meter/<uuid:meter_id>/budget/set/', SetBudgetAPIView.as_view(), name='api_set_budget'),
]