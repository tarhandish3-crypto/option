# analytics/strategy_classifier.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from core.models import Opportunity, StrategyClassification
from core.enums import OptionType, Side, MarketType, RiskLevel, InvestorProfile

# تنظیم لوگر اختصاصی
logger = logging.getLogger("OptionScanner.Analytics.Classifier")


class StrategyClassifier:
    """
    موتور هوشمند و یونانی‌محور طبقه‌بندی موقعیت‌های معاملاتی (Greeks-Driven Classification)
    
    تغییرات نسخه جدید:
    ۱. استفاده ۱۰۰٪ از Enumهای هسته (MarketType, RiskLevel, InvestorProfile) به جای استرینگ خام.
    ۲. مجهز به متد batch_classify جهت پردازش گروهی و سریع در خط لوله اسکنر.
    ۳. ارتقای متد تشخیص سناریوی بازار با تحلیل مستقیم گاما (Gamma) و تتا (Theta) پوزیشن.
    """

    @classmethod
    def batch_classify(cls, opportunities: List[Opportunity]) -> List[Opportunity]:
        """
        طبقه‌بندی گروهی و دسته‌ای فرصت‌های معاملاتی خروجی رنکر
        """
        for opp in opportunities:
            cls.classify(opp)
        logger.info(f"🏷️ تعداد {len(opportunities)} موقعیت معاملاتی با موفقیت برچسب‌گذاری فازی شدند.")
        return opportunities

    @classmethod
    def classify(cls, opportunity: Opportunity) -> StrategyClassification:
        """
        تحلیل ارگانیک یک موقعیت و تزریق ساختار طبقه‌بندی الگوهای ساختاریافته به آن
        """
        # ۱. تشخیص سناریوی بازار بر اساس نام استراتژی و یونانی‌های ترکیبی (گاما و تتا)
        market_type = cls._determine_market_type(opportunity)
        
        # ۲. ارزیابی سطح ریسک واقعی
        risk_level = cls._assess_risk_level(opportunity)
        
        # ۳. نگاشت به بهترین پروفایل رفتاری سرمایه‌گذار
        investor_profile = cls._match_investor_profile(opportunity, market_type, risk_level)
        
        # ۴. تولید توصیف متنی فارسی برای رندر نهایی خروجی اکسل
        description = cls._generate_persian_description(opportunity, market_type, investor_profile, risk_level)

        # ساخت و تزریق شیء استاندارد طبقه بندی
        classification = StrategyClassification(
            market_type=market_type.value,          # ذخیره مقدار استرینگ بومی انوم برای گزارش‌گیری
            investor_profile=investor_profile.value,
            risk_level=risk_level.value,
            description=description
        )
        
        opportunity.classification = classification
        return classification

    @classmethod
    def _determine_market_type(cls, opp: Opportunity) -> MarketType:
        """تشخیص دقیق جهت‌گیری بازار با تلفیق ساختار استراتژی و فاکتورهای گاما/تتا/دلتا"""
        name = opp.strategy_name.lower()
        metadata = opp.metadata
        
        # الف) ارزیابی بر اساس یونانی‌های پوزیشن (اولویت با رفتار ریاضی پوزیشن است)
        gamma = metadata.get('total_gamma', 0.0)
        theta = metadata.get('total_theta', 0.0)
        total_delta = metadata.get('total_delta', 0.0)

        # اگر گامای مثبت قوی داشته باشیم -> خریدار نوسان شدید
        if gamma > 0.5:
            return MarketType.HIGH_VOLATILITY
        # اگر گامای منفی قوی داشته باشیم -> فروشنده نوسان / رنج‌باز
        elif gamma < -0.5:
            return MarketType.RANGE_BOUND

        # ب) ارزیابی بر اساس نام و ماهیت ساختاری استراتژی‌ها
        if any(x in name for x in ['straddle', 'strangle', 'iron_butterfly', 'iron_condor', 'calendar']):
            if 'short' in name or 'sell' in name or any(l.side == Side.SELL for l in opp.legs if not l.is_stock_leg):
                return MarketType.RANGE_BOUND
            return MarketType.HIGH_VOLATILITY
            
        if any(x in name for x in ['bull', 'call_calendar', 'covered_call', 'buy_call']):
            return MarketType.MAIN_BULLISH if hasattr(MarketType, 'MAIN_BULLISH') else MarketType.BULLISH
            
        if any(x in name for x in ['bear', 'buy_put', 'protective_put']):
            return MarketType.BEARISH

        # ج) کنترل ثانویه بر اساس دلتای کل پوزیشن
        if total_delta > 0.2:
            return MarketType.BULLISH
        elif total_delta < -0.2:
            return MarketType.BEARISH
            
        # د) اگر تتای پوزیشن مثبت باشد و هیچ روند خاصی کشف نشود
        if theta > 0:
            return MarketType.RANGE_BOUND

        return MarketType.NEUTRAL

    @classmethod
    def _assess_risk_level(cls, opp: Opportunity) -> RiskLevel:
        """تعیین سطح ریسک واقعی با استفاده از ساختار سیستم بازگشتی Enum"""
        metadata = opp.metadata
        is_uncapped_loss = metadata.get('is_uncapped_loss', False)
        
        if is_uncapped_loss or opp.max_loss == float('inf') or opp.max_loss < -50000000:
            return RiskLevel.EXTREME
            
        if opp.required_margin > 0:
            loss_to_margin_ratio = abs(opp.max_loss) / opp.required_margin
            if loss_to_margin_ratio > 0.8:
                return RiskLevel.HIGH
            if loss_to_margin_ratio < 0.2:
                return RiskLevel.LOW
                
        if opp.profile_scores.conservative > 75:
            return RiskLevel.LOW
        elif opp.profile_scores.aggressive > 75:
            return RiskLevel.HIGH
            
        return RiskLevel.MEDIUM

    @classmethod
    def _match_investor_profile(cls, opp: Opportunity, market_type: MarketType, risk_level: RiskLevel) -> InvestorProfile:
        """نگاشت دقیق به آبجکت انوم پروفایل بر اساس برآیند فاکتورهای ریاضیاتی رنکر"""
        scores = opp.profile_scores
        metadata = opp.metadata
        theta = metadata.get('total_theta', 0.0)
        
        # بررسی فاکتور تتا برای استراتژی‌های درآمدی (تتای مثبت به شدت جذاب برای پروفایل Income است)
        if theta > 0 and scores.income > 65:
            return InvestorProfile.INCOME

        # تطابق بر اساس بیشترین امتیاز کسب‌شده در رنکر موازی
        highest_profile = InvestorProfile.BALANCED
        max_score = scores.balanced
        
        if scores.conservative > max_score:
            max_score = scores.conservative
            highest_profile = InvestorProfile.CONSERVATIVE
        if scores.aggressive > max_score:
            max_score = scores.aggressive
            highest_profile = InvestorProfile.AGGRESSIVE
        if scores.income > max_score:
            max_score = scores.income
            highest_profile = InvestorProfile.INCOME
        if scores.volatility > max_score:
            max_score = scores.volatility
            highest_profile = InvestorProfile.VOLATILITY

        # کالیبراسیون محافظه‌کاری سیستم
        if risk_level == RiskLevel.EXTREME and highest_profile in [InvestorProfile.CONSERVATIVE, InvestorProfile.INCOME]:
            return InvestorProfile.AGGRESSIVE
            
        return highest_profile

    @classmethod
    def _generate_persian_description(cls, opp: Opportunity, market: MarketType, profile: InvestorProfile, risk: RiskLevel) -> str:
        """تولید اتوماتیک سطر توصیفی غنی بر اساس مقادیر نمایشی فرعی Enumها"""
        strategy_fa = opp.strategy_name.replace('_', ' ').title()
        
        dict_fa = {
            'Covered Call': 'کاور کادر (خرید سهام + فروش کال)',
            'Bull Call Spread': 'اسپرد صعودی خرید',
            'Bear Put Spread': 'اسپرد نزولی فروش',
            'Long Straddle': 'استرادل خرید (نوسان‌گیری)',
            'Short Straddle': 'استرادل فروش (کسب سود از گذر زمان)',
            'Long Call': 'خرید اختیار خرید عریان',
            'Long Put': 'خرید اختیار فروش عریان'
        }
        strat_desc = dict_fa.get(strategy_fa, strategy_fa)
        
        # استخراج بخش فارسی تمیز داخل پرانتزهای انوم‌ها برای خروجی متنی شکیل
        p_name = profile.value.split('(')[1].replace(')', '') if '(' in profile.value else profile.value
        m_name = market.value.split('(')[1].replace(')', '') if '(' in market.value else market.value
        r_name = risk.value.split('(')[1].replace(')', '') if '(' in risk.value else risk.value

        return f"فرصت {strat_desc} روی نماد {opp.underlying_ticker}، مناسب برای رویکرد {p_name} در سناریوی بازار {m_name}. ریسک: {r_name}."