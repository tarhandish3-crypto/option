# strategies/generators/stock_option.py
# -*- coding: utf-8 -*-

"""
تولیدکننده جامع استراتژی‌های ترکیب سهم و اختیار (Stock + Option Generator) بورس ایران.
مسئول اسکن، اعتبارسنجی و کپسوله‌سازی استراتژی‌های ترکیبی دارایی پایه نظیر:
    - Covered Call (کاور کاله / کاور شده)
    - Married Put (بیمه سبد سهام با اختیار فروش)

کاملاً هماهنگ با دکترین معماری V4 و ساختار OpportunityBuilder.
نکته معماری: استراتژی‌های ۳ لگی مانند Collar (یقه) باید توسط ThreeLegGenerator پردازش شوند.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Set, Tuple, Optional

from core.models import (
    OptionContract,
    UnderlyingAsset,
    Opportunity,
    LegDefinition,
)
from core.enums import GeneratorType, Side, OptionType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.StockOption")


class StockOptionGenerator(BaseGenerator):
    """
    تولیدکننده استاندارد استراتژی‌های ترکیبی سهم و یک اختیار معامله (۲ لگی).
    """

    DEFAULT_ATM_TOLERANCE_PCT = 0.05  # تلرانس ۵٪ برای محدوده ATM

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.STOCK_OPTION:
            raise ValueError(
                f"{strategy_def.name} با StockOptionGenerator سازگار نیست."
            )

        if not getattr(strategy_def, "include_stock", True):
            raise ValueError(
                f"استراتژی {strategy_def.name} فاقد پرچم الزامی include_stock است."
            )

        # لگ سهام پایه ضمنی است (include_stock=True)، پس patterns فقط لگ‌های آپشنی را شامل می‌شود
        # covered_call: 1 لگ آپشن + سهام ضمنی = مجموع ۲ لگ واقعی
        # conversion: 2 لگ آپشن + سهام ضمنی = مجموع ۳ لگ واقعی
        option_legs_count = getattr(strategy_def, "legs_count", 1)
        if option_legs_count < 1 or option_legs_count > 3:
            raise ValueError(
                f"ژنراتور StockOptionGenerator از ۱ تا ۳ لگ آپشنی پشتیبانی می‌کند. "
                f"دریافت {option_legs_count} لگ."
            )

        logger.debug(
            f"StockOptionGenerator initialized for {strategy_def.name}")

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float],
    ) -> List[Opportunity]:
        """
        اسکن هوشمند و ساخت فرصت‌های معاملاتی کاورکال و مریدپوت بر پایه قیمت پایانی/آخرین معامله.
        """
        opportunities: List[Opportunity] = []

        if not contracts:
            return opportunities

        # ۱. استخراج امن قیمت مبنای سهم (اولویت با قیمت پایانی جهت جلوگیری از پرش‌های دیتا لایه صفر)
        spot_price = underlying.close_price or underlying.last_price or 0.0

        if spot_price <= 0:
            logger.warning(
                f"قیمت نامعتبر برای دارایی پایه {underlying.ticker}: {spot_price}"
            )
            return opportunities

        # ۲. استخراج هوشمند نوع اختیار از weight_pattern
        opt_type, weight = self._resolve_option_pattern()

        if opt_type is None:
            logger.error(
                f"امکان استخراج نوع اختیار از الگوی وزنی {self.strategy_def.name} وجود ندارد."
            )
            return opportunities

        rules = self.strategy_def.rules or {}
        seen_keys: Set[Tuple] = set()

        # ۳. پردازش قراردادها
        for contract in contracts:
            # فیلتر بر اساس نوع اختیار
            if contract.option_type != opt_type:
                continue

            # اعمال فیلترهای استرایک داینامیک بورس ایران
            if not self._apply_strike_rules(contract, spot_price, rules):
                continue

            # جلوگیری از تکرار
            unique_key = (underlying.ticker, contract.ticker, weight > 0)
            if unique_key in seen_keys:
                continue
            seen_keys.add(unique_key)

            # ۴. ساخت لگ‌های جفت استاندارد
            # لگ سهام پایه: ساخت OptionContract ضمنی با نوع STOCK
            stock_contract = OptionContract(
                ticker=underlying.ticker,
                name=underlying.name,
                underlying_ticker=underlying.ticker,
                option_type=OptionType.STOCK,
                strike_price=spot_price,
                contract_size=1,
                last_price=spot_price,
                close_price=spot_price,
                underlying_price=spot_price,
            )
            stock_leg = LegDefinition(
                contract=stock_contract,
                side=Side.BUY,
                ratio=1,
            )

            option_leg = LegDefinition(
                contract=contract,
                side=Side.BUY if weight > 0 else Side.SELL,
                ratio=abs(int(weight)) if abs(weight) > 0 else 1,
            )

            legs = [stock_leg, option_leg]

            # ۵. ساخت متادیتای غنی کانتراکت پایانی
            metadata = self._build_metadata(
                contract=contract,
                spot=spot_price,
                contract_scores=contract_scores
            )

            # ۶. ساخت فرصت نهایی از بیلدر کارخانه مرکزی V4
            opportunity = OpportunityBuilder.create_opportunity(
                strategy_name=self.strategy_def.name,
                ticker=underlying.ticker,
                legs=legs,
                metrics=metadata,
                days_to_maturity=contract.days_to_maturity,
                underlying_price=spot_price,
            )

            if opportunity is not None:
                opportunities.append(opportunity)

        logger.info(
            "%s: %d stock-option opportunities generated",
            self.strategy_def.name,
            len(opportunities),
        )

        return opportunities

    # ---------------------------------------------------------
    # PRIVATE PRODUCTION HELPERS
    # ---------------------------------------------------------

    def _resolve_option_pattern(self) -> Tuple[Optional[OptionType], float]:
        """
        استخراج امضا و وزن آپشن از روی weight_pattern با سازگاری همه‌جانبه ساختارهای V4.
        """
        patterns = self.strategy_def.patterns
        if not patterns:
            return None, 0.0

        target_pattern = patterns[0]

        # ساختار شی‌گرا (StrategyLegPattern)
        if hasattr(target_pattern, 'option_type'):
            opt_type = target_pattern.option_type
            weight = getattr(target_pattern, 'weight',
                             getattr(target_pattern, 'ratio', 1.0))
            return opt_type, float(weight)

        # ساختار توپل با انوم یا رشته متنی
        if isinstance(target_pattern, tuple) and len(target_pattern) >= 2:
            first = target_pattern[0]
            weight = float(target_pattern[1])

            if isinstance(first, OptionType):
                return first, weight

            if isinstance(first, str):
                opt_str = first.strip().lower()
                if opt_str in ["put", "p"]:
                    return OptionType.PUT, weight
                elif opt_str in ["call", "c"]:
                    return OptionType.CALL, weight

        # ساختار دیکشنری
        if isinstance(target_pattern, dict):
            opt_type = target_pattern.get('option_type')
            weight = float(target_pattern.get('weight', 1.0))
            if opt_type:
                return opt_type, weight

        return None, 0.0

    def _apply_strike_rules(
        self,
        contract: OptionContract,
        spot: float,
        rules: Dict[str, Any]
    ) -> bool:
        """
        اعمال شروط درصدی فواصل قیمت اعمال (Strike) جهت فیلترینگ کانتراکت‌های فاقد توجیه اقتصادی.
        """
        strike = contract.strike_price

        if strike <= 0 or spot <= 0:
            return False

        # Covered Call: جلوگیری از فروش کال‌های عمیقاً در سود یا زیان شدید (محدوده بهینه بازار ایران)
        if rules.get("strike_above_spot", False):
            min_strike = spot * 0.85
            if strike < min_strike:
                return False

        # Married Put: جلوگیری از خرید اختیارهای فروش گران‌قیمت خارج از ارزش زمانی
        if rules.get("strike_below_spot", False):
            max_strike = spot * 1.05
            if strike > max_strike:
                return False

        return True

    def _calculate_moneyness(self, contract: OptionContract, spot: float) -> str:
        """
        محاسبه ریاضی دقیق وضعیت پول‌بودگی بر مبنای تلرانس تعریف‌شده سهم پایه.
        """
        strike = contract.strike_price
        if strike <= 0 or spot <= 0:
            return "UNKNOWN"

        diff_pct = abs(strike - spot) / spot

        if diff_pct <= self.DEFAULT_ATM_TOLERANCE_PCT:
            return "ATM"

        if contract.option_type == OptionType.CALL:
            return "ITM" if strike < spot else "OTM"
        elif contract.option_type == OptionType.PUT:
            return "ITM" if strike > spot else "OTM"
        else:
            return "UNKNOWN"

    def _build_metadata(
        self,
        contract: OptionContract,
        spot: float,
        contract_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        غنی‌سازی متادیتا جهت مانیتورینگ آنلاین تابلوی آپشن و استفاده در لایه‌های فیلترینگ سمت فرانت.
        """
        return {
            "underlying_spot": spot,
            "underlying_ticker": contract.underlying_ticker or "",
            "option_ticker": contract.ticker,
            "strike_price": contract.strike_price,
            "days_to_maturity": contract.days_to_maturity,
            "option_type": contract.option_type.value if contract.option_type else "UNKNOWN",
            "moneyness": self._calculate_moneyness(contract, spot),
            "contract_score": contract_scores.get(contract.ticker, 0.0),
            "strike_to_spot_ratio": round(contract.strike_price / spot, 4) if spot > 0 else 0.0,
            "bid": contract.bid,
            "ask": contract.ask,
            "last_price": contract.last_price,
            "volume": contract.volume,
            "open_interest": contract.open_interest,
            "delta": contract.delta or 0.0,
            "gamma": contract.gamma or 0.0,
            "theta": contract.theta or 0.0,
            "vega": contract.vega or 0.0,
        }
