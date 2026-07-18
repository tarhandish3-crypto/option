import requests
import pandas as pd
import time

def get_option_market_watch():
    """دریافت دیتافریم کامل دیده‌بان بازار اختیار معامله"""
    url = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        raw_data = response.json().get("instrumentOptMarketWatch", [])
        if not raw_data:
            return pd.DataFrame()
        df = pd.json_normalize(raw_data)
        return df
    except:  # noqa: E722
        return pd.DataFrame()


def get_total_shares(ua_inscode):
    """دریافت تعداد کل سهام شرکت پایه بر اساس شناسه نماد"""
    url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/{ua_inscode}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        info = response.json().get('instrumentInfo', {})
        if not info:
            return pd.DataFrame()
        pd.json_normalize(info)
        total_shares = info.get('zTitad')
        return float(total_shares) if total_shares else None
    except Exception:
       return None

def main():
    print("در حال دریافت اطلاعات دیده‌بان آپشن‌ها...")
    df = get_option_market_watch()
    
    if df is None or df.empty:
        print("دیتایی دریافت نشد.")
        return

    # ۱. استخراج لیست نمادهای پایه منحصربه‌فرد برای بهینه‌سازی تعداد درخواست‌ها
    unique_ua_inscodes = df['uaInsCode'].dropna().unique()
    print(f"تعداد {len(unique_ua_inscodes)} دارایی پایه منحصربه‌فرد یافت شد. در حال دریافت تعداد سهام...")
    
    # ۲. گرفتن تعداد کل سهام برای هر نماد پایه و ذخیره در یک دیکشنری (کَش کردن داده)
    ua_shares_dict = {}
    for ua_code in unique_ua_inscodes:
        shares = get_total_shares(ua_code)
        if shares:
            ua_shares_dict[ua_code] = shares
        time.sleep(0.5) # تاخیر نیم ثانیه‌ای برای جلوگیری از بلاک شدن توسط TSETMC
    
    # ۳. نگاشت (Map) تعداد کل سهام به دیتافریم اصلی بر اساس ستون uaInsCode
    df['ua_total_shares'] = df['uaInsCode'].map(ua_shares_dict)
    
    # ۴. فرمول محاسباتی بورس: سقف موقعیت باز بازار (فرض: ۱ درصد کل سهام شرکت پایه)
    # این درصد بسته به نوع نماد ممکن است ۱٪، ۳٪ یا ۵٪ باشد؛ ما ۱٪ را مبنا قرار می‌دهیم.
    PERCENTAGE_LIMIT = 0.01 
    
    # محاسبه سقف مجاز قراردادها (تعداد کل سهام ضربدر درصد مجاز، تقسیم بر اندازه هر قرارداد)
    df['calculated_position_limit'] = (df['ua_total_shares'] * PERCENTAGE_LIMIT) / df['contractSize']
    
    # ۵. محاسبه درصد پر شده سقف برای اختیار خرید (Call) و اختیار فروش (Put)
    # فرمول: (موقعیت‌های باز فعلی / سقف مجاز) * 100
    df['filled_percentage_C'] = (df['yesterdayOP_C'] / df['calculated_position_limit']) * 100
    df['filled_percentage_P'] = (df['yesterdayOP_P'] / df['calculated_position_limit']) * 100
    
    # مرتب‌سازی ستون‌ها برای نمایش تمیزتر خروجی
    final_cols = [
        'lVal30_C', 'yesterdayOP_C', 'filled_percentage_C', 
        'lVal30_P', 'yesterdayOP_P', 'filled_percentage_P',
        'strikePrice', 'calculated_position_limit'
    ]
    
    # حذف ردیف‌هایی که دیتای سهام پایه آن‌ها یافت نشد (اختیاری)
    df_result = df.dropna(subset=['calculated_position_limit'])
    
    print("\n--- ۵ ردیف اول خروجی بر اساس بیشترین موقعیت باز اختیار خرید ---")
    print(df_result[final_cols].sort_values(by='yesterdayOP_C', ascending=False).head().to_string())
    
    # ذخیره خروجی نهایی در یک فایل اکسل جهت بررسی دقیق‌تر
    df_result[final_cols].to_excel("options_open_interest_report.xlsx", index=False)
    print("\nگزارش کامل در فایل options_open_interest_report.xlsx ذخیره شد.")

if __name__ == "__main__":
    main()