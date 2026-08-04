import os
import logging
import numpy as np
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

# مسارات الأوزان والـ Scaler2 الخاصة بالتنبؤ اليومي
WEIGHTS_PATH = os.path.join(settings.BASE_DIR, 'core', 'ai_models', 'saved_models', '04_window_60_2.weights.h5')
SCALER_PATH = os.path.join(settings.BASE_DIR, 'core', 'ai_models', 'saved_models', 'scaler2.pkl')

_DAILY_MODEL = None
_DAILY_SCALER = None

def build_daily_model_architecture():
    """
    بناء البنية الهندسية لنموذج التنبؤ اليومي:
    Input(shape=(60, 1)) -> LSTM(100, relu, return_sequences=True) -> Dropout(0.2) -> LSTM(32, relu) -> Dense(1)
    """
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Input, LSTM, Dropout, Dense

    model = Sequential([
        Input(shape=(60, 1)),
        LSTM(100, activation='relu', return_sequences=True),
        Dropout(0.2),
        LSTM(32, activation='relu'),
        Dense(1)
    ])
    return model

def load_daily_ai_assets():
    """
    تحميل أوزان النموذج والـ Scaler2 مرة واحدة في الذاكرة (Singleton Pattern)
    """
    global _DAILY_MODEL, _DAILY_SCALER
    if _DAILY_MODEL is None and os.path.exists(WEIGHTS_PATH):
        try:
            model = build_daily_model_architecture()
            model.load_weights(WEIGHTS_PATH)
            _DAILY_MODEL = model
            logger.info("تم تحميل أوزان نموذج LSTM اليومي (60 يوماً) بنجاح.")
        except Exception as e:
            logger.error(f"فشل تحميل أوزان النموذج اليومي: {str(e)}")

    if _DAILY_SCALER is None and os.path.exists(SCALER_PATH):
        try:
            import joblib
            _DAILY_SCALER = joblib.load(SCALER_PATH)
            logger.info("تم تحميل Scaler2 التنبؤ اليومي بنجاح.")
        except Exception as e:
            logger.error(f"فشل تحميل Scaler2: {str(e)}")

    return _DAILY_MODEL, _DAILY_SCALER

def predict_daily_consumption(historical_days_data: list) -> Decimal:
    """
    التنبؤ باستهلاك اليوم القادم بناءً على نافذة الـ 60 يوماً التاريخية:
    - الأيام المتاحة 0 -> إرجاع المتوسط الإقليمي (12.50 kWh)
    - الأيام المتاحة < 60 -> إرجاع المتوسط الحسابي للأيام المتاحة (Cold Start)
    - الأيام المتاحة >= 60 -> استدعاء نموذج LSTM ذو النافذة 60
    """
    raw_data = [float(x) for x in historical_days_data] if historical_days_data else []
    count = len(raw_data)

    # 1. حالة البداية الباردة (0 يوم)
    if count == 0:
        logger.info("Daily Cold Start: 0 days available. Returning regional default 12.50 kWh.")
        return Decimal('12.50')

    # 2. حالة البداية الباردة (أقل من 60 يوماً): عدم استدعاء الموديل
    if count < 60:
        avg_val = Decimal(str(sum(raw_data))) / Decimal(str(count))
        logger.info(f"Daily Cold Start: {count} days available (<60). Returning calculated mean: {avg_val:.2f} kWh.")
        return round(avg_val, 2)

    # 3. النافذة المكتملة (60 يوماً فأكثر): تشغيل النموذج الحقيقي
    model, scaler = load_daily_ai_assets()
    input_60 = np.array(raw_data[-60:], dtype=np.float32)

    if model is not None and scaler is not None:
        try:
            # تقييس البيانات للنافذة 60
            features = ['consumption_sum']
            scaled_input = scaler.transform(input_60.reshape(-1, 1)).flatten()
            scaled_input = np.clip(scaled_input, 0, 1)
            input_3d = scaled_input.reshape((1, 60, 1))

            # إجراء التنبؤ
            pred_scaled = model.predict(input_3d, verbose=0)[0][0]
            pred_scaled = np.clip(pred_scaled, 0, 1)

            # التحويل العكسي
            pred_raw = scaler.inverse_transform(np.array([[pred_scaled]]))[0][0]
            predicted_kwh = round(Decimal(str(max(0.0, float(pred_raw)))), 2)

            return predicted_kwh
        except Exception as e:
            logger.error(f"خطأ أثناء التنبؤ بالموديل اليومي: {str(e)}")

    # خطة احتياطية
    avg_val = Decimal(str(sum(input_60))) / Decimal('60.0')
    return round(avg_val, 2)