# analytics/margin_calculator.py
# -*- coding: utf-8 -*-

"""
ماژول محاسبه وجه تضمین (Margin Required) و کال مارجین بر اساس ضوابط رسمی بورس ایران (سمات)

اصلاحات اعمال‌شده:
- تغییر نام OptionContract داخلی به MarginContract جهت رفع تداخل نام با core.models
- رفع باگ AttributeError در متد تبدیل لگ با ارجاع صحیح به leg.entry_price
- حفظ علامت پوزیشن (مثبت/منفی) در فیلد weight متناسب با Side
- استفاده از core.models.LegDefinition و core.enums بدون بازتعریف محلی
- تفکیک کامل لگ‌های سهام از لگ‌های آپشن برای جلوگیری از خطای استراتژی
- گرد کردن به مضرب ۱۰,۰۰۰ ریال (Ceil) طبق قوانین سمات
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union

from config import SYMBOL_INFO
from core.models import LegDefinition
from core.enums import OptionType, Side


# ============================================================================
# بخش ۱: مدل‌های داده داخلی
# ============================================================================

@dataclass
class MarginContract:
    """قرارداد آپشن بهینه‌شده صرفاً برای محاسبات داخلی مارجین"""
    strike_price: float
    option_type: OptionType
    contract_size: int = 1000
    last_price: float = 0.0
    days_to_maturity: int = 30


@dataclass(slots=True)
class MarginResult:
    """نتیجه کامل محاسبه وجه تضمین"""
    initial_margin: float
    required_margin: float
    strategy_type: str = "naked"
    is_covered: bool = False
    is_spread: bool = False
    net_premium: float = 0.0
    premium_effect: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)


# ============================================================================
# بخش ۲: ماشین‌حساب وجه تضمین
# ============================================================================

class MarginCalculator:
    """
    محاسبه‌گر وجه تضمین بر اساس فرمول رسمی سمات بورس ایران
    """

    ROUND_FACTOR = 10_000  # گرد کردن به مضرب ۱۰,۰۰۰ ریال

    # ضرایب استاندارد بورس ایران
    STOCK_A = 0.20
    STOCK_B = 0.10

    ETF_A = 0.15
    ETF_B = 0.075

    FIXED_INCOME_A = 0.04
    FIXED_INCOME_B = 0.02

    # ============================================================
    # بخش ۲-۱: توابع تبدیل و آماده‌سازی داده‌ها
    # ============================================================

    @classmethod
    def _convert_leg_to_internal(cls, leg: any) -> LegDefinition:
        """
        تبدیل موقعیت‌های ورودی (مدل مرجع یا دیکشنری) به LegDefinition استاندارد شده
        """
        # حالت اول: ورودی یک شیء (Object-based Leg) است
        if hasattr(leg, 'contract') and leg.contract:
            contract = leg.contract
            opt_type = getattr(contract, 'option_type', OptionType.CALL)
            
            # ساخت آبجکت قرارداد جدید با نام MarginContract
            margin_contract = MarginContract(
                strike_price=getattr(contract, 'strike_price', 0.0),
                option_type=opt_type,
                contract_size=getattr(contract, 'contract_size', 1000),
                last_price=getattr(contract, 'last_price', 0.0),
                days_to_maturity=getattr(contract, 'days_to_maturity', 30)
            )

            side = Side.BUY
            if hasattr(leg, 'side'):
                side = Side.BUY if leg.side == Side.BUY else Side.SELL
            elif hasattr(leg, 'weight') and leg.weight < 0:
                side = Side.SELL

            # تعیین دقیق ریشیو و وزن جهت جلوگیری از باگ عدم تطابق استراتژی
            ratio = abs(getattr(leg, 'ratio', getattr(leg, 'weight', 1)))
            weight = ratio * (-1 if side == Side.SELL else 1)
            entry_price = getattr(leg, 'entry_price', margin_contract.last_price)

            return LegDefinition(
                contract=margin_contract,
                side=side,
                entry_price=entry_price,
                weight=weight,
                ratio=ratio,
                is_stock_leg=getattr(leg, 'is_stock_leg', False)
            )
        
        # حالت دوم: ورودی دیکشنری است (Legacy / Test Cases)
        elif isinstance(leg, dict):
            opt_type = OptionType.CALL if leg.get('type', 1) == 1 or leg.get('option_type') == OptionType.CALL else OptionType.PUT
            
            margin_contract = MarginContract(
                strike_price=leg.get('strike', leg.get('strike_price', 0.0)),
                option_type=opt_type,
                contract_size=leg.get('contract_size', 1000),
                last_price=leg.get('premium', leg.get('last_price', 0.0)),
                days_to_maturity=leg.get('days_to_maturity', 30)
            )

            is_buy = leg.get('is_buy', True) if 'is_buy' in leg else (leg.get('side') == Side.BUY or leg.get('weight', 1) > 0)
            side = Side.BUY if is_buy else Side.SELL
            ratio = abs(leg.get('ratio', leg.get('weight', 1)))

            return LegDefinition(
                contract=margin_contract,
                side=side,
                entry_price=leg.get('entry_price', leg.get('premium', 0.0)),
                weight=ratio * (-1 if side == Side.SELL else 1),
                ratio=ratio,
                is_stock_leg=leg.get('is_stock_leg', False)
            )
        
        else:
            raise TypeError(f"نوع لگ ارسالی پشتیبانی نمی‌شود: {type(leg)}")

    @classmethod
    def _prepare_legs(cls, legs: List) -> List[LegDefinition]:
        """آماده‌سازی یکپارچه لِگ‌ها پیش از شروع محاسبات مارجین"""
        prepared_legs = []
        for leg in legs:
            prepared_legs.append(cls._convert_leg_to_internal(leg))
        return prepared_legs

    @classmethod
    def get_asset_type_from_symbol(cls, symbol: str) -> str:
        info = SYMBOL_INFO.get(symbol, {})
        kind = info.get('Kind', 'stock')

        kind_mapping = {
            'stock': 'stock',
            'etf-stock': 'etf',
            'etf-gold': 'etf',
            'etf-fix': 'etf-fix',
            'etf-mix': 'etf',
        }
        return kind_mapping.get(kind, 'stock')

    @classmethod
    def get_market_coefficients(cls, asset_type: Optional[str] = None) -> Tuple[float, float]:
        if asset_type == "etf-fix":
            return cls.FIXED_INCOME_A, cls.FIXED_INCOME_B
        elif asset_type == "etf":
            return cls.ETF_A, cls.ETF_B
        else:
            return cls.STOCK_A, cls.STOCK_B

    # ============================================================
    # بخش ۲-۲: اعتبارسنجی
    # ============================================================

    @classmethod
    def _validate_legs(cls, legs: List[LegDefinition]) -> None:
        if not legs:
            raise ValueError("لیست موقعیت‌ها خالی است")

        for i, leg in enumerate(legs):
            if leg.weight == 0:
                raise ValueError(f"وزن موقعیت {i+1} نمی‌تواند صفر باشد")
            
            if not leg.is_stock_leg and leg.contract.strike_price <= 0:
                raise ValueError(f"قیمت اعمال موقعیت {i+1} باید مثبت باشد: {leg.contract.strike_price}")
            
            if leg.entry_price < 0:
                raise ValueError(f"قیمت ورودی موقعیت {i+1} نمی‌تواند منفی باشد: {leg.entry_price}")

    # ============================================================
    # بخش ۲-۳: محاسبه مارجین تک قرارداد (Naked Short)
    # ============================================================

    @classmethod
    def calculate_contract_margin(
        cls,
        contract: MarginContract,
        underlying_price: float,
        asset_type: Optional[str] = None
    ) -> Dict[str, float]:
        if underlying_price <= 0:
            raise ValueError(f"قیمت دارایی پایه باید مثبت باشد: {underlying_price}")

        S = underlying_price
        K = contract.strike_price
        size = contract.contract_size
        premium = contract.last_price

        A, B = cls.get_market_coefficients(asset_type)

        if contract.option_type == OptionType.CALL:
            otm_per_unit = max(0.0, K - S)
        else:
            otm_per_unit = max(0.0, S - K)

        base_margin_per_unit = max((A * S) - otm_per_unit, B * K)
        base_margin_per_unit = max(base_margin_per_unit, 0.0)

        raw_base_margin = base_margin_per_unit * size
        initial_margin = math.ceil(raw_base_margin / cls.ROUND_FACTOR) * cls.ROUND_FACTOR

        premium_total = premium * size
        required_margin = initial_margin + premium_total

        return {
            "initial_margin": float(initial_margin),
            "required_margin": float(required_margin),
            "raw_base_margin": float(raw_base_margin),
            "base_margin_per_unit": float(base_margin_per_unit),
            "otm_per_unit": float(otm_per_unit)
        }

    # ============================================================
    # بخش ۲-۴: محاسبه مارجین اسپرد
    # ============================================================

    @classmethod
    def _calculate_spread_margin(
        cls,
        buy_leg: LegDefinition,
        sell_leg: LegDefinition,
        underlying_price: float,
        asset_type: Optional[str] = None
    ) -> Optional[MarginResult]:
        if buy_leg.contract.option_type != sell_leg.contract.option_type:
            return None

        if buy_leg.ratio != sell_leg.ratio:
            return None

        if buy_leg.contract.days_to_maturity < sell_leg.contract.days_to_maturity:
            return None

        size = sell_leg.contract.contract_size
        ratio = abs(sell_leg.weight)

        net_premium = (sell_leg.entry_price - buy_leg.entry_price) * size * ratio

        is_debit_call = (sell_leg.contract.option_type == OptionType.CALL and buy_leg.contract.strike_price < sell_leg.contract.strike_price)
        is_debit_put = (sell_leg.contract.option_type == OptionType.PUT and buy_leg.contract.strike_price > sell_leg.contract.strike_price)

        if is_debit_call or is_debit_put:
            return MarginResult(
                initial_margin=0.0,
                required_margin=0.0,
                strategy_type="debit_spread",
                is_spread=True,
                net_premium=net_premium,
                premium_effect=0.0
            )

        is_credit_call = (sell_leg.contract.option_type == OptionType.CALL and buy_leg.contract.strike_price > sell_leg.contract.strike_price)
        is_credit_put = (sell_leg.contract.option_type == OptionType.PUT and buy_leg.contract.strike_price < sell_leg.contract.strike_price)

        if is_credit_call or is_credit_put:
            spread_risk = abs(buy_leg.contract.strike_price - sell_leg.contract.strike_price) * size * ratio
            return MarginResult(
                initial_margin=spread_risk,
                required_margin=spread_risk,
                strategy_type="credit_spread",
                is_spread=True,
                net_premium=net_premium,
                premium_effect=-net_premium if net_premium > 0 else 0.0
            )

        return None

    # ============================================================
    # بخش ۲-۵: محاسبه مارجین فروش برهنه
    # ============================================================

    @classmethod
    def _calculate_naked_margin(
        cls,
        sell_legs: List[LegDefinition],
        underlying_price: float,
        asset_type: Optional[str] = None
    ) -> MarginResult:
        total_initial = 0.0
        total_required = 0.0
        breakdown = {}
        total_net_premium = 0.0

        for i, leg in enumerate(sell_legs):
            abs_weight = abs(leg.weight)
            margin_info = cls.calculate_contract_margin(
                contract=leg.contract,
                underlying_price=underlying_price,
                asset_type=asset_type
            )

            leg_initial = margin_info["initial_margin"] * abs_weight
            leg_required = margin_info["required_margin"] * abs_weight

            total_initial += leg_initial
            total_required += leg_required
            total_net_premium += leg.entry_price * leg.contract.contract_size * abs_weight

            breakdown[f"Leg_{i+1}"] = leg_initial

        return MarginResult(
            initial_margin=total_initial,
            required_margin=total_required,
            strategy_type="naked",
            is_spread=False,
            net_premium=total_net_premium,
            premium_effect=0.0,
            breakdown=breakdown
        )

    # ============================================================
    # بخش ۲-۶: محاسبه مارجین Iron Condor
    # ============================================================

    @classmethod
    def _calculate_iron_condor_margin(
        cls,
        legs: List[LegDefinition],
        underlying_price: float,
        asset_type: Optional[str] = None
    ) -> Optional[MarginResult]:
        if len(legs) != 4:
            return None

        sells = [l for l in legs if l.side == Side.SELL]
        buys = [l for l in legs if l.side == Side.BUY]

        if len(sells) != 2 or len(buys) != 2:
            return None

        call_sells = [l for l in sells if l.contract.option_type == OptionType.CALL]
        put_sells = [l for l in sells if l.contract.option_type == OptionType.PUT]
        call_buys = [l for l in buys if l.contract.option_type == OptionType.CALL]
        put_buys = [l for l in buys if l.contract.option_type == OptionType.PUT]

        if len(call_sells) != 1 or len(put_sells) != 1 or len(call_buys) != 1 or len(put_buys) != 1:
            return None

        call_sell, call_buy = call_sells[0], call_buys[0]
        put_sell, put_buy = put_sells[0], put_buys[0]

        if call_buy.contract.days_to_maturity < call_sell.contract.days_to_maturity:
            return None
        if put_buy.contract.days_to_maturity < put_sell.contract.days_to_maturity:
            return None

        if call_sell.contract.strike_price >= call_buy.contract.strike_price:
            return None
        if put_sell.contract.strike_price <= put_buy.contract.strike_price:
            return None

        size = call_sell.contract.contract_size
        ratio = abs(call_sell.weight)

        call_risk = (call_buy.contract.strike_price - call_sell.contract.strike_price) * size * ratio
        put_risk = (put_sell.contract.strike_price - put_buy.contract.strike_price) * size * ratio

        max_risk = max(call_risk, put_risk)

        net_premium = sum(
            (-leg.side.value) * leg.entry_price * leg.contract.contract_size * abs(leg.weight)
            for leg in legs
        )

        return MarginResult(
            initial_margin=max_risk,
            required_margin=max_risk,
            strategy_type="iron_condor",
            is_spread=True,
            net_premium=net_premium,
            premium_effect=-net_premium if net_premium > 0 else 0.0,
            breakdown={
                'call_spread_risk': call_risk,
                'put_spread_risk': put_risk,
                'max_risk': max_risk
            }
        )

    # ============================================================
    # بخش ۲-۷: محاسبه مارجین Butterfly
    # ============================================================

    @classmethod
    def _calculate_butterfly_margin(
        cls,
        legs: List[LegDefinition],
        underlying_price: float,
        asset_type: Optional[str] = None
    ) -> Optional[MarginResult]:
        if len(legs) != 3:
            return None

        weights = [leg.weight for leg in legs]
        if sorted(weights) != [-2, 1, 1]:
            return None

        sells = [l for l in legs if l.side == Side.SELL]
        buys = [l for l in legs if l.side == Side.BUY]

        if len(sells) != 1 or len(buys) != 2:
            return None

        sell_leg = sells[0]

        for buy_leg in buys:
            if buy_leg.contract.days_to_maturity < sell_leg.contract.days_to_maturity:
                return None

        strikes = sorted([l.contract.strike_price for l in legs])
        spread_width = (strikes[2] - strikes[0]) * sell_leg.contract.contract_size

        net_premium = sum(
            (-leg.side.value) * leg.entry_price * leg.contract.contract_size * abs(leg.weight)
            for leg in legs
        )

        return MarginResult(
            initial_margin=spread_width,
            required_margin=spread_width,
            strategy_type="butterfly",
            is_spread=True,
            net_premium=net_premium,
            premium_effect=-net_premium if net_premium > 0 else 0.0,
            breakdown={
                'spread_width': spread_width,
                'strikes': strikes
            }
        )

    # ============================================================
    # بخش ۲-۸: تابع هماهنگ‌کننده اصلی
    # ============================================================

    @classmethod
    def calculate_strategy_margin(
        cls,
        legs: List[Union[LegDefinition, Dict]],
        underlying_price: float,
        asset_type: Optional[str] = None,
        underlying_symbol: Optional[str] = None
    ) -> MarginResult:
        prepared_legs = cls._prepare_legs(legs)

        if underlying_symbol and asset_type is None:
            asset_type = cls.get_asset_type_from_symbol(underlying_symbol)

        if asset_type is None:
            asset_type = 'stock'

        cls._validate_legs(prepared_legs)

        stock_legs = [l for l in prepared_legs if l.is_stock_leg]
        option_legs = [l for l in prepared_legs if not l.is_stock_leg]

        buy_legs = [l for l in option_legs if l.side == Side.BUY]
        sell_legs = [l for l in option_legs if l.side == Side.SELL]

        if not sell_legs:
            net_premium = sum(
                (-l.side.value) * l.entry_price * l.contract.contract_size * abs(l.weight)
                for l in option_legs
            )
            return MarginResult(
                initial_margin=0.0,
                required_margin=0.0,
                strategy_type="long_only",
                is_covered=False,
                is_spread=False,
                net_premium=net_premium
            )

        if stock_legs:
            uncovered_sells = [l for l in sell_legs if l.contract.option_type != OptionType.CALL]
            if not uncovered_sells:
                net_premium = sum(
                    (-l.side.value) * l.entry_price * l.contract.contract_size * abs(l.weight)
                    for l in option_legs
                )
                return MarginResult(
                    initial_margin=0.0,
                    required_margin=0.0,
                    strategy_type="covered_call",
                    is_covered=True,
                    net_premium=net_premium
                )

        iron_condor = cls._calculate_iron_condor_margin(option_legs, underlying_price, asset_type)
        if iron_condor:
            return iron_condor

        butterfly = cls._calculate_butterfly_margin(option_legs, underlying_price, asset_type)
        if butterfly:
            return butterfly

        if len(buy_legs) == 1 and len(sell_legs) == 1:
            spread_result = cls._calculate_spread_margin(buy_legs[0], sell_legs[0], underlying_price, asset_type)
            if spread_result:
                return spread_result

        return cls._calculate_naked_margin(sell_legs, underlying_price, asset_type)

    # ============================================================
    # بخش ۲-۹: محاسبات مدیریت سرمایه
    # ============================================================

    @classmethod
    def calculate_required_capital(
        cls,
        legs: List[Union[LegDefinition, Dict]],
        underlying_price: float,
        asset_type: Optional[str] = None,
        underlying_symbol: Optional[str] = None,
        capital: float = 100_000_000
    ) -> Dict[str, float]:
        if underlying_symbol and asset_type is None:
            asset_type = cls.get_asset_type_from_symbol(underlying_symbol)

        result = cls.calculate_strategy_margin(legs, underlying_price, asset_type, underlying_symbol)
        prepared_legs = cls._prepare_legs(legs)

        total_cost = sum(
            l.entry_price * l.contract.contract_size * abs(l.weight)
            for l in prepared_legs
            if l.side == Side.BUY and not l.is_stock_leg
        )

        capital_required = result.required_margin + max(0.0, total_cost)

        return {
            'margin': result.initial_margin,
            'required_margin': result.required_margin,
            'total_cost': total_cost,
            'capital_required': capital_required,
            'free_capital': capital - capital_required,
            'margin_to_capital_ratio': (capital_required / capital) * 100 if capital > 0 else 0.0,
            'max_positions': int(capital / (capital_required + 1e-6)) if capital_required > 0 else 0,
            'strategy_type': result.strategy_type
        }