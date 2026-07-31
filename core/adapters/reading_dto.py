from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

@dataclass(frozen=True)
class StandardReadingDTO:
    """
    كائن النطاق الموحد (Domain Target DTO)
    يحمي قاعدة البيانات عبر توحيد مخرجات جميع محولات العدادات
    مهما كانت صيغة البيانات القادمة من الحساسات.
    """
    cumulativeWh: Decimal
    timestamp: datetime