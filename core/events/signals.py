from django.dispatch import Signal

# تعريف الإشارات السيادية للأحداث الحركية في النظام
anomaly_detected_signal = Signal()       # حدث كشف عطل أو تسريب كهربائي
budget_limit_exceeded_signal = Signal()  # حدث تقييم ميزانية اليوم المنقضي
tier_limit_exceeded_signal = Signal()    # حدث تقييم الشريحة والدعم لليوم المنقضي