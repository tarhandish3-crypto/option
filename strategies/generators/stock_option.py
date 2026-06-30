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
                f"{strategy_def.name} با StockOptionGenerator سازگار نیست.")

        if not getattr(strategy_def, "include_stock", True):
            raise ValueError(
                f"استراتژی {strategy_def.name} فاقد پرچم الزامی include_stock است.")

        # legs_count برای covered_call ممکن است ۱ باشد (فقط CALL pattern، سهم implicit است)
        # بنابراین بررسی می‌کنیم بین ۱ تا ۲ لگ باشد
        lc = getattr(strategy_def, "legs_count", 1)
        if lc > 2:
            raise ValueError(
                f"StockOptionGenerator برای استراتژی‌های ۱ یا ۲ لگی است. "
                f"تعداد لگ‌های درخواستی: {lc}")

        logger.debug(
            f"StockOptionGenerator initialized for {strategy_def.name}")

    def generate(
            self,
            underlying: UnderlyingAsset,
            contracts: List[OptionContract],
            contract_scores: Dict[str, float],) -> List[Opportunity]:
        """
        اسکن هوشمند و ساخت فرصت‌های معاملاتی کاورکال و مریدپوت بر پایه قیمت پایانی/آخرین معامله.
        """
        opportunities: List[Opportunity] = []

        if not contracts:
            return opportunities

        # ۱. استخراج قیمت مبنای سهم
        spot_price = underlying.close_price or underlying.last_price or 0.0

        if spot_price <= 0:
            logger.warning(
                f"قیمت نامعتبر برای دارایی پایه {underlying.ticker}: {spot_price}")
            return opportunities

        # ۲. استخراج نوع اختیار و جهت از patterns
        opt_type, weight = self._resolve_option_pattern()

        if opt_type is None:
            logger.error(
                f"امکان استخراج نوع اختیار از patterns {self.strategy_def.name} وجود ندارد.")
            return opportunities

        rules = self.strategy_def.rules or {}
        seen_keys: Set[Tuple] = set()

        # ۳. ساخت یک stock_contract مجازی برای لگ سهم پایه
        # (is_stock_leg یک @property است که از option_type==STOCK استنتاج می‌شود)
        from core.models import OptionContract as OC
        stock_contract = OC(
            ticker=underlying.ticker,
            name=underlying.name,
            underlying_ticker=underlying.ticker,
            option_type=OptionType.STOCK,
            strike_price=spot_price,
            contract_size=1,
            last_price=spot_price,
            underlying_price=spot_price,
        )

        # ۴. پردازش قراردادهای اختیار
        for contract in contracts:
            if contract.option_type != opt_type:
                continue

            if not self._apply_strike_rules(contract, spot_price, rules):
                continue

            unique_key = (underlying.ticker, contract.ticker)
            if unique_key in seen_keys:
                continue
            seen_keys.add(unique_key)

            # لگ سهم پایه — option_type=STOCK → is_stock_leg=True (از property)
            stock_leg = LegDefinition(
                contract=stock_contract,
                side=Side.BUY,
                ratio=1,
                entry_price=spot_price,
            )

            # لگ اختیار
            option_side = Side.BUY if weight > 0 else Side.SELL
            ep = (contract.ask if contract.ask > 0 else contract.last_price) if option_side == Side.BUY \
                else (contract.bid if contract.bid > 0 else contract.last_price)
            option_leg = LegDefinition(
                contract=contract,
                side=option_side,
                ratio=max(1, abs(int(weight))),
                entry_price=ep,
            )

            legs = [stock_leg, option_leg]

            metadata = self._build_metadata(
                contract=contract,
                spot=spot_price,
                contract_scores=contract_scores,
            )

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

        logger.info("%s: %d stock-option opportunities generated",
                    self.strategy_def.name, len(opportunities))
        return opportunities

    # ---------------------------------------------------------
    # PRIVATE PRODUCTION HELPERS
    # ---------------------------------------------------------

    def _resolve_option_pattern(self) -> Tuple[Optional[OptionType], float]:
        """
        استخراج نوع اختیار و جهت از روی patterns استراتژی (StrategyLegPattern).
        """
        # ✅ patterns به جای weight_pattern که در StrategyDefinition وجود ندارد
        patterns = self.strategy_def.patterns
        if not patterns:
            return None, 0.0

        # پیدا کردن اولین لگ غیر-STOCK
        for p in patterns:
            if hasattr(p, 'option_type') and p.option_type != OptionType.STOCK:
                # weight = ratio با علامت (مثبت برای BUY، منفی برای SELL)
                weight = float(p.weight)  # property روی StrategyLegPattern
                # weight = float(p.ratio if p.side == Side.BUY else -p.ratio)
                return p.option_type, weight

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
