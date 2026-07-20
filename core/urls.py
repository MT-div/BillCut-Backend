from django.urls import path
from .views import (
    LoginAPIView, 
    AdminCreateUserAPIView, 
    ProfileUpdateAPIView, 
    SetBudgetAPIView
)

urlpatterns = [
    # روابط التحقق والدخول والمستخدمين
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('admin/users/create/', AdminCreateUserAPIView.as_view(), name='api_admin_create_user'),
    path('user/profile/update/', ProfileUpdateAPIView.as_view(), name='api_profile_update'),
    
    # رابط إدارة الميزانية لعداد مخصص (يمرر معرّف العداد في الرابط)
    path('meter/<uuid:meter_id>/budget/set/', SetBudgetAPIView.as_view(), name='api_set_budget'),
]