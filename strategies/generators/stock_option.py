# strategies/generators/stock_option.py
# -*- coding: utf-8 -*-

"""
تولیدکننده استراتژی‌های ترکیب سهم و اختیار (Stock + Option) متصل به کارخانه لایه پایه

پشتیبانی از:
    - Covered Call: خرید سهم + فروش Call
    - Married Put: خرید سهم + خرید Put
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
import logging

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from core.enums import Side, OptionType
from strategies.base import StrategyDefinition, GeneratorType
from strategies.generators.base import BaseGenerator

logger = logging.getLogger("OptionScanner.Strategies.Generators.StockOption")


class StockOptionGenerator(BaseGenerator):
    """
    تولیدکننده استراتژی‌های ترکیب سهم و اختیار هماهنگ با خط لوله غنی‌سازی هسته
    """

    DEFAULT_ATM_TOLERANCE_PCT = 0.05  # تلرانس ۵٪ برای استرایک‌های هم‌قیمت

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        assert strategy_def.generator_type == GeneratorType.STOCK_OPTION
        assert strategy_def.include_stock is True

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]
    ) -> List[Opportunity]:
        """تولید فرصت‌های ترکیب سهم و اختیار با ارجاع ساخت به لایه انتزاعی والد"""
        opportunities = []

        if not contracts:
            logger.debug(f"{self.strategy_def.name}: No contracts provided")
            return opportunities

        # ===== مرحله ۱: استخراج الگوی وزنی و تبدیل امن به انام سیستم =====
        option_leg_pattern = self.strategy_def.weight_pattern[0]
        opt_type = option_leg_pattern.option_type if hasattr(option_leg_pattern, 'option_type') else option_leg_pattern[0]
        weight = option_leg_pattern.weight if hasattr(option_leg_pattern, 'weight') else option_leg_pattern[1]

        if isinstance(opt_type, str):
            opt_str = opt_type.strip().lower()
            opt_type = OptionType.PUT if opt_str in ["put", "p"] else OptionType.CALL

        logger.debug(f"{self.strategy_def.name}: Looking for {opt_type.value} options with weight {weight}")

        # ===== مرحله ۲: فیلتر بر اساس نوع اختیار =====
        filtered_contracts = [c for c in contracts if c.option_type == opt_type]

        if not filtered_contracts:
            logger.debug(f"{self.strategy_def.name}: No {opt_type.value} contracts found")
            return opportunities

        # ===== مرحله ۳: گروه‌بندی بر اساس سررسید =====
        maturity_groups: Dict[int, List[OptionContract]] = {}
        for contract in filtered_contracts:
            maturity_groups.setdefault(contract.days_to_maturity, []).append(contract)

        if not maturity_groups:
            logger.debug(f"{self.strategy_def.name}: No maturity groups found")
            return opportunities

        # ===== مرحله ۴: پردازش هر گروه سررسید =====
        for days_to_maturity, group_contracts in maturity_groups.items():
            logger.debug(f"{self.strategy_def.name}: Processing {len(group_contracts)} contracts for {days_to_maturity} days")

            for contract in group_contracts:
                # ۴-الف: اعمال قوانین استرایک
                if not self._apply_strike_rules(contract, underlying):
                    continue

                # ۴-ب: ساخت لگ سهم پایه (خرید سهم)
                stock_leg = LegDefinition(
                    contract=None,  # مشخص‌کننده دارایی پایه در ساختار مدل‌ها
                    side=Side.BUY,
                    ratio=1
                )

                # ۴-ج: ساخت لگ اختیار معامله
                option_leg = LegDefinition(
                    contract=contract,
                    side=Side.BUY if weight > 0 else Side.SELL,
                    ratio=abs(int(weight))
                )

                legs = [stock_leg, option_leg]

                # ۴-د: غنی‌سازی متادیتای محلی و ارجاع تولید به متد کارخانه والد
                local_metadata = {
                    "volatility_signal": "منصفانه",
                    "stock_price": underlying.last_price,
                    "strike_price": contract.strike_price,
                    "option_type": contract.option_type.value,
                    "moneyness": self._calculate_moneyness(contract, underlying)
                }

                # استفاده از متد والد جهت یکپارچگی محاسبات و فیلدهای درصدی هسته سیستم
                opp = self._create_opportunity(
                    legs=legs,
                    underlying=underlying,
                    days_to_maturity=days_to_maturity,
                    contract_scores=contract_scores,
                    base_metadata=local_metadata
                )
                if opp:
                    opportunities.append(opp)

        logger.info(f"{self.strategy_def.name}: Generated {len(opportunities)} opportunities")
        return opportunities

    def _apply_strike_rules(self, contract: OptionContract, underlying: UnderlyingAsset) -> bool:
        """اعمال قوانین استرایک با انعطاف‌پذیری برای استراتژی‌های سهم-اختیار"""
        rules = self.strategy_def.rules
        spot = underlying.last_price
        strike = contract.strike_price

        if spot <= 0:
            return False

        diff_pct = (strike - spot) / spot

        # ===== قانون ۱: استرایک بالاتر از قیمت سهم (Covered Call) =====
        if rules.get("strike_above_spot", False):
            atm_tolerance = rules.get("atm_tolerance_pct", self.DEFAULT_ATM_TOLERANCE_PCT)
            if diff_pct < -atm_tolerance:
                return False
            return True

        # ===== قانون ۲: استرایک پایین‌تر از قیمت سهم (Married Put) =====
        if rules.get("strike_below_spot", False):
            atm_tolerance = rules.get("atm_tolerance_pct", self.DEFAULT_ATM_TOLERANCE_PCT)
            if diff_pct > atm_tolerance:
                return False
            return True

        return True

    def _calculate_moneyness(self, contract: OptionContract, underlying: UnderlyingAsset) -> str:
        """محاسبه وضعیت پول‌بودگی (Moneyness) قرارداد"""
        if underlying.last_price <= 0:
            return "Unknown"

        diff_pct = (contract.strike_price - underlying.last_price) / underlying.last_price
        atm_tolerance = self.DEFAULT_ATM_TOLERANCE_PCT

        if abs(diff_pct) <= atm_tolerance:
            return "ATM"
        elif contract.option_type == OptionType.CALL:
            return "ITM" if diff_pct < 0 else "OTM"
        else:  # PUT
            return "ITM" if diff_pct > 0 else "OTM"