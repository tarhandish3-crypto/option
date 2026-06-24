# analytics/cost_calculator.py
# -*- coding: utf-8 -*-

"""
محاسبه‌گر رسمی کارمزدها و هزینه‌های معاملاتی بازار اختیار معامله بورس ایران (TSE / IFB)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config import (
    COMMISSION_DICT,
    SYMBOL_INFO,
    EXERCISE_FEE_RATE,
    EXERCISE_TAX_RATE,
    DEFAULT_CONTRACT_SIZE,
    get_exercise_fee_rate,
    get_symbol_info,
    get_symbol_market,
    get_symbol_kind,
    get_commission_rate,
)
from core.models import LegDefinition
from core.enums import Side, OptionType


@dataclass(slots=True)
class StrategyCosts:
    """
    هزینه‌های تجمیعی یک استراتژی
    این کلاس صرفاً حامل داده‌های ساختاریافته کارمزدهاست و فاقد منطق سود و زیان ناخالص است.
    """
    option_entry_fees: float = 0.0
    option_exit_fees: float = 0.0

    option_exercise_fees: float = 0.0
    exercise_tax: float = 0.0

    underlying_buy_fees: float = 0.0
    underlying_sell_fees: float = 0.0

    clearing_fees: float = 0.0

    total_if_closed: float = 0.0      # سناریوی خروج قبل از سررسید (آفست نقدی)
    total_if_exercised: float = 0.0   # سناریوی نگهداری تا سررسید و اعمال فیزیکی

    breakdown: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, float]:
        """تبدیل ساختار دیتاکلاس به دیکشنری برای مصارف عمومی و لایه متادیتا"""
        return {
            'option_entry_fees': self.option_entry_fees,
            'option_exit_fees': self.option_exit_fees,
            'option_exercise_fees': self.option_exercise_fees,
            'exercise_tax': self.exercise_tax,
            'underlying_buy_fees': self.underlying_buy_fees,
            'underlying_sell_fees': self.underlying_sell_fees,
            'clearing_fees': self.clearing_fees,
            'total_if_closed': self.total_if_closed,
            'total_if_exercised': self.total_if_exercised,
        }


class IranMarketCostCalculator:
    """
    محاسبه‌گر متمرکز کارمزدهای بازار سرمایه ایران بر اساس تعرفه‌های سازمان بورس و سمات
    """

    EXERCISE_TAX_RATE = EXERCISE_TAX_RATE
    CLEARING_FEE_RATE = 0.0001  # نرخ ۰.۰۱٪ کارمزد تسویه
    CLEARING_FEE_MIN = 1000.0   # حداقل ۱,۰۰۰ تومان کف کارمزد تسویه برای هر موقعیت خرید

    @classmethod
    def _get_symbol_info(cls, underlying_symbol: str) -> Dict[str, Any]:
        return get_symbol_info(underlying_symbol) or {
            'Market': 'tse',
            'Kind': 'stock'
        }

    @classmethod
    def _get_market(cls, underlying_symbol: str) -> str:
        return get_symbol_market(underlying_symbol)

    @classmethod
    def _get_kind(cls, underlying_symbol: str) -> str:
        return get_symbol_kind(underlying_symbol)

    @classmethod
    def _get_commission_rate(cls, market: str, kind: str, is_buy: bool) -> float:
        return get_commission_rate(market, kind, is_buy)

    @classmethod
    def _get_exercise_rate(cls, market: str, kind: str) -> float:
        return get_exercise_fee_rate(market, kind)

    @classmethod
    def _calculate_leg_cost(
        cls,
        underlying_symbol: str,
        strike: float,
        entry_price: float,
        exit_price: float,
        quantity: float,  # ✅ پشتیبانی از وزن‌های کسری
        side: Side,
        option_type: Optional[OptionType],
        contract_size: int,
        include_clearing: bool = True,
        include_exercise_tax: bool = True
    ) -> Dict[str, Any]:
        """
        محاسبه هزینه‌های مجزا و جزئی یک لگ اختیار معامله
        """
        info = cls._get_symbol_info(underlying_symbol)
        market = info['Market']
        kind = info['Kind']

        # ✅ استفاده از quantity به عنوان float برای پشتیبانی از وزن‌های کسری
        entry_value = entry_price * contract_size * quantity
        exit_value = exit_price * contract_size * quantity
        strike_value = strike * contract_size * quantity

        # ۱. کارمزد ورود (باز کردن پوزیشن)
        entry_rate = cls._get_commission_rate(market, 'option', side == Side.BUY)
        entry_fee = entry_value * entry_rate

        # ۲. کارمزد خروج (بستن پوزیشن پیش از سررسید)
        exit_rate = cls._get_commission_rate(market, 'option', side != Side.BUY)
        exit_fee = exit_value * exit_rate

        # ۳. کارمزد اعمال در سررسید (تعرفه سمات بر اساس ارزش اعمال)
        exercise_rate = cls._get_exercise_rate(market, kind)
        exercise_fee = strike_value * exercise_rate

        # ۴. مالیات اعمال (۰.۵٪ ارزش اعمال فیزیکی - فقط بر عهده فروشنده سهم پایه)
        exercise_tax = 0.0
        if include_exercise_tax and option_type is not None:
            # در اختیار خرید (Call): فروشنده اختیار (Side.SELL) ملزم به فروش سهم است.
            # در اختیار فروش (Put): خریدار اختیار (Side.BUY) حق فروش سهم را دارد.
            if (option_type == OptionType.CALL and side == Side.SELL) or \
               (option_type == OptionType.PUT and side == Side.BUY):
                exercise_tax = strike_value * cls.EXERCISE_TAX_RATE

        # ۵. کارمزد تسویه اتاق پایاپای (فقط برای پوزیشن‌های خرید اختیار معامله)
        clearing_fee = 0.0
        if include_clearing and side == Side.BUY:
            clearing_fee = max(entry_value * cls.CLEARING_FEE_RATE, cls.CLEARING_FEE_MIN)

        # ۶. تجمیع مقادیر لگ
        total_if_closed = entry_fee + exit_fee + clearing_fee
        total_if_exercised = entry_fee + exercise_fee + clearing_fee + exercise_tax

        return {
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'exercise_fee': exercise_fee,
            'exercise_tax': exercise_tax,
            'clearing_fee': clearing_fee,
            'total_if_closed': total_if_closed,
            'total_if_exercised': total_if_exercised,
            'entry_value': entry_value,
            'exit_value': exit_value,
            'strike_value': strike_value,
            'market': market,
            'kind': kind,
            'quantity': quantity,  # ✅ ذخیره quantity برای استفاده در breakdown
        }

    @classmethod
    def _calculate_underlying_cost(
        cls,
        underlying_symbol: str,
        spot_price: float,
        quantity: float,  # ✅ پشتیبانی از وزن‌های کسری
        is_buy: bool
    ) -> Dict[str, float]:
        """محاسبه دقیق کارمزد خرید یا فروش سهام دارایی پایه"""
        market = cls._get_market(underlying_symbol)
        kind = cls._get_kind(underlying_symbol)
        total_value = spot_price * quantity

        rate = cls._get_commission_rate(market, kind, is_buy)
        fee = total_value * rate

        return {
            'fee': fee,
            'rate': rate,
            'total_value': total_value,
            'quantity': quantity,
        }

    @classmethod
    def calculate_strategy_costs(
        cls,
        underlying_symbol: str,
        legs: List[LegDefinition],
        spot_price: Optional[float] = None,
        include_clearing: bool = True,
        include_exercise_tax: bool = True
    ) -> StrategyCosts:
        """
        نقطه ورود اصلی: محاسبه تجمیعی و همه‌جانبه هزینه‌های کل استراتژی بر اساس لگ‌های فعال
        """
        total_entry = 0.0
        total_exit = 0.0
        total_exercise = 0.0
        total_tax = 0.0
        total_clearing = 0.0
        total_underlying_buy = 0.0
        total_underlying_sell = 0.0

        leg_breakdown = []
        has_option_legs = False
        total_contracts = 0.0  # ✅ نام دقیق‌تر با پشتیبانی از وزن‌های کسری

        # ۱. محاسبه پله‌ای هزینه‌های لگ‌های آپشن
        for leg in legs:
            contract = getattr(leg, 'contract', None)
            if contract is not None:
                has_option_legs = True

                quantity = abs(getattr(leg, 'weight', 1.0)) 
                total_contracts += quantity

                # contract_size = int(getattr(contract, 'contract_size', None) or DEFAULT_CONTRACT_SIZE)
                contract_size = leg.contract.contract_size
                strike = getattr(contract, 'strike_price')
                option_type = getattr(leg, 'option_type')

                entry_price = getattr(leg, 'entry_price')
                if entry_price is None:
                    entry_price = getattr(contract, 'last_price', 0.0)

                exit_price = getattr(contract, 'last_price', entry_price)

                leg_cost = cls._calculate_leg_cost(
                    underlying_symbol=underlying_symbol,
                    strike=strike,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=quantity,
                    side=leg.side,
                    option_type=option_type,
                    contract_size=contract_size,
                    include_clearing=include_clearing,
                    include_exercise_tax=include_exercise_tax
                )

                total_entry += leg_cost['entry_fee']
                total_exit += leg_cost['exit_fee']
                total_exercise += leg_cost['exercise_fee']
                total_tax += leg_cost['exercise_tax']
                total_clearing += leg_cost['clearing_fee']

                leg_breakdown.append(leg_cost)

        # ۲. محاسبه کارمزد دارایی پایه (✅ اصلاح: بر اساس contract_size واقعی)
        has_underlying = any(getattr(leg, 'is_stock_leg', False) for leg in legs)
        
        if has_underlying and spot_price is not None and spot_price > 0:
            # ✅ محاسبه دقیق حجم سهام بر اساس contract_size هر لگ
            total_underlying_quantity = 0.0
            for leg in legs:
                if getattr(leg, 'is_stock_leg', False):
                    quantity = abs(getattr(leg, 'weight', 1.0))
                    contract_size = getattr(leg, 'contract_size', 1)  # برای سهام پایه contract_size = 1
                    total_underlying_quantity += quantity * contract_size

            # اگر لگ سهام نداشتیم، از تعداد قراردادها استفاده کن
            if total_underlying_quantity <= 0 and has_option_legs:
                total_underlying_quantity = total_contracts * DEFAULT_CONTRACT_SIZE

            underlying_buy = cls._calculate_underlying_cost(
                underlying_symbol=underlying_symbol,
                spot_price=spot_price,
                quantity=total_underlying_quantity,
                is_buy=True
            )
            total_underlying_buy = underlying_buy['fee']

            underlying_sell = cls._calculate_underlying_cost(
                underlying_symbol=underlying_symbol,
                spot_price=spot_price,
                quantity=total_underlying_quantity,
                is_buy=False
            )
            total_underlying_sell = underlying_sell['fee']

        # ۳. جمع‌بندی نهایی سناریوهای کلان هزینه
        if not has_option_legs:
            total_if_closed = total_underlying_buy + total_underlying_sell
            total_if_exercised = total_if_closed
        else:
            total_if_closed = total_entry + total_exit + total_clearing + total_underlying_buy
            total_if_exercised = total_entry + total_exercise + total_clearing + total_tax + total_underlying_buy

        return StrategyCosts(
            option_entry_fees=round(total_entry, 2),
            option_exit_fees=round(total_exit, 2),
            option_exercise_fees=round(total_exercise, 2),
            exercise_tax=round(total_tax, 2),
            underlying_buy_fees=round(total_underlying_buy, 2),
            underlying_sell_fees=round(total_underlying_sell, 2),
            clearing_fees=round(total_clearing, 2),
            total_if_closed=round(total_if_closed, 2),
            total_if_exercised=round(total_if_exercised, 2),
            breakdown={
                'legs': leg_breakdown,
                'underlying': underlying_symbol,
                'has_option_legs': has_option_legs,
                'has_underlying': has_underlying,
                'total_contracts': total_contracts,
                'total_underlying_quantity': total_underlying_quantity if has_underlying else 0,
                'spot_price': spot_price,
                'include_clearing': include_clearing,
                'include_exercise_tax': include_exercise_tax,
            }
        )

    @classmethod
    def calculate_simple_costs(
        cls,
        underlying_symbol: str,
        premium: float,
        quantity: int,
        is_buy: bool,
        contract_size: int = 1000,
        include_clearing: bool = True
    ) -> Dict[str, float]:
        """محاسبه فوری و سبک کارمزد معامله منفرد"""
        market = cls._get_market(underlying_symbol)
        total_value = premium * contract_size * quantity

        entry_rate = cls._get_commission_rate(market, 'option', is_buy)
        entry_fee = total_value * entry_rate

        exit_rate = cls._get_commission_rate(market, 'option', not is_buy)
        exit_fee = total_value * exit_rate

        clearing_fee = 0.0
        if include_clearing and is_buy:
            clearing_fee = max(total_value * cls.CLEARING_FEE_RATE, cls.CLEARING_FEE_MIN)

        return {
            'entry_fee': round(entry_fee, 2),
            'exit_fee': round(exit_fee, 2),
            'clearing_fee': round(clearing_fee, 2),
            'total': round(entry_fee + exit_fee + clearing_fee, 2),
        }


# ================================================================
# تابع کمکی (Facade)
# ================================================================

def calculate_costs(
    underlying_symbol: str,
    legs: List[LegDefinition],
    spot_price: Optional[float] = None,
    include_clearing: bool = True,
    include_exercise_tax: bool = True
) -> StrategyCosts:
    """تابع کمکی (Facade) بیرونی جهت دسترسی روان و سریع سیستم به ماشین‌حساب کارمزدها"""
    return IranMarketCostCalculator.calculate_strategy_costs(
        underlying_symbol=underlying_symbol,
        legs=legs,
        spot_price=spot_price,
        include_clearing=include_clearing,
        include_exercise_tax=include_exercise_tax
    )