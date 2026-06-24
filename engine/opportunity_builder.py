# engine/opportunity_builder.py

from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime

from core.models import Opportunity, LegDefinition
from core.enums import Side
from analytics.margin_calculator import MarginCalculator
from scoring.liquidity_score import LiquidityScorer

logger = logging.getLogger("OptionScanner.Engine.OpportunityBuilder")


class OpportunityBuilder:
    """
    کارخانه تبدیل لنگه‌های خام معاملاتی به شیء کپسوله‌شده Opportunity همراه با محاسبات مالی
    
    مسئولیت‌ها:
        - محاسبه total_premium
        - محاسبه required_margin
        - محاسبه liquidity_score
        - استخراج break_even_points
        - ساخت Opportunity نهایی
    """
    
    @staticmethod
    def create_opportunity(
        strategy_name: str,
        ticker: str,
        legs: List[Opportunity],
        metrics: Opportunity,
        days_to_maturity: int,
        underlying_price: float = 0.0,
        break_even_points: Optional[List[float]] = None) -> Opportunity:
        """
        ساخت و تنظیم فیلدهای تخت و ساختاریافته مدل Opportunity
        
        Args:
            strategy_name: نام استراتژی
            ticker: نماد پایه
            legs: لیست لگ‌های استراتژی
            metrics: معیارهای محاسبه شده
            days_to_maturity: روزهای مانده تا سررسید
            underlying_price: قیمت سهم پایه (برای محاسبه مارجین)
            break_even_points: نقاط سربه‌سر (اختیاری)
            
        Returns:
            Opportunity: شیء فرصت معاملاتی
        """
        # 1. محاسبه کل حق بیمه
        total_premium = OpportunityBuilder._calculate_total_premium(legs)
        
        # 2. محاسبه وجه تضمین مورد نیاز
        required_margin = OpportunityBuilder._calculate_required_margin(legs, underlying_price)
        
        # 3. محاسبه امتیاز نقدشوندگی
        liquidity_score = OpportunityBuilder._calculate_liquidity_score(legs)
        
        # 4. محاسبه امتیاز قابلیت اجرا
        execution_score = OpportunityBuilder._calculate_execution_score(legs)
        
        # 5. استخراج نقاط سربه‌سر
        if break_even_points is None:
            break_even_points = OpportunityBuilder._extract_break_even_points(metrics)
        
        # 6. ساخت Opportunity
        opp = Opportunity(
            strategy_name=strategy_name,
            ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            scan_timestamp=datetime.now(),
            
            # معیارهای سرمایه
            required_margin=required_margin,
            total_premium=total_premium,
            
            # معیارهای اجرا
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            
            # معیارهای ترکیبی
            metrics=metrics,
            
            # نقاط سربه‌سر
            break_even_points=break_even_points or [],
            
            # امتیاز نهایی و رتبه (مقدار اولیه)
            final_score=0.0,
            rank=0)
        
        return opp
    
    @staticmethod
    def _calculate_total_premium(legs: List[Opportunity]) -> float:
        """
        محاسبه کل حق بیمه استراتژی
        
        فرمول: جمع (قیمت ورود * وزن) برای همه لگ‌ها
        """
        total = 0.0
        for leg in legs:
            # وزن مثبت = خرید (هزینه)، وزن منفی = فروش (دریافت)
            total += leg.entry_price * leg.weight
        return round(total, 2)
    
    @staticmethod
    def _calculate_required_margin(
        legs: List[Opportunity],
        underlying_price: float) -> float:
        """
        محاسبه وجه تضمین مورد نیاز استراتژی
        
        فقط برای موقعیت‌های فروش (Short) محاسبه می‌شود
        """
        total_margin = 0.0
        
        for leg in legs:
            if leg.side == Side.SELL:
                contract = leg.contract
                margin = MarginCalculator.calculate_contract_margin(
                    contract=contract,
                    underlying_close_price=underlying_price or contract.underlying_price)
                total_margin += margin["required_margin"] * leg.ratio
        
        return round(total_margin, 2)
    
    @staticmethod
    def _calculate_liquidity_score(legs: List[LegDefinition]) -> float:
        """
        محاسبه امتیاز نقدشوندگی استراتژی
        """
        if not legs:
            return 0.0
        
        scores = []
        for leg in legs:
            score = LiquidityScorer.score_single_contract(leg.contract)
            scores.append(score)
        
        # 70% وزن ضعیف‌ترین لگ + 30% میانگین
        weakest = min(scores)
        avg = sum(scores) / len(scores)
        
        return round((weakest * 0.70) + (avg * 0.30), 2)
    
    @staticmethod
    def _calculate_execution_score(legs: List[Opportunity]) -> float:
        """
        محاسبه امتیاز قابلیت اجرا استراتژی
        """
        if not legs:
            return 0.0
        
        # حداقل حجم در بین لگ‌ها
        min_volume = min(leg.contract.volume for leg in legs)
        min_oi = min(leg.contract.open_interest for leg in legs)
        
        # حداکثر اسپرد
        max_spread = 0.0
        for leg in legs:
            if leg.contract.bid > 0 and leg.contract.ask > 0:
                spread = (leg.contract.ask - leg.contract.bid) / ((leg.contract.bid + leg.contract.ask) / 2)
                max_spread = max(max_spread, spread)
        
        score = 100.0
        
        # جریمه حجم
        if min_volume < 50:
            score -= 30
        elif min_volume < 200:
            score -= 15
        
        # جریمه OI
        if min_oi < 20:
            score -= 25
        elif min_oi < 100:
            score -= 12
        
        # جریمه اسپرد
        if max_spread > 0.15:
            score -= 30
        elif max_spread > 0.10:
            score -= 20
        elif max_spread > 0.05:
            score -= 10
        
        # جریمه تعداد لگ‌ها
        score -= (len(legs) - 1) * 5
        
        return max(0.0, round(score, 2))
    
    @staticmethod
    def _extract_break_even_points(metrics: Opportunity) -> List[float]:
        """
        استخراج نقاط سربه‌سر از معیارها
        
        در صورت عدم وجود، لیست خالی برمی‌گرداند
        """
        # در آینده می‌توان از محاسبات Payoff استخراج کرد
        return []