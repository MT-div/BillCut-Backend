from decimal import Decimal

def predict_daily_consumption(historical_days_data) -> Decimal:
    """
    محاكاة مؤقتة لنموذج GRU اليومي:
    يتوقع استهلاك اليوم الجديد بناءً على متوسط الأيام السابقة.
    """
    if not historical_days_data:
        return Decimal('12.50')
        
    avg_daily = sum(historical_days_data) / len(historical_days_data)
    return round(avg_daily, 2)