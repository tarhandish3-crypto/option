# strategies/generators/stock_option.py
# -*- coding: utf-8 -*-

"""
تولیدکننده جامع و جریانی استراتژی‌های ترکیب سهم و اختیار (Stock + Option Generator) بورس ایران.
مسئول اسکن، اعتبارسنجی و کپسوله‌سازی استراتژی‌های ترکیبی بدون وابستگی به ماژول‌های فرعی ناموجود.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Set, Tuple, Optional, Iterator

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
    تولیدکننده استاندارد و غیرانسدادی استراتژی‌های ترکیبی سهم و یک اختیار معامله (۲ لگی).
    خروجی به صورت جریانی (Iterator) مستقیماً روی مدل‌های اصلی پروژه ست شده است.
    """

    DEFAULT_ATM_TOLERANCE_PCT = 0.05  # تلرانس ۵٪ برای محدوده ATM

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.STOCK_OPTION:
            raise ValueError(f"{strategy_def.name} با StockOptionGenerator سازگار نیست.")

        if not getattr(strategy_def, "include_stock", True):
            raise ValueError(f"استراتژی {strategy_def.name} فاقد include_stock است.")

        lc = getattr(strategy_def, "legs_count", 1)
        if lc > 2:
            raise ValueError(
                f"StockOptionGenerator برای استراتژی‌های ۱ یا ۲ لگی است. "
                f"تعداد لگ‌های درخواستی: {lc}"
            )

        logger.debug(f"StockOptionGenerator initialized for {strategy_def.name}")

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]
    ) -> Iterator[Opportunity]:
        """
        اسکن جریانی کاندیداها و تولید تنبل فرصت‌ها (Yield) متناسب با ساختار اصلی پروژه.
        """
        if not contracts:
            return

        # ۱. استخراج قیمت مبنای سهم با متد Fallback کلاس پایه
        spot_price = self._get_S0_stock(underlying)

        if spot_price <= 0:
            logger.warning(f"قیمت نامعتبر برای دارایی پایه {underlying.ticker}: {spot_price}")
            return

        # ۲. استخراج نوع اختیار و جهت از patterns
        opt_type, weight = self._resolve_option_pattern()

        if opt_type is None:
            logger.error(f"امکان استخراج نوع اختیار از patterns {self.strategy_def.name} وجود ندارد.")
            return

        rules = self.strategy_def.rules or {}
        seen_keys: Set[Tuple] = set()

        # ۳. ساخت یک stock_contract مجازی برای لگ سهم پایه
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

        # ۴. پردازش جریانی و بدون انسداد حافظه
        for contract in contracts:
            if contract.option_type != opt_type:
                continue

            if not self._apply_strike_rules(contract, spot_price, rules):
                continue

            unique_key = (underlying.ticker, contract.ticker)
            if unique_key in seen_keys:
                continue
            seen_keys.add(unique_key)
            
            # شمارش در سیستم آمار لایه پایه
            self.increment_generated()

            # تنظیم لگ سهم پایه
            stock_leg = LegDefinition(
                contract=stock_contract,
                side=Side.BUY,
                ratio=1,
                entry_price=spot_price,
            )

            # تنظیم لگ اختیار معامله (خرید/فروش و قیمت ورود مبنا)
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

            # ادغام متادیتای اختصاصی با متادیتای ساختاری لایه پایه برنامه (_build_base_metadata)
            custom_metadata = self._build_metadata(
                contract=contract,
                spot=spot_price,
                contract_scores=contract_scores,
            )
            base_metadata = self._build_base_metadata(custom_metadata)

            # ساخت شیء نهایی با بیلدر اصلی سیستم
            opportunity = OpportunityBuilder.create_opportunity(
                strategy_name=self.strategy_def.name,
                ticker=underlying.ticker,
                legs=legs,
                metrics=base_metadata,
                days_to_maturity=contract.days_to_maturity,
                underlying_price=spot_price,
            )

            if opportunity is not None:
                yield opportunity

    # ---------------------------------------------------------
    # PRIVATE PRODUCTION HELPERS
    # ---------------------------------------------------------

    def _resolve_option_pattern(self) -> Tuple[Optional[OptionType], float]:
        """
        استخراج نوع اختیار و جهت از روی patterns استراتژی.
        """
        patterns = self.strategy_def.patterns
        if not patterns:
            return None, 0.0

        for p in patterns:
            if hasattr(p, 'option_type') and p.option_type != OptionType.STOCK:
                weight = float(p.weight)
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

        # Covered Call: فروش کارهایی که خیلی در سود (ITM عمیق) هستند توجیه ندارد چون سهم زود اعمال می‌شود.
        # بهینه‌ترین حالت بازار ایران: خرید سهم + فروش کال اوتی‌ام (OTM) یا نزدیک به مانی (ATM).
        if rules.get("strike_above_spot", False):
            if strike < (spot * 0.95):  # فیلتر کردن کال‌های عمیقاً در سود
                return False

        # Married Put: خرید اختیارهای فروشی که خیلی از سهم فاصله دارند (عمیقاً OTM یا ITM گران‌قیمت) فیلتر می‌شوند.
        if rules.get("strike_below_spot", False):
            if strike < (spot * 0.85) or strike > (spot * 1.15):
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
        غنی‌سازی متادیتا جهت مانیتورینگ آنلاین تابلوی آپشن.
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