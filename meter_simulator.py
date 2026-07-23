import os
import time
import requests
from datetime import datetime

# إعدادات الروابط
SERVER_URL = "http://127.0.0.1:8000"
METER_ID = "11111111-1111-1111-1111-111111111111"

BULK_API = f"{SERVER_URL}/api/meter/{METER_ID}/consumption/bulk_backfill/"
LIVE_API = f"{SERVER_URL}/api/meter/{METER_ID}/consumption/update/"

FILE_PATH = os.path.join('core', 'data', 'channel_1.dat')

def load_and_aggregate_data():
    if not os.path.exists(FILE_PATH):
        print(f"عذراً، لم يتم العثور على ملف القراءات في المسار: {FILE_PATH}")
        return None

    print("جاري قراءة وضغط البيانات التاريخية لربع ساعة للحقن التاريخي...")
    
    original_start_ts = 1352500095
    target_start_ts = 1746057600  # 1 أيار 2025
    time_offset = target_start_ts - original_start_ts
    
    # حد النهاية التاريخي للحقن هو "هذه اللحظة الحالية لجهازك الآن"
    current_real_time_ts = int(time.time())
    
    cumulative_wh = 0.0
    interval_data = {}
    last_processed_orig_ts = 0

    with open(FILE_PATH, 'r') as file:
        for line in file:
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            
            orig_ts = int(parts[0])
            watts = float(parts[1])

            shifted_ts = orig_ts + time_offset
            
            # نتوقف عن تجميع الحقن التاريخي فوراً إذا وصلنا للتوقيت الفعلي الحالي لجهازك الآن
            if shifted_ts >= current_real_time_ts:
                last_processed_orig_ts = orig_ts
                break

            # ضغط البيانات التاريخية لربع ساعة لتأمين أداء فائق لقاعدة البيانات
            dt = datetime.fromtimestamp(shifted_ts)
            minute_block = (dt.minute // 15) * 15
            rounded_dt = dt.replace(minute=minute_block, second=0, microsecond=0)
            rounded_ts = int(rounded_dt.timestamp())

            # حساب الطاقة المستهلكة الخام (بدون معامل مواءمة)
            energy_wh = watts * (6.0 / 3600.0)

            if rounded_ts not in interval_data:
                interval_data[rounded_ts] = 0.0
            interval_data[rounded_ts] += energy_wh
            last_processed_orig_ts = orig_ts

    # فرز وتراكم البيانات لربع ساعة وتقريبها لخانتين عشريتين تماماً لموافقة شروط قاعدة البيانات
    sorted_ts = sorted(interval_data.keys())
    bulk_payload = []
    
    for ts in sorted_ts:
        cumulative_wh += interval_data[ts]
        bulk_payload.append({
            "timestamp": ts,
            "cumulativeWh": round(cumulative_wh, 2) # تقريب دقيق لخانتين عشريتين
        })

    return bulk_payload, last_processed_orig_ts, time_offset

def start_simulation():
    # 1. مرحلة الحقن التاريخي التلقائي والتصفير الفوري لقاعدة البيانات والكاش
    payload_data = load_and_aggregate_data()
    if not payload_data:
        return

    bulk_readings, last_orig_ts, offset = payload_data
    
    print(f"جاري إرسال طلب الحقن التاريخي لـ {len(bulk_readings)} قراءة تراكمية...")
    try:
        response = requests.post(BULK_API, json={"readings": bulk_readings})
        if response.status_code == 201:
            print("نجحت عملية التصفير والحقن التاريخي بنجاح مذهل!")
        else:
            print(f"فشل الحقن التاريخي: {response.text}")
            return
    except Exception as e:
        print(f"تعذر الاتصال بالسيرفر للحقن: {str(e)}")
        return

    # 2. الدخول الفوري في مرحلة البث الحي بالواط الفعلي والتوقيت الحالي لجهازك
    print("\n==================================================")
    print("بدء مرحلة البث اللحظي الحي الحقيقي (كل 6 ثوانٍ)...")
    print("==================================================\n")

    current_orig_ts = last_orig_ts
    
    with open(FILE_PATH, 'r') as file:
        for line in file:
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            orig_ts = int(parts[0])
            if orig_ts <= current_orig_ts:
                continue
            
            watts = float(parts[1])
            
            # إرسال قراءة الواط اللحظية مصحوبة بالتوقيت الفعلي اللحظي الحالي لجهازك الآن
            current_timestamp = int(time.time())
            dt_str = datetime.fromtimestamp(current_timestamp).strftime('%Y-%m-%d %H:%M:%S')

            print(f"[العداد الذكي] بث حي -> الاستطاعة: {watts} واط | التوقيت: {dt_str}")

            payload = {
                "watts": watts,
                "timestamp": current_timestamp
            }

            try:
                res = requests.post(LIVE_API, json=payload)
                if res.status_code == 201:
                    print(f"   [السيرفر] تم الاستلام والتراكم. القراءة الكلية: {res.json()['data']['cumulativeWh']} Wh")
                else:
                    print(f"   [السيرفر] خطأ في الاستلام: {res.text}")
            except Exception as e:
                print(f"   [السيرفر] فشل في الاتصال: {str(e)}")

            time.sleep(6)

if __name__ == "__main__":
    start_simulation()