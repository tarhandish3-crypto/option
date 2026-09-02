# -*- coding: utf-8 -*-
"""
Generate PNG payoff icons for option strategies.

Each icon is rendered as a compact payoff/profit-loss diagram
at expiration without labels or grid lines.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


# =========================================================================
# General configuration
# =========================================================================

ICON_SIZE = 48
DPI = 72

SPOT_PRICE = 100.0
PRICE_MIN = 50.0
PRICE_MAX = 150.0
PRICE_POINTS = 401

BACKGROUND_COLOR = "none"

SHOW_BREAK_EVEN_MARKERS = False


# =========================================================================
# Icon appearance
# =========================================================================

PAYOFF_LINE_WIDTH = 2.4
AXIS_LINE_WIDTH = 0.65

AXIS_COLOR = "#7D8590"
AXIS_ALPHA = 0.45

PAYOFF_FILL_ALPHA_POSITIVE = 0.09
PAYOFF_FILL_ALPHA_NEGATIVE = 0.05

PLOT_LEFT = 0.10
PLOT_BOTTOM = 0.10
PLOT_WIDTH = 0.84
PLOT_HEIGHT = 0.84

X_MARGIN_RATIO = 0.03
Y_PADDING_RATIO = 0.16
MIN_Y_PADDING = 0.14


# =========================================================================
# Strategy colors
# =========================================================================

STRATEGY_COLORS = {
    "bullish": "#35D07F",
    "bearish": "#FF5C57",
    "neutral": "#A970FF",
    "volatility": "#4AA8FF",
    "arbitrage": "#F2B544",
}


# =========================================================================
# Option leg definition
# =========================================================================

@dataclass(frozen=True)
class OptionLeg:
    """
    Represents one stock or option position.
    """

    instrument: str
    position: int
    strike: float = 0.0
    premium: float = 0.0
    quantity: int = 1


# =========================================================================
# Payoff calculation functions
# =========================================================================

def stock_pnl(
    prices: np.ndarray,
    entry_price: float,
    position: int = 1,
    quantity: int = 1,
) -> np.ndarray:
    """
    Calculate stock profit/loss at expiration.
    """

    return (
        position
        * quantity
        * (prices - entry_price)
    )


def call_pnl(
    prices: np.ndarray,
    strike: float,
    premium: float,
    position: int = 1,
    quantity: int = 1,
) -> np.ndarray:
    """
    Calculate call option profit/loss at expiration.
    """

    intrinsic_value = np.maximum(
        prices - strike,
        0.0,
    )

    if position > 0:
        return quantity * (
            intrinsic_value - premium
        )

    return quantity * (
        premium - intrinsic_value
    )


def put_pnl(
    prices: np.ndarray,
    strike: float,
    premium: float,
    position: int = 1,
    quantity: int = 1,
) -> np.ndarray:
    """
    Calculate put option profit/loss at expiration.
    """

    intrinsic_value = np.maximum(
        strike - prices,
        0.0,
    )

    if position > 0:
        return quantity * (
            intrinsic_value - premium
        )

    return quantity * (
        premium - intrinsic_value
    )


def calculate_leg_pnl(
    prices: np.ndarray,
    leg: OptionLeg,
) -> np.ndarray:
    """
    Calculate profit/loss for a single strategy leg.
    """

    if leg.instrument == "stock":

        return stock_pnl(
            prices=prices,
            entry_price=leg.premium,
            position=leg.position,
            quantity=leg.quantity,
        )

    if leg.instrument == "call":

        return call_pnl(
            prices=prices,
            strike=leg.strike,
            premium=leg.premium,
            position=leg.position,
            quantity=leg.quantity,
        )

    if leg.instrument == "put":

        return put_pnl(
            prices=prices,
            strike=leg.strike,
            premium=leg.premium,
            position=leg.position,
            quantity=leg.quantity,
        )

    raise ValueError(
        f"Unsupported instrument type: {leg.instrument}"
    )


def calculate_strategy_pnl(
    prices: np.ndarray,
    legs: List[OptionLeg],
) -> np.ndarray:
    """
    Calculate total strategy profit/loss.
    """

    total_pnl = np.zeros_like(
        prices,
        dtype=float,
    )

    for leg in legs:

        total_pnl += calculate_leg_pnl(
            prices=prices,
            leg=leg,
        )

    return total_pnl


# =========================================================================
# Strategy definitions
# =========================================================================

def get_strategy_legs() -> Dict[str, List[OptionLeg]]:
    """
    Return all strategy legs.
    """

    return {

        # -----------------------------------------------------------------
        # Bullish strategies
        # -----------------------------------------------------------------

        "covered_call": [

            OptionLeg(
                instrument="stock",
                position=1,
                premium=100.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=4.0,
            ),
        ],

        "bull_call_spread": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=90.0,
                premium=13.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=5.0,
            ),
        ],

        "bull_put_spread": [

            OptionLeg(
                instrument="put",
                position=-1,
                strike=110.0,
                premium=12.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=90.0,
                premium=4.0,
            ),
        ],

        "long_call": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=100.0,
                premium=7.0,
            ),
        ],

        "short_put": [

            OptionLeg(
                instrument="put",
                position=-1,
                strike=100.0,
                premium=7.0,
            ),
        ],

        "collar": [

            OptionLeg(
                instrument="stock",
                position=1,
                premium=100.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=90.0,
                premium=4.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=4.0,
            ),
        ],

        "married_put": [

            OptionLeg(
                instrument="stock",
                position=1,
                premium=100.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=90.0,
                premium=4.0,
            ),
        ],


        # -----------------------------------------------------------------
        # Bearish strategies
        # -----------------------------------------------------------------

        "bear_put_spread": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=110.0,
                premium=13.0,
            ),

            OptionLeg(
                instrument="put",
                position=-1,
                strike=90.0,
                premium=5.0,
            ),
        ],

        "bear_call_spread": [

            OptionLeg(
                instrument="call",
                position=-1,
                strike=90.0,
                premium=12.0,
            ),

            OptionLeg(
                instrument="call",
                position=1,
                strike=110.0,
                premium=4.0,
            ),
        ],

        "long_put": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=100.0,
                premium=7.0,
            ),
        ],

        "short_call": [

            OptionLeg(
                instrument="call",
                position=-1,
                strike=100.0,
                premium=7.0,
            ),
        ],


        # -----------------------------------------------------------------
        # Neutral strategies
        # -----------------------------------------------------------------

        "iron_condor": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=80.0,
                premium=2.0,
            ),

            OptionLeg(
                instrument="put",
                position=-1,
                strike=90.0,
                premium=5.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=5.0,
            ),

            OptionLeg(
                instrument="call",
                position=1,
                strike=120.0,
                premium=2.0,
            ),
        ],

        "iron_butterfly": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=80.0,
                premium=3.0,
            ),

            OptionLeg(
                instrument="put",
                position=-1,
                strike=100.0,
                premium=8.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=100.0,
                premium=8.0,
            ),

            OptionLeg(
                instrument="call",
                position=1,
                strike=120.0,
                premium=3.0,
            ),
        ],

        "short_straddle": [

            OptionLeg(
                instrument="call",
                position=-1,
                strike=100.0,
                premium=7.0,
            ),

            OptionLeg(
                instrument="put",
                position=-1,
                strike=100.0,
                premium=7.0,
            ),
        ],

        "short_strangle": [

            OptionLeg(
                instrument="put",
                position=-1,
                strike=90.0,
                premium=4.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=4.0,
            ),
        ],


        # -----------------------------------------------------------------
        # Volatility strategies
        # -----------------------------------------------------------------

        "strap": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=100.0,
                premium=6.0,
                quantity=1,
            ),

            OptionLeg(
                instrument="call",
                position=1,
                strike=100.0,
                premium=6.0,
                quantity=2,
            ),
        ],

        "strip": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=100.0,
                premium=6.0,
                quantity=1,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=100.0,
                premium=6.0,
                quantity=2,
            ),
        ],

        "long_straddle": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=100.0,
                premium=7.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=100.0,
                premium=7.0,
            ),
        ],

        "long_strangle": [

            OptionLeg(
                instrument="put",
                position=1,
                strike=90.0,
                premium=4.0,
            ),

            OptionLeg(
                instrument="call",
                position=1,
                strike=110.0,
                premium=4.0,
            ),
        ],

        "long_guts": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=90.0,
                premium=11.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=110.0,
                premium=11.0,
            ),
        ],


        # -----------------------------------------------------------------
        # Arbitrage strategies
        # -----------------------------------------------------------------

        "conversion": [

            OptionLeg(
                instrument="stock",
                position=1,
                premium=100.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=100.0,
                premium=6.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=100.0,
                premium=6.0,
            ),
        ],

        "long_box": [

            OptionLeg(
                instrument="call",
                position=1,
                strike=90.0,
                premium=13.0,
            ),

            OptionLeg(
                instrument="put",
                position=1,
                strike=110.0,
                premium=13.0,
            ),

            OptionLeg(
                instrument="call",
                position=-1,
                strike=110.0,
                premium=5.0,
            ),

            OptionLeg(
                instrument="put",
                position=-1,
                strike=90.0,
                premium=5.0,
            ),
        ],
    }


# =========================================================================
# Strategy categories
# =========================================================================

def get_strategy_categories() -> Dict[str, str]:
    """
    Return visual category for each strategy.
    """

    return {

        "covered_call": "bullish",
        "bull_call_spread": "bullish",
        "bull_put_spread": "bullish",
        "long_call": "bullish",
        "short_put": "bullish",
        "collar": "bullish",
        "married_put": "bullish",

        "bear_put_spread": "bearish",
        "bear_call_spread": "bearish",
        "long_put": "bearish",
        "short_call": "bearish",

        "iron_condor": "neutral",
        "iron_butterfly": "neutral",
        "short_straddle": "neutral",
        "short_strangle": "neutral",

        "strap": "volatility",
        "strip": "volatility",
        "long_straddle": "volatility",
        "long_strangle": "volatility",
        "long_guts": "volatility",

        "conversion": "arbitrage",
        "long_box": "arbitrage",
    }


# =========================================================================
# Payoff normalization
# =========================================================================

def normalize_pnl(
    pnl: np.ndarray,
    minimum_range: float = 20.0,
) -> Tuple[np.ndarray, float]:
    """
    Normalize profit/loss while preserving payoff geometry.
    """

    max_abs = float(
        np.max(
            np.abs(pnl)
        )
    )

    scale = max(
        max_abs,
        minimum_range,
    )

    return pnl / scale, scale


def get_y_limits(
    normalized_pnl: np.ndarray,
) -> Tuple[float, float]:
    """
    Calculate balanced vertical limits.
    """

    minimum = float(
        np.min(
            normalized_pnl
        )
    )

    maximum = float(
        np.max(
            normalized_pnl
        )
    )

    payoff_range = (
        maximum - minimum
    )

    if payoff_range < 0.05:

        payoff_range = 0.05

    padding = max(
        payoff_range
        * Y_PADDING_RATIO,
        MIN_Y_PADDING,
    )

    lower = (
        minimum - padding
    )

    upper = (
        maximum + padding
    )

    lower = min(
        lower,
        -padding,
    )

    upper = max(
        upper,
        padding,
    )

    return lower, upper


# =========================================================================
# Break-even calculation
# =========================================================================

def find_break_even_points(
    prices: np.ndarray,
    pnl: np.ndarray,
) -> List[float]:
    """
    Find zero-crossing points using linear interpolation.
    """

    break_evens = []

    signs = np.sign(
        pnl
    )

    crossings = np.where(
        np.diff(signs) != 0
    )[0]

    for index in crossings:

        x1 = prices[index]
        x2 = prices[index + 1]

        y1 = pnl[index]
        y2 = pnl[index + 1]

        if np.isclose(
            y1,
            y2,
        ):
            continue

        break_even = (
            x1
            - y1
            * (x2 - x1)
            / (y2 - y1)
        )

        break_evens.append(
            float(break_even)
        )

    return break_evens


# =========================================================================
# Icon rendering
# =========================================================================

def create_strategy_icon(
    strategy_key: str,
    legs: List[OptionLeg],
    color: str,
    output_path: Path,
    size: int = ICON_SIZE,
) -> None:
    """
    Generate one strategy payoff icon.
    """

    prices = np.linspace(
        PRICE_MIN,
        PRICE_MAX,
        PRICE_POINTS,
    )

    pnl = calculate_strategy_pnl(
        prices=prices,
        legs=legs,
    )

    normalized_pnl, _ = normalize_pnl(
        pnl
    )

    y_min, y_max = get_y_limits(
        normalized_pnl
    )

    x_range = (
        PRICE_MAX - PRICE_MIN
    )

    x_padding = (
        x_range
        * X_MARGIN_RATIO
    )

    x_min = (
        PRICE_MIN
        - x_padding
    )

    x_max = (
        PRICE_MAX
        + x_padding
    )

    figure_size = (
        size / DPI
    )

    fig = plt.figure(
        figsize=(
            figure_size,
            figure_size,
        ),
        dpi=DPI,
        facecolor="none",
    )

    ax = fig.add_axes(
        [
            PLOT_LEFT,
            PLOT_BOTTOM,
            PLOT_WIDTH,
            PLOT_HEIGHT,
        ]
    )

    ax.set_facecolor(
        "none"
    )

    # ---------------------------------------------------------------------
    # Coordinate axes
    # ---------------------------------------------------------------------

    ax.annotate(
        "",
        xy=(
            x_max,
            0.0,
        ),
        xytext=(
            x_min,
            0.0,
        ),
        arrowprops={
            "arrowstyle": "-|>",
            "color": AXIS_COLOR,
            "lw": AXIS_LINE_WIDTH,
            "alpha": AXIS_ALPHA,
            "shrinkA": 0,
            "shrinkB": 0,
        },
        zorder=1,
    )

    ax.annotate(
        "",
        xy=(
            x_min,
            y_max,
        ),
        xytext=(
            x_min,
            y_min,
        ),
        arrowprops={
            "arrowstyle": "-|>",
            "color": AXIS_COLOR,
            "lw": AXIS_LINE_WIDTH,
            "alpha": AXIS_ALPHA,
            "shrinkA": 0,
            "shrinkB": 0,
        },
        zorder=1,
    )

    # ---------------------------------------------------------------------
    # Positive payoff area
    # ---------------------------------------------------------------------

    ax.fill_between(
        prices,
        normalized_pnl,
        0.0,
        where=normalized_pnl >= 0.0,
        interpolate=True,
        color=color,
        alpha=PAYOFF_FILL_ALPHA_POSITIVE,
        zorder=2,
    )

    # ---------------------------------------------------------------------
    # Negative payoff area
    # ---------------------------------------------------------------------

    ax.fill_between(
        prices,
        normalized_pnl,
        0.0,
        where=normalized_pnl < 0.0,
        interpolate=True,
        color=color,
        alpha=PAYOFF_FILL_ALPHA_NEGATIVE,
        zorder=2,
    )

    # ---------------------------------------------------------------------
    # Payoff curve
    # ---------------------------------------------------------------------

    ax.plot(
        prices,
        normalized_pnl,
        color=color,
        linewidth=PAYOFF_LINE_WIDTH,
        solid_capstyle="round",
        solid_joinstyle="round",
        antialiased=True,
        zorder=3,
    )

    # ---------------------------------------------------------------------
    # Optional break-even markers
    # ---------------------------------------------------------------------

    if SHOW_BREAK_EVEN_MARKERS:

        break_evens = (
            find_break_even_points(
                prices=prices,
                pnl=normalized_pnl,
            )
        )

        for break_even in break_evens:

            ax.plot(
                break_even,
                0.0,
                marker="o",
                markersize=1.8,
                markerfacecolor=BACKGROUND_COLOR,
                markeredgecolor=color,
                markeredgewidth=0.8,
                zorder=4,
            )

    # ---------------------------------------------------------------------
    # Final axis configuration
    # ---------------------------------------------------------------------

    ax.set_xlim(
        x_min,
        x_max,
    )

    ax.set_ylim(
        y_min,
        y_max,
    )

    ax.set_xticks([])
    ax.set_yticks([])

    for spine in ax.spines.values():

        spine.set_visible(
            False
        )

    fig.savefig(
        output_path
        / f"{strategy_key}.png",
        dpi=DPI,
        transparent=True,
        bbox_inches=None,
        pad_inches=0,
    )

    plt.close(
        fig
    )

    print(
        f"Created: {strategy_key}.png"
    )


# =========================================================================
# Batch generation
# =========================================================================

def generate_all_icons(
    output_dir: Path = None,
) -> None:
    """
    Generate all strategy payoff icons.
    """

    if output_dir is None:

        output_dir = (
            Path(__file__).parent
            / "strategies"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    strategy_legs = (
        get_strategy_legs()
    )

    strategy_categories = (
        get_strategy_categories()
    )

    for (
        strategy_key,
        legs,
    ) in strategy_legs.items():

        category = (
            strategy_categories[
                strategy_key
            ]
        )

        color = (
            STRATEGY_COLORS[
                category
            ]
        )

        create_strategy_icon(
            strategy_key=strategy_key,
            legs=legs,
            color=color,
            output_path=output_dir,
        )

    print(
        f"Generated {len(strategy_legs)} strategy icons."
    )


# =========================================================================
# Entry point
# =========================================================================

if __name__ == "__main__":

    generate_all_icons()