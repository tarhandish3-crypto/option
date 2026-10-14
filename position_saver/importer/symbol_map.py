# position_saver/importer/symbol_map.py
# -*- coding: utf-8 -*-

"""
نقشه‌ی نمادهای پایه‌ی آپشن + کدهای InstrumentCode-UA.

هر نماد پایه که در این لیست است، حتماً آپشن دارد.
نمادهای خارج از این لیست → آپشن ندارند ولی نگه داشته می‌شوند
تا کاربر خودش تصمیم بگیرد.
"""

import logging
from typing import Optional

logger = logging.getLogger("PositionSaver.Importer.SymbolMap")


# ═══════════════════════════════════════════════════
# نقشه‌ی نماد پایه → کد InstrumentCode-UA
# ═══════════════════════════════════════════════════

SYMBOL_MAP = {
    "تاصيكو": "23293437377896568",
    "توان": "41927452991671109",
    "موج": "67141987086032267",
    "اهرم": "17914401175772326",
    "اطلس": "11427939669935844",
    "شپنا": "7745894403636165",
    "فزر": "8175784894140974",
    "وبملت": "778253364357513",
    "وتجارت": "63917421733088077",
    "طعام": "31230051169165044",
    "جوانه كوچك": "67455383896188985",
    "شستا": "2400322364771558",
    "خودرو": "65883838195688438",
    "فملي": "35425587644337450",
    "هم تراز": "51920757918600374",
    "ذوب": "71483646978964608",
    "وبصادر": "28320293733348826",
    "زرگر": "16817885126368964",
    "جواهر": "38544104313215500",
    "كهربا": "25559236668122210",
    "طلا": "46700660505281786",
    "درخشان": "61805666737517582",
    "بساما": "41625340598198551",
}

CODE_TO_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}


# ═══════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════

def is_known_underlying(symbol: str) -> bool:
    """آیا این نماد یک سهم پایه‌ی شناخته‌شده است؟"""
    if not symbol:
        return False
    s = str(symbol).strip()
    return s in SYMBOL_MAP


def get_underlying_ins_code(symbol: str) -> str:
    """دریافت کد InstrumentCode-UA برای یک سهم پایه"""
    if not symbol:
        return ""
    return SYMBOL_MAP.get(str(symbol).strip(), "")


def get_symbol_by_ins_code(ins_code: str) -> Optional[str]:
    """دریافت نام نماد از روی کد InstrumentCode-UA"""
    if not ins_code:
        return None
    return CODE_TO_SYMBOL.get(str(ins_code).strip())


def is_option_symbol(symbol: str) -> bool:
    """آیا این نماد یک قرارداد آپشن است؟ (فقط بر اساس پیشوند)"""
    if not symbol:
        return False
    s = str(symbol).strip()
    return s.startswith(("ض", "ط"))


def infer_underlying_from_option(option_symbol: str) -> str:
    """
    استخراج نام سهم پایه از روی نماد آپشن.

    مثال:
        ضفزر819 → فزر
        طخودرو805 → خودرو
    """
    if not option_symbol:
        return ""
    s = str(option_symbol).strip()
    if s.startswith(("ض", "ط")):
        s = s[1:]
    # حذف اعداد انتهایی
    import re
    m = re.match(r'([^\d]+)', s)
    if m:
        return m.group(1).strip()
    return s[:4] if len(s) >= 4 else s


__all__ = [
    "SYMBOL_MAP",
    "CODE_TO_SYMBOL",
    "is_known_underlying",
    "get_underlying_ins_code",
    "get_symbol_by_ins_code",
    "is_option_symbol",
    "infer_underlying_from_option",
]