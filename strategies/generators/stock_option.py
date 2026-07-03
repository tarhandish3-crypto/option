# strategies/generators/stock_option.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Any, Iterator, Tuple, Optional
from dataclasses import dataclass

from core.models import OptionContract, UnderlyingAsset, Opportunity
from core.enums import GeneratorType, Side, OptionType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.StockOption")


# ✅ استفاده از dataclass به همراه slots جهت حذف __dict__ و کاهش اورهد تخصیص حافظه در لوپ داغ
@dataclass(slots=True)
class OptionLegData:
    contract: OptionContract
    side: Side
    ratio: int
    entry_price: float


class StockOptionGenerator(BaseGenerator):
    """
    تولیدکننده نهایی، صنعتی و لایه Ultra-Low Latency برای استراتژی‌های ترکیبی سهم و اختیار.
    مجهز به تکنیک‌های Pre-binding، متغیرهای محلی رجیستری، الیکیشن بهینه با Dataclass Slots و اینلاین‌سازی فیلترها.
    """

    __slots__ = ('_strategy_name_lower', '_include_stock', '_cached_opt_type', '_cached_weight')

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.STOCK_OPTION:
            raise ValueError(f"{strategy_def.name} با StockOptionGenerator سازگار نیست.")

        if not getattr(strategy_def, "include_stock", True):
            raise ValueError(f"استراتژی {strategy_def.name} فاقد پرچم الزامی include_stock است.")

        if getattr(strategy_def, "legs_count", 1) > 2:
            raise ValueError("ساختار StockOptionGenerator حداکثر مجاز به مدیریت ۲ لگ است.")

        self._strategy_name_lower = strategy_def.name.lower().strip()
        self._include_stock = True
        
        # کش کردن الگو در فاز راه‌اندازی برای جلوگیری از پردازش O(k) در ترافیک زنده
        self._cached_opt_type, self._cached_weight = self._resolve_option_pattern()

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        """اسکن جریانی مطلق (True Streaming) با سرعت فرکانس بالا و تخصیص حافظه کنترل‌شده"""
        
        spot_price = self._get_S0_stock(underlying)
        if spot_price <= 0.0 or index.is_empty:
            return

        opt_type = self._cached_opt_type
        weight = self._cached_weight
        if opt_type is None:
            return

        # دریافت مستقیم کانتراکت‌های هدف بدون فیلترینگ پنهان ثانویه
        target_contracts = index.get_contracts_by_type(opt_type)
        if not target_contracts:
            return

        # کش کردن قوانین استراتژی در خارج از حلقه داغ
        rules = self.strategy_def.rules or {}
        strike_above_spot = rules.get("strike_above_spot", False)
        strike_below_spot = rules.get("strike_below_spot", False)
        min_liq_score = rules.get("min_liquidity_score", 30.0)

        option_side = Side.BUY if weight > 0 else Side.SELL
        abs_ratio = max(1, abs(int(weight)))

        # Pre-binding متدها جهت ارتقای سرعت کلاک مفسر پایتون
        get_score = contract_scores.get
        increment_generated = self.increment_generated
        create_opportunity = OpportunityBuilder.create_stock_option_opportunity

        # بهینه‌سازی لوپ اصلی کانتراکت‌ها (Hot-Loop Tuning)
        for contract in target_contracts:
            
            # کش کردن ویژگی‌های کانتراکت جهت حذف اورهد Attribute Lookup پایتون
            ticker = contract.ticker
            strike = contract.strike_price
            ask = contract.ask
            bid = contract.bid
            last_price = contract.last_price

            # خط دفاعی اول: فیلتر سریع نقدشوندگی بدون تخصیص حافظه
            if get_score(ticker, 0.0) < min_liq_score:
                continue

            # اینلاین‌سازی فیلترهای استرایک (حذف سربار ساخت Stack Frame توابع فرعی)
            if strike <= 0.0:
                continue

            # فیلترینگ Covered Call (کال‌های عمیقاً در سود ریجکت می‌شوند)
            if strike_above_spot and strike < (spot_price * 0.95):
                continue

            # فیلترینگ Married Put (پوت‌های نامتعارف ریجکت می‌شوند)
            if strike_below_spot and (strike < (spot_price * 0.85) or strike > (spot_price * 1.15)):
                continue

            # محاسبه قیمت ورود بر مبنای جهت معامله
            if option_side == Side.BUY:
                entry_price = ask if ask > 0.0 else last_price
            else:
                entry_price = bid if bid > 0.0 else last_price

            # استفاده از Dataclass بهینه شده با slots برای ترکیب خوانایی و پرفورمنس
            leg_data = OptionLegData(
                contract=contract,
                side=option_side,
                ratio=abs_ratio,
                entry_price=entry_price
            )

            opp = create_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                option_leg_data=leg_data,
                spot_price=spot_price,
                contract_scores=contract_scores
            )

            if opp is not None:
                increment_generated()
                yield opp

    # ============================================================
    # PRIVATE INITIALIZATION HELPERS
    # ============================================================

    def _resolve_option_pattern(self) -> Tuple[Optional[OptionType], float]:
        """استخراج مشخصات الگو در فاز کانستراکتور"""
        patterns = self.strategy_def.patterns
        if not patterns:
            return None, 0.0

        for p in patterns:
            if hasattr(p, 'option_type') and p.option_type != OptionType.STOCK:
                return p.option_type, float(p.weight)

        return None, 0.0