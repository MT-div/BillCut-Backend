from decimal import Decimal

def predict_monthly_consumption(historical_data_13_months) -> tuple:
    """
    محاكاة مؤقتة لنموذج LSTM الشهري:
    تحسب متوسط الاستهلاك لآخر 13 شهراً وتتوقع قيم الشهر الأول والثاني حول هذا المتوسط.
    """
    if not historical_data_13_months:
        return Decimal('350.00'), Decimal('320.00') # قيم افتراضية في حال عدم توفر البيانات
        
    avg_consumption = sum(historical_data_13_months) / len(historical_data_13_months)
    # توليد قيم قريبة من المتوسط مع انحراف بسيط للمحاكاة الواقعية
    predicted_m1 = round(avg_consumption * Decimal('0.95'), 2)
    predicted_m2 = round(avg_consumption * Decimal('1.02'), 2)
    return predicted_m1, predicted_m2