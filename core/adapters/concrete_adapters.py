from decimal import Decimal
from datetime import datetime
from typing import Optional
from core.models import ConsumptionReading
from .base_adapter import BaseIngestionAdapter
from .reading_dto import StandardReadingDTO

# 1. محول العدادات اللحظية بالواط (المعتمد حالياً في المحاكي)
class InstantWattsAdapter(BaseIngestionAdapter):
    def parse_payload(
        self, 
        payload: dict, 
        last_reading: Optional[ConsumptionReading], 
        timestamp_dt: datetime
    ) -> StandardReadingDTO:
        watts = Decimal(str(payload.get('watts', '0.00')))
        
        if not last_reading:
            cumulative_wh = Decimal('0.00')
        else:
            delta_t_seconds = Decimal(str((timestamp_dt - last_reading.timestamp).total_seconds()))
            if delta_t_seconds < 0:
                delta_t_seconds = Decimal('0.00')
            
            energy_wh = watts * (delta_t_seconds / Decimal('3600.00'))
            cumulative_wh = last_reading.cumulativeWh + energy_wh

        return StandardReadingDTO(
            cumulativeWh=round(cumulative_wh, 2),
            timestamp=timestamp_dt
        )

# 2. محول العدادات الحديثة التي ترسل الكيلوواط الكلي المباشر (Direct KWh)
class DirectKWhAdapter(BaseIngestionAdapter):
    def parse_payload(
        self, 
        payload: dict, 
        last_reading: Optional[ConsumptionReading], 
        timestamp_dt: datetime
    ) -> StandardReadingDTO:
        raw_kwh = Decimal(str(payload.get('kwh') or payload.get('cumulativeKWh') or '0.00'))
        cumulative_wh = raw_kwh * Decimal('1000.00') # تحويل KWh إلى Wh للموائمة

        return StandardReadingDTO(
            cumulativeWh=round(cumulative_wh, 2),
            timestamp=timestamp_dt
        )

# 3. محول العدادات الصناعية (الفولت والأمبير ومعامل القدرة Volt/Ampere)
class VoltAmpereAdapter(BaseIngestionAdapter):
    def parse_payload(
        self, 
        payload: dict, 
        last_reading: Optional[ConsumptionReading], 
        timestamp_dt: datetime
    ) -> StandardReadingDTO:
        voltage = Decimal(str(payload.get('voltage', '220.0')))
        current = Decimal(str(payload.get('current', '0.0')))
        pf = Decimal(str(payload.get('powerFactor', '0.9'))) # Power Factor
        
        calculated_watts = voltage * current * pf
        
        # استدعاء معادلة تحويل الواط والزمن
        watts_adapter = InstantWattsAdapter()
        return watts_adapter.parse_payload({'watts': calculated_watts}, last_reading, timestamp_dt)