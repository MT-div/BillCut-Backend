from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from core.models import ConsumptionReading
from .reading_dto import StandardReadingDTO

class BaseIngestionAdapter(ABC):
    """
    العقد البرمجي الإجباري (Abstract Adapter Contract)
    يفرض على أي محول عتاد جديد تطبيق دالة parse_payload وتحويل بياناته لـ StandardReadingDTO
    """
    @abstractmethod
    def parse_payload(
        self, 
        payload: dict, 
        last_reading: Optional[ConsumptionReading], 
        timestamp_dt: datetime
    ) -> StandardReadingDTO:
        pass