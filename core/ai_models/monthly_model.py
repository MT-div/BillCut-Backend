# from decimal import Decimal

# def predict_monthly_consumption(historical_data_13_months) -> tuple:
#     """
#     محاكاة مؤقتة لنموذج LSTM الشهري:
#     تحسب متوسط الاستهلاك لآخر 13 شهراً وتتوقع قيم الشهر الأول والثاني حول هذا المتوسط.
#     """
#     if not historical_data_13_months:
#         return Decimal('350.00'), Decimal('320.00') # قيم افتراضية في حال عدم توفر البيانات
        
#     avg_consumption = sum(historical_data_13_months) / len(historical_data_13_months)
#     # توليد قيم قريبة من المتوسط مع انحراف بسيط للمحاكاة الواقعية
#     predicted_m1 = round(avg_consumption * Decimal('0.95'), 2)
#     predicted_m2 = round(avg_consumption * Decimal('1.02'), 2)
#     return predicted_m1, predicted_m2

import os
import logging
import numpy as np
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_WEIGHTS_PATH = os.path.join(settings.BASE_DIR, 'core', 'ai_models', 'saved_models', 'best_model_weights.weights.h5')
SCALER_PATH = os.path.join(settings.BASE_DIR, 'core', 'ai_models', 'saved_models', 'scaler.pkl')

_MONTHLY_MODEL = None
_MONTHLY_SCALER = None

def build_monthly_model_architecture():
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Input, LSTM, Dropout, Dense

    model = Sequential([
        Input(shape=(13, 1)),
        LSTM(100, return_sequences=True, activation='relu'),
        Dropout(0.3),
        LSTM(32, return_sequences=False, activation='relu'),
        Dense(1)
    ])
    return model

def load_ai_assets():
    global _MONTHLY_MODEL, _MONTHLY_SCALER
    if _MONTHLY_MODEL is None and os.path.exists(MODEL_WEIGHTS_PATH):
        try:
            model = build_monthly_model_architecture()
            model.load_weights(MODEL_WEIGHTS_PATH)
            _MONTHLY_MODEL = model
            logger.info("تم تحميل أوزان نموذج LSTM الشهري بنجاح.")
        except Exception as e:
            logger.error(f"فشل تحميل أوزان النموذج: {str(e)}")

    if _MONTHLY_SCALER is None and os.path.exists(SCALER_PATH):
        try:
            import joblib
            _MONTHLY_SCALER = joblib.load(SCALER_PATH)
            logger.info("تم تحميل Scaler الذكاء الاصطناعي بنجاح.")
        except Exception as e:
            logger.error(f"فشل تحميل Scaler: {str(e)}")

    return _MONTHLY_MODEL, _MONTHLY_SCALER

def predict_monthly_consumption(historical_months: list) -> Decimal:
    """
    وظيفة واحدة صافية (SRP): يتوقع استهلاك شهر واحد قادم بناءً على القائمة الممررة:
    - اللائحة فارغة (0) -> يرجع المتوسط الإقليمي (350.00 kWh)
    - اللائحة أقل من 13 شهراً -> يرجع المتوسط الحسابي للأشهر المتوفرة
    - اللائحة 13 شهراً أو أكثر -> يأخذ آخر 13 شهراً ويستدعي نموذج LSTM
    """
    raw_data = [float(x) for x in historical_months] if historical_months else []
    count = len(raw_data)

    # 1. اللائحة فارغة تماماً (0 شهر)
    if count == 0:
        logger.info("Cold Start: 0 months available. Returning regional default 350.00 kWh.")
        return Decimal('350.00')

    # 2. اللائحة أقل من 13 شهراً
    if count < 13:
        avg_val = Decimal(str(sum(raw_data))) / Decimal(str(count))
        logger.info(f"Cold Start: {count} months available. Returning calculated mean: {avg_val:.2f} kWh.")
        return round(avg_val, 2)

    # 3. اللائحة 13 شهراً أو أكثر: اقتطاع آخر 13 شهراً واستدعاء LSTM
    model, scaler = load_ai_assets()
    input_13 = np.array(raw_data[-13:], dtype=np.float32)

    if model is not None and scaler is not None:
        try:
            scaled_input = scaler.transform(input_13.reshape(-1, 1)).flatten()
            scaled_input = np.clip(scaled_input, 0, 1)
            input_3d = scaled_input.reshape((1, 13, 1))

            pred_scaled = model.predict(input_3d, verbose=0)[0][0]
            pred_scaled = np.clip(pred_scaled, 0, 1)
            
            pred_raw = scaler.inverse_transform(np.array([[pred_scaled]]))[0][0]
            predicted_kwh = round(Decimal(str(max(0.0, float(pred_raw)))), 2)
            
            return predicted_kwh
        except Exception as e:
            logger.error(f"خطأ أثناء التنبؤ بنموذج LSTM: {str(e)}")

    # خطة احتياطية عند تعذر تشغيل الموديل
    avg_val = Decimal(str(sum(input_13))) / Decimal('13.0')
    return round(avg_val, 2)