# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

"""
محاسبه‌گر P&L و غنی‌سازی فرصت‌ها
"""

import numpy as np
from numba import njit
from typing import List, Dict, Any, Optional

from config import get_price_steps, get_feature_flags, get_price_levels
from core.models import Opportunity, LegDefinition
from core.enums import Side, OptionType
from analytics.cost_calculator import IranMarketCostCalculator


@njit(cache=True)
def calc_pure_gross_payoff_numba(
        price_levels: np.ndarray,
        weights: np.ndarray,
        strikes: np.ndarray,
        entry_prices: np.ndarray,
        option_types: np.ndarray,
        sides: np.ndarray,
        contract_sizes: np.ndarray) -> np.ndarray:
    """
    تابع عددی محض - فقط سود ناخالص را محاسبه می‌کند
    """
    num_points = len(price_levels)
    num_legs = len(weights)
    gross_profits = np.zeros(num_points, dtype=np.float64)

    for i in range(num_points):
        S = price_levels[i]
        total_pnl = 0.0

        for j in range(num_legs):
            w = weights[j]
            side = sides[j]
            opt_type = option_types[j]
            K = strikes[j]
            entry_p = entry_prices[j]
            c_size = contract_sizes[j]

            if opt_type == 1:  # Call
                payoff = max(S - K, 0.0) if side == 1 else -max(S - K, 0.0)
                premium_pnl = (
                    payoff - entry_p) if side == 1 else (entry_p + payoff)
                total_pnl += w * premium_pnl * c_size

            elif opt_type == 2:  # Put
                payoff = max(K - S, 0.0) if side == 1 else -max(K - S, 0.0)
                premium_pnl = (
                    payoff - entry_p) if side == 1 else (entry_p + payoff)
                total_pnl += w * premium_pnl * c_size

            elif opt_type == 0:  # Stock
                stock_pnl = (S - entry_p) if side == 1 else (entry_p - S)
                total_pnl += w * stock_pnl * c_size

        gross_profits[i] = total_pnl

    return gross_profits


class IranMarketPayoffCalculator:
    """
    محاسبه‌گر P&L
    """

    @classmethod
    def calculate_strategy_payoff(
        cls,
        underlying_symbol: str,
        legs: List[LegDefinition],
        price_levels: np.ndarray,
        spot_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        محاسبه P&L یک استراتژی
        """
        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)

        for idx, leg in enumerate(legs):
            weights[idx] = abs(getattr(leg, 'weight', 1.0))
            sides[idx] = 1 if leg.side == Side.BUY else -1

            contract = getattr(leg, 'contract', None)
            if contract is not None:
                strikes[idx] = getattr(contract, 'strike_price', 0.0)
                entry_prices[idx] = getattr(leg, 'entry_price', None) or getattr(
                    contract, 'last_price', 0.0)
                # ✅ STOCK=0, CALL=1, PUT=2
                ot = leg.contract.option_type
                option_types[idx] = 1 if ot == OptionType.CALL else (
                    0 if ot == OptionType.STOCK else 2)
                contract_sizes[idx] = getattr(contract, 'contract_size')
            else:
                strikes[idx] = 0.0
                entry_prices[idx] = spot_price or 0.0
                option_types[idx] = 0
                contract_sizes[idx] = 1

        gross_profits = calc_pure_gross_payoff_numba(
            price_levels=price_levels,
            weights=weights,
            strikes=strikes,
            entry_prices=entry_prices,
            option_types=option_types,
            sides=sides,
            contract_sizes=contract_sizes
        )

        strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
            underlying_symbol=underlying_symbol,
            legs=legs,
            spot_price=spot_price
        )

        exercise_costs_vector = IranMarketCostCalculator.generate_exercise_cost_vector(
            underlying_symbol=underlying_symbol,
            legs=legs,
            price_levels=price_levels
        )

        # اعمال کارمزد فقط اگر feature flag فعال باشد
        flags = get_feature_flags()
        if flags.get("apply_commissions", True):
            net_profits_closed = gross_profits - strategy_costs.total_if_closed
            net_profits_exercised = gross_profits - \
                (exercise_costs_vector + strategy_costs.option_entry_fees +
                 strategy_costs.clearing_fees + strategy_costs.underlying_buy_fees)
        else:
            # بدون کارمزد: P&L ناخالص
            net_profits_closed = gross_profits.copy()
            net_profits_exercised = gross_profits.copy()
            strategy_costs.total_if_closed = 0.0
            strategy_costs.total_if_exercised = 0.0

        max_profit = float(np.max(net_profits_closed))
        max_loss = float(np.min(net_profits_closed))
        rr_ratio = max_profit / \
            abs(max_loss) if max_loss != 0 else float('inf')

        return {
            'price_levels': price_levels.tolist(),
            'gross_profits': gross_profits.tolist(),
            'net_profits_closed': net_profits_closed.tolist(),
            'net_profits_exercised': net_profits_exercised.tolist(),
            'max_profit': round(max_profit, 2),
            'max_loss': round(max_loss, 2),
            'risk_reward_ratio': round(rr_ratio, 2),
            'transaction_costs': strategy_costs.to_dict(),
        }


# ================================================================
# تابع Orchestration برای غنی‌سازی Opportunity
# ================================================================

def enrich_opportunity_with_pnl(
        opportunity: Opportunity,
        factor: float = 1.0,
        include_clearing: bool = True,
        include_exercise_tax: bool = True,
        profit_threshold: Optional[float] = None) -> Opportunity:
    """
    غنی‌سازی یک فرصت با محاسبات P&L

    Args:
        opportunity: شیء Opportunity خام
        factor: ضریب تبدیل (اختیاری)
        include_clearing: شامل کارمزد تسویه
        include_exercise_tax: شامل مالیات اعمال
        profit_threshold: آستانه سود

    Returns:
        Opportunity: شیء غنی‌شده با داده‌های P&L
    """

    S0_stock = getattr(opportunity, 'S0_stock')
    pct_steps = np.array(get_price_steps())
    price_levels = get_price_levels(S0_stock)

    result = IranMarketPayoffCalculator.calculate_strategy_payoff(
        underlying_symbol=opportunity.underlying_ticker,
        legs=opportunity.legs,
        price_levels=price_levels,
        spot_price=S0_stock)

    opportunity.max_profit = result['max_profit']
    opportunity.max_loss = result['max_loss']
    opportunity.risk_reward_ratio = result['risk_reward_ratio']

    net_profits = result.get('net_profits_closed', [])
    # محاسبه درصد سود نسبت به سرمایه اولیه (یا مارجین)
    if opportunity.required_margin > 0:
        returns_pct = [(p / opportunity.required_margin)
                       * 100 for p in net_profits]
    else:
        returns_pct = [(p / S0_stock) * 100 for p in net_profits]

    transaction_costs = result.get('transaction_costs', {})
    opportunity.metadata.update({
        'net_profits_closed': result['net_profits_closed'],
        'net_profits_exercised': result['net_profits_exercised'],
        'gross_profits': result['gross_profits'],
        'price_levels': result['price_levels'],
        'pct_steps': pct_steps.tolist(),
        'net_profits_closed': [float(x) for x in net_profits],
        'returns_monthly_pct': [float(x) for x in returns_pct],
        'transaction_costs': transaction_costs,
        'option_entry_fees': transaction_costs.get('option_entry_fees'),
        'option_exit_fees': transaction_costs.get('option_exit_fees'),
        'clearing_fees': transaction_costs.get('clearing_fees'),
        'underlying_buy_fees': transaction_costs.get('underlying_buy_fees'),
        'total_if_closed': transaction_costs.get('total_if_closed'),
        'total_if_exercised': transaction_costs.get('total_if_exercised'),
    })

    return opportunity
