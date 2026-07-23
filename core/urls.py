from django.urls import path
from .views import (
    BulkIngestionAPIView,
    ConsumptionUpdateAPIView,
    LoginAPIView, 
    AdminCreateUserAPIView,
    MeterDashboardAPIView, 
    ProfileUpdateAPIView, 
    SetBudgetAPIView
)

urlpatterns = [
    # روابط الحسابات والمستخدمين
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('admin/users/create/', AdminCreateUserAPIView.as_view(), name='api_admin_create_user'),
    path('user/profile/update/', ProfileUpdateAPIView.as_view(), name='api_profile_update'),
    path('meter/<uuid:meter_id>/budget/set/', SetBudgetAPIView.as_view(), name='api_set_budget'),
    
    # روابط إنترنت الأشياء والـ Dashboard للعداد الذكي
    path('meter/<uuid:meter_id>/dashboard/', MeterDashboardAPIView.as_view(), name='api_meter_dashboard'),
    path('meter/<uuid:meter_id>/consumption/update/', ConsumptionUpdateAPIView.as_view(), name='api_consumption_update'),
    path('meter/<uuid:meter_id>/consumption/bulk_backfill/', BulkIngestionAPIView.as_view(), name='api_bulk_backfill'),
]