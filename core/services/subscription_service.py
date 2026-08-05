from django.db import transaction
from core.models import SubscriptionRequest, User
from core.services.user_service import UserService
from core.services.association_service import AssociationService

class SubscriptionService:

    @classmethod
    def create_request(cls, full_name: str, phone_number: str, governorate: str, detailed_address: str) -> SubscriptionRequest:
        """
        إنشاء طلب اشتراك جديد مع فحص قيد عدم تجاوز 2 طلب قيد الانتظار لنفس الرقم
        """
        cleaned_phone = phone_number.strip()
        
        # 1. فحص عدد الطلبات القائمة الحالية لهذا الرقم بصفة 'PENDING'
        pending_count = SubscriptionRequest.objects.filter(
            phoneNumber=cleaned_phone,
            status='PENDING'
        ).count()

        if pending_count >= 2:
            raise ValueError("لديك طلبان اشتراك قيد الانتظار مسبقاً برقم الهاتف هذا. يرجى الانتظار لحين معالجتهما قبل إرسال طلب جديد.")

        req = SubscriptionRequest.objects.create(
            fullName=full_name.strip(),
            phoneNumber=cleaned_phone,
            governorate=governorate.strip(),
            detailedAddress=detailed_address.strip(),
            status='PENDING'
        )
        return req

    @classmethod
    def provision_and_complete_request(cls, request_id: int, meter_id: str, alias: str) -> tuple:
        """
        العملية الذرية الموحدة (Atomic Provisioning):
        - يفحص هل المواطن مسجل مسبقاً أم جديد.
        - يربط العداد بالحساب تلقائياً.
        - يحول حالة الطلب لمكتمل COMPLETED.
        """
        with transaction.atomic():
            req = SubscriptionRequest.objects.get(pk=request_id)

            if req.status == 'COMPLETED':
                raise ValueError("هذا الطلب معلم كمكتمل مسبقاً.")

            user = User.objects.filter(phoneNumber=req.phoneNumber, role='RESIDENT').first()
            temp_password = None
            is_new_user = False

            if not user:
                # إنشاء حساب جديد وتوليد كلمة مرور مؤقتة
                user, temp_password = UserService.create_resident_user(req.fullName, req.phoneNumber)
                is_new_user = True

            # إسناد العداد سواء كان الحساب جديداً أو موجوداً مسبقاً
            AssociationService.assign_meter_to_user(meter_id, user.id, alias)

            # تحويل حالة الطلب إلى مكتمل
            req.status = 'COMPLETED'
            req.save()

            return user, temp_password, is_new_user, req

    @classmethod
    def update_request_status(cls, request_id: int, new_status: str) -> SubscriptionRequest:
        req = SubscriptionRequest.objects.get(pk=request_id)

        # قيد الأمان الصارم: يمنع تحويل الطلب لمكتمل إذا لم يكن هناك أي عداد مرتبط بحساب المشترك!
        if new_status == 'COMPLETED':
            user = User.objects.filter(phoneNumber=req.phoneNumber, role='RESIDENT').first()
            has_bound_meters = user and user.meter_preferences.exists() if user else False

            if not has_bound_meters:
                raise ValueError("عذراً، يمنع تعيين الطلب كمكتمل لعدم وجود أي عداد مرتبط بحساب هذا المشترك حتى الآن. يرجى إسناد عداد أولاً عبر زر 'تركيب وحساب'.")

        if new_status in ['PENDING', 'COMPLETED', 'CANCELLED']:
            req.status = new_status
            req.save()
        return req

    @classmethod
    def delete_request(cls, request_id: int) -> None:
        req = SubscriptionRequest.objects.get(pk=request_id)
        req.delete()