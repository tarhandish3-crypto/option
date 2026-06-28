# strategies/definitions/__init__.py

"""
استراتژی‌های موجود:
    - long_call          : خرید اختیار خرید
    - long_put           : خرید اختیار فروش
    - covered_call       : خرید سهم + فروش اختیار خرید
    - married_put        : خرید سهم + خرید اختیار فروش
    - collar             : خرید سهم + خرید پوت + فروش کال
    - bull_call_spread   : خرید Call پایین‌تر + فروش Call بالاتر
    - bear_put_spread    : فروش Put پایین‌تر + خرید Put بالاتر
    - long_straddle      : خرید Call + خرید Put با strike یکسان
    - long_strangle      : خرید Put + خرید Call با strike متفاوت
    - long_guts          : خرید Put + خرید Call (ITM)
    - strip              : 1 Call + 2 Put - دیدگاه نزولی
    - strap              : 1 Put + 2 Call - دیدگاه صعودی
    - conversion         : خرید سهم + فروش کال + خرید پوت (آربیتراژ)
    - long_box           : استراتژی آربیتراژ
"""

# بارگذاری پویا در strategies.core انجام می‌شود
# بنابراین این فایل فقط برای معرفی ماژول است.

__all__ = []