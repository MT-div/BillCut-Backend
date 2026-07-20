import string
import random
from django.contrib.auth import authenticate
from core.models import User, NotificationSettings

class AuthService:

    @staticmethod
    def generate_temp_password(length=8) -> str:
        """
        خدمة توليد كلمات المرور المؤقتة والآمنة للمستخدمين الجدد
        """
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    @classmethod
    def create_resident_user(cls, full_name: str, phone_number: str) -> tuple:
        """
        خدمة إنشاء مستخدم جديد وتأسيس إعدادات الإشعارات التلقائية له (Composition)
        """
        temp_password = cls.generate_temp_password()
        
        # إنشاء اسم مستخدم فريد يعتمد على رقم الهاتف
        username = f"user_{phone_number[-10:]}"
        
        # إنشاء كائن المستخدم وحفظه مشفراً
        user = User.objects.create_user(
            username=username,
            phoneNumber=phone_number,
            fullName=full_name,
            role='RESIDENT',
            password=temp_password # دجانغو سيقوم بتشفيرها تلقائياً بـ pbkdf2_sha256
        )
        
        # إنشاء كائن الإعدادات الافتراضية المرتبط به
        NotificationSettings.objects.create(user=user)
        
        return user, temp_password