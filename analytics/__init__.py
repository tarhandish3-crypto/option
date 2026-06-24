# analytics/__init__.py
# -*- coding: utf-8 -*-

"""
پکیج تحلیل پیشرفته برای استراتژی‌های اختیار معامله بورس ایران

این فایل به عنوان یک لایه دسترسی (Facade) عمل کرده و ابزارهای اصلی محاسبات 
یونانی‌ها، سود/زیان (Payoff)، مدیریت ریسک، وجه تضمین (Margin) و کارمزدها را به صورت یکپارچه عرضه می‌کند.
"""

# ============================================================================
# ۱. یونانی‌ها و توزیع احتمال (Greeks & Probabilities)
# ============================================================================
from analytics.greeks_and_probabilities import (
    calculate_d1_d2,
    calculate_leg_greeks,
    calculate_vega,
    calculate_full_greeks,
    get_price_step_probabilities,
    calculate_strategy_greeks,
)

# ============================================================================
# ۲. محاسبه سود/زیان (Payoff Calculator)
# ============================================================================
from analytics.payoff_calculator import (
    PayoffCalculator,
    PayoffResult
)

# ============================================================================
# ۳. موتور محاسبات ریسک (Risk Engine)
# ============================================================================
from analytics.risk_engine import (
    RiskEngine,
    RiskMetrics,
    CurveType,
    print_risk_summary,
    calculate_risk_metrics_from_payoff
)

# ============================================================================
# ۴. محاسبه وجه تضمین رسمی سمات (Margin Calculator)
# ============================================================================
from analytics.margin_calculator import (
    MarginCalculator,
    MarginResult,
    MarginContract,
    LegDefinition
)

# ============================================================================
# ۵. محاسبه کارمزدها و هزینه‌های معاملاتی (Cost Calculator) ✅ اضافه شد
# ============================================================================
from analytics.cost_calculator import (
    IranMarketCostCalculator,
    AdvancedTradeCosts
)

# تعاریف مشترک از هسته پوزیشن‌ها (در صورت نیاز به استفاده مستقیم در محاسبات)
from core.enums import OptionType, Side

# ============================================================================
# ۶. لیست کلاس‌ها و توابع مجاز پکیج (Public API)
# ============================================================================
__all__ = [
    # بخش یونانی‌ها
    'calculate_d1_d2',
    'calculate_leg_greeks',
    'calculate_vega',
    'calculate_full_greeks',
    'get_price_step_probabilities',
    'calculate_strategy_greeks',
    
    # بخش محاسبات سود و زیان
    'PayoffCalculator',
    'PayoffResult',
    
    # بخش مدیریت و محاسبات ریسک پیشرفته
    'RiskEngine',
    'RiskMetrics',
    'CurveType',
    'print_risk_summary',
    'calculate_risk_metrics_from_payoff',
    
    # بخش ماشین حساب مارجین بورس ایران
    'MarginCalculator',
    'MarginResult',
    'MarginContract',
    'LegDefinition',
    
    # بخش محاسبات کارمزد بورس ایران ✅ اضافه شد
    'IranMarketCostCalculator',
    'AdvancedTradeCosts',
    
    # انوم‌های مرجع
    'OptionType',
    'Side',
]