# scoring/liquidity_score.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Dict
from core.models import OptionContract, LegDefinition
from core.enums import OptionType
from config import MIN_VOLUME, MIN_OPEN_INTEREST, MAX_SPREAD_PCT

logger = logging.getLogger("OptionScanner.Scoring.LiquidityScore")


class LiquidityScorer:
    """
    محاسبه‌گر امتیاز نقدشوندگی قراردادها و استراتژی‌ها بر اساس تابلوی بورس ایران
    امتیاز نهایی بین ۰ تا ۱۰۰
    """
    
    # آستانه پیش‌فرض عمق سفارشات (تعداد قرارداد موجود در بهترین بید/اسک)
    DEFAULT_DEPTH_THRESHOLD = 300
    
    # ============================================================
    # متدهای موجود (بدون تغییر)
    # ============================================================

    @staticmethod
    def calc_spread_pct(contract: OptionContract) -> float:
        """
        محاسبه درصد اسپرد بر اساس قیمت میانه (Mid Price) با پایداری کامل خطا
        """
        if contract.bid <= 0 or contract.ask <= 0:
            return 1.0
            
        mid = (contract.bid + contract.ask) / 2.0
        if mid <= 1e-6:
            return 1.0
            
        return (contract.ask - contract.bid) / mid
    
    @classmethod
    def score_single_contract(cls, contract: OptionContract) -> float:
        """
        امتیاز نقدشوندگی یک قرارداد (۰ تا ۱۰۰)
        """
        breakdown = cls.get_score_breakdown(contract)
        return breakdown["total"]
    
    @classmethod
    def pre_score_contracts(cls, contracts: List[OptionContract]) -> Dict[str, float]:
        """پیش‌محاسبه امتیاز همه قراردادها جهت ارتقای سرعت اسکنر با پیچیدگی O(1)"""
        return {contract.ticker: cls.score_single_contract(contract) for contract in contracts}
    
    @classmethod
    def score_strategy(cls, legs: List[LegDefinition], contract_scores: Dict[str, float]) -> float:
        """
        امتیاز نقدشوندگی کل استراتژی ترکیبی
        فرمول: ۷۰٪ وزن ضعیف‌ترین لگ + ۳۰٪ وزن میانگین همراه با جریمه بحرانی اسپرد
        """
        if not legs:
            return 0.0
        
        # استخراج امتیازها از ساختار کَش پیش‌محاسبه شده
        scores = [contract_scores.get(leg.contract.ticker, 0.0) for leg in legs if leg.contract]
        if not scores:
            return 0.0
        
        weakest = min(scores)
        avg = sum(scores) / len(scores)
        
        result = (weakest * 0.70) + (avg * 0.30)
        
        # جریمه اسپردهای بحرانی بازار ایران
        max_spread = max(cls.calc_spread_pct(leg.contract) for leg in legs if leg.contract)
        
        if max_spread > MAX_SPREAD_PCT:
            result *= 0.20
        elif max_spread > 0.15:
            result *= 0.60
        elif max_spread > 0.10:
            result *= 0.85
            
        return round(result, 2)
    
    @classmethod
    def get_score_breakdown(cls, contract: OptionContract) -> Dict[str, float]:
        """
        دریافت تفکیک مؤلفه‌های امتیاز یک قرارداد (منبع واحد محاسبات فاکتورها)
        """
        # ۱. امتیاز حجم معاملات (0-30)
        volume_ratio = min(contract.volume / max(MIN_VOLUME, 1), 1.0)
        volume_score = volume_ratio * 30.0
        
        # ۲. امتیاز موقعیت‌های باز Open Interest (0-25)
        oi_ratio = min(contract.open_interest / max(MIN_OPEN_INTEREST, 1), 1.0)
        oi_score = oi_ratio * 25.0
        
        # ۳. امتیاز اسپرد قیمت (0-25)
        spread = cls.calc_spread_pct(contract)
        if spread >= MAX_SPREAD_PCT:
            spread_score = 0.0
        else:
            spread_score = (1.0 - (spread / MAX_SPREAD_PCT)) * 25.0
        
        # ۴. امتیاز عمق سفارشات خرید و فروش (0-20)
        depth = min(contract.bid_volume, contract.ask_volume)
        depth_ratio = min(depth / cls.DEFAULT_DEPTH_THRESHOLD, 1.0)
        depth_score = depth_ratio * 20.0
        
        total = volume_score + oi_score + spread_score + depth_score
        
        return {
            "volume": round(volume_score, 2),
            "open_interest": round(oi_score, 2),
            "spread": round(spread_score, 2),
            "depth": round(depth_score, 2),
            "total": round(max(0.0, min(total, 100.0)), 2),
        }
    
    @classmethod
    def is_liquid(cls, contract: OptionContract, min_score: float = 40.0) -> bool:
        """بررسی سریع صلاحیت ورود قرارداد به اسکنر"""
        return cls.score_single_contract(contract) >= min_score

    # ============================================================
    # ✅ متد جدید: محاسبه امتیاز اجرا (Execution Score)
    # ============================================================

    @classmethod
    def execution_score(cls, legs: List[LegDefinition]) -> float:
        """
        محاسبه امتیاز قابلیت اجرا (ریسک لغزش قیمت)
    
        
        معیارهای ارزیابی:
        - حجم معاملات (min_volume)
        - Open Interest (min_oi)
        - اسپرد قیمت (max_spread)
        - تعداد لگ‌ها (جریمه پیچیدگی)
        
        Returns:
            float: امتیاز بین ۰ تا ۱۰۰
        """
        if not legs:
            return 0.0
            
        # استخراج لگ‌های اختیار معامله (به جز سهام)
        option_contracts = [
            leg.contract for leg in legs
            if leg.contract and leg.contract.option_type != OptionType.STOCK
        ]
        
        # اگر فقط سهام داریم، اجرا آسان است
        if not option_contracts:
            return 100.0

        # استخراج معیارها
        min_volume = min((c.volume for c in option_contracts), default=0)
        min_oi = min((c.open_interest for c in option_contracts), default=0)
        
        max_spread = 0.0
        for c in option_contracts:
            if c.bid > 0 and c.ask > 0:
                mid = (c.bid + c.ask) / 2
                if mid > 0:
                    max_spread = max(max_spread, (c.ask - c.bid) / mid)

        # شروع از ۱۰۰
        score = 100.0

        # جریمه حجم پایین
        if min_volume < 50:
            score -= 30
        elif min_volume < 200:
            score -= 15
            
        # جریمه Open Interest پایین
        if min_oi < 20:
            score -= 25
        elif min_oi < 100:
            score -= 12
            
        # جریمه اسپرد بالا
        if max_spread > 0.15:
            score -= 30
        elif max_spread > 0.10:
            score -= 20
        elif max_spread > 0.05:
            score -= 10
            
        # جریمه پیچیدگی (هر لگ اضافی)
        score -= (len(legs) - 1) * 5
        
        return max(0.0, round(score, 2))

    # ============================================================
    # متدهای کمکی برای گزارش‌گیری
    # ============================================================

    @classmethod
    def get_min_leg_volume(cls, legs: List[LegDefinition]) -> int:
        return min((leg.contract.volume for leg in legs if leg.contract), default=0)
        
    @classmethod
    def get_min_leg_open_interest(cls, legs: List[LegDefinition]) -> int:
        return min((leg.contract.open_interest for leg in legs if leg.contract), default=0)
        
    @classmethod
    def get_max_leg_spread_pct(cls, legs: List[LegDefinition]) -> float:
        return max((cls.calc_spread_pct(leg.contract) for leg in legs if leg.contract), default=0.0)