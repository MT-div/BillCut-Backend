import string
import random
from decimal import Decimal
from core.models import User, NotificationSettings

class UserService:

    @staticmethod
    def generate_temp_password(length=8) -> str:
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    @classmethod
    def create_resident_user(cls, full_name: str, phone_number: str) -> tuple:
        temp_password = cls.generate_temp_password()
        username = f"user_{phone_number[-10:]}"
        
        user = User.objects.create_user(
            username=username,
            phoneNumber=phone_number,
            fullName=full_name,
            role='RESIDENT',
            password=temp_password
        )
        NotificationSettings.objects.create(user=user)
        return user, temp_password

    @staticmethod
    def update_user_account(user_id: int, full_name: str, phone_number: str) -> User:
        user = User.objects.get(pk=user_id, role='RESIDENT')
        user.fullName = full_name
        user.phoneNumber = phone_number
        
        # حسم التزامن الهيكلي: إعادة صياغة ومزامنة اسم المستخدم (Username) تلقائياً ليطابق الهاتف المعدّل من الأدمن
        user.username = f"user_{phone_number[-10:]}"
        
        user.save()
        return user


    @staticmethod
    def delete_user_account(user_id: int) -> None:
        user = User.objects.get(pk=user_id, role='RESIDENT')
        user.delete() # الحذف المتتالي سيتكفل بالباقي


    @staticmethod
    def update_phone(user_id: int, new_phone: str) -> User:
        user = User.objects.get(pk=user_id)
        user.phoneNumber = new_phone
        user.username = f"user_{new_phone[-10:]}"
        user.save()
        return user

    @staticmethod
    def update_password(user_id: int, new_password: str) -> User:
        user = User.objects.get(pk=user_id)
        user.set_password(new_password)
        user.save()
        return user
    
    @staticmethod
    def update_profile(user_id: int, new_phone: str, new_password: str = None) -> User:
        user = User.objects.get(pk=user_id)
        user.phoneNumber = new_phone
        
        # مزامنة وتحديث اسم المستخدم (Username) تلقائياً ليتوافق مع الهاتف الجديد لمنع أي تضارب أمني
        user.username = f"user_{new_phone[-10:]}"
        
        if new_password:
            user.set_password(new_password)
        user.save()
        return user