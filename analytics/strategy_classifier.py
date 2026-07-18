# analytics/strategy_classifier.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging

from core.models import Opportunity
from core.enums import RiskLevel

# تنظیم لوگر اختصاصی
logger = logging.getLogger("OptionScanner.Analytics.Classifier")


class StrategyClassifier:
    """
    موتور هوشمند و یونانی‌محور طبقه‌بندی موقعیت‌های معاملاتی (Greeks-Driven Classification)
    
    تغییرات نسخه جدید:
    ۱. استفاده ۱۰۰٪ از Enumهای هسته (nvestorProfile) به جای استرینگ خام.
    ۳. ارتقای متد تشخیص سناریوی بازار با تحلیل مستقیم گاما (Gamma) و تتا (Theta) پوزیشن.
    """

    @classmethod
    def _assess_risk_level(cls, opp: Opportunity) -> RiskLevel:
        """تعیین سطح ریسک واقعی با استفاده از ساختار سیستم بازگشتی Enum"""
        metadata = opp.metadata
        is_uncapped_loss = metadata.get('is_uncapped_loss', False)
        
        if is_uncapped_loss or opp.max_loss == float('inf') or opp.max_loss < -50000000:
            return RiskLevel.HIGH

        # استخراج ایمن required_margin — در صورتی که به اشتباه MarginResult باشد، float می‌گیریم
        required_margin = opp.required_margin
        if hasattr(required_margin, 'required_margin'):
            required_margin = float(required_margin.required_margin)
        else:
            try:
                required_margin = float(required_margin)
            except (TypeError, ValueError):
                required_margin = 0.0

        if required_margin > 0:
            loss_to_margin_ratio = abs(opp.max_loss) / required_margin
            if loss_to_margin_ratio > 0.8:
                return RiskLevel.HIGH
            if loss_to_margin_ratio < 0.2:
                return RiskLevel.LOW
                
        if opp.profile_scores.conservative > 75:
            return RiskLevel.LOW
        elif opp.profile_scores.aggressive > 75:
            return RiskLevel.HIGH
            
        return RiskLevel.MEDIUM