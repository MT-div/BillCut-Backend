from core.models import User, Meter, UserMeterPreference

class AssociationService:

    @staticmethod
    def assign_meter_to_user(meter_id: str, user_id: int, alias: str) -> UserMeterPreference:
        user = User.objects.get(pk=user_id, role='RESIDENT')
        meter = Meter.objects.get(pk=meter_id)
        
        pref, created = UserMeterPreference.objects.get_or_create(
            user=user,
            meter=meter,
            defaults={'alias': alias, 'isDefault': False}
        )
        if not created:
            raise ValueError("هذا العداد مسند بالفعل لهذا المستخدم مسبقاً.")
        return pref

    @staticmethod
    def unassign_meter_from_user(meter_id: str, user_id: int) -> None:
        pref = UserMeterPreference.objects.get(user_id=user_id, meter_id=meter_id)
        pref.delete()