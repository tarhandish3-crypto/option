import json
import requests


def generate_js_contract_sizes():
    url = (
        "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        options_list = data.get("instrumentOptMarketWatch", [])

        contract_sizes = {}

        for item in options_list:
            size = item.get("contractSize", 1000)

            # استخراج نام نماد پایه
            full_name = item.get("lval30_UA") or item.get("lVal18AFC_UA")

            # اگر نام نماد پایه معتبر بود ذخیره کند
            if full_name and isinstance(full_name, str):
                full_name = full_name.strip()
                contract_sizes[full_name] = size

        # مرتب‌سازی الفبایی نمادهای پایه
        sorted_sizes = dict(sorted(contract_sizes.items()))

        # تبدیل دیکشنری به فرمت کد جاوااسکریپت
        js_code = "var SYMBOL_CONTRACT_SIZE = {\n"
        for symbol, size in sorted_sizes.items():
            js_code += f"    '{symbol}': {size},\n"

        if sorted_sizes:
            js_code = js_code.rstrip(",\n") + "\n"
        js_code += "};"

        # ذخیره صحیح متنی در فایل
        with open("contract_sizes.js", "w", encoding="utf-8") as f:
            f.write(js_code)

    except Exception as e:
        print(f"❌ خطا در دریافت یا ذخیره داده‌ها: {e}")


if __name__ == "__main__":
    generate_js_contract_sizes()