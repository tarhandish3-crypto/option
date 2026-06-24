# core/enums.py
# -*- coding: utf-8 -*-

from enum import Enum

class GeneratorType(Enum):
    """نوع تولیدکننده ترکیب‌ها"""
    STOCK_OPTION = "stock_option"
    SINGLE_LEG = "single_leg"
    TWO_LEG = "two_leg"
    THREE_LEG = "three_leg"
    FOUR_LEG = "four_leg"


class OptionType(Enum):
    """نوع اختیار معامله"""
    CALL = "Call"
    PUT = "Put"


class OptionStatus(Enum):
    """وضعیت اختیار نسبت به قیمت سهم"""
    ITM = "ITM"      # In The Money (داخل پول)
    ATM = "ATM"      # At The Money (هم‌قیمت)
    OTM = "OTM"      # Out of The Money (خارج از پول)


# ✅ اضافه کردن مجدد جهت همخوانی با لایه models.py
class ExchangeType(Enum):
    """نوع بورس / بازار ساختاری"""
    TSE = "tse"      # بورس تهران
    IFB = "ifb"      # فرابورس


class AssetType(Enum):
    """نوع دارایی پایه"""
    STOCK = "stock"
    ETF_STOCK = "etf-stock"
    ETF_GOLD = "etf-gold"
    ETF_FIX = "etf-fix"
    ETF_MIX = "etf-mix"


class VolatilitySignal(Enum):
    """سیگنال نوسان‌پذیری"""
    OVERPRICED = "OVERPRICED"
    UNDERPRICED = "UNDERPRICED"
    FAIR = "FAIR"


class Side(Enum):
    """سمت معامله"""
    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(Enum):
    """حالت اجرای برنامه"""
    NORMAL = "normal"
    BACKTEST = "backtest"
    SIMULATION = "simulation"


# ✅ انوم رتبه‌بندی پروفایل (پایبند به کدهای قدیمی شما)
class RankingProfile(Enum):
    """پروفایل رتبه‌بندی کاربر"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    INCOME = "income"
    VOLATILITY = "volatility"


# =====================================================
# ✅ انوم‌های کلاسیفایر چندبعدی سیستم تصمیم‌یار (DSS)
# =====================================================

class MarketType(Enum):
    """طبقه‌بندی وضعیت روند و ساختار کلان بازار"""
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"
    HIGH_VOLATILITY = "High Volatility"


class RiskLevel(Enum):
    """سطح ریسک پوزیشن معاملاتی ترکیبی"""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class InvestorProfile(Enum):
    """پروفایل انطباق پوزیشن با روحیات سرمایه‌گذار"""
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"
    INCOME = "Income"
    VOLATILITY = "Volatility"


# =====================================================
# ✅ انوم تشخیص منحنی (Curve Detection)
# =====================================================

class CurveType(Enum):
    """نوع منحنی سود/زیان استراتژی"""
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"
    HIGH_VOLATILITY = "High-Volatility"
    LOW_VOLATILITY = "Low-Volatility"
    BUTTERFLY = "Butterfly"
    IRON_CONDOR = "Iron Condor"
    FLAT = "Flat"
    UNKNOWN = "Unknown"