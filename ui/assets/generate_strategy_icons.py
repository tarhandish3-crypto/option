# -*- coding: utf-8 -*-
"""
تولید تصاویر PNG شماتیک نمودار سود/زیان برای 25 استراتژی
هر تصویر 48x48 پیکسل - فقط نمودار بدون متن
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# =========================================================================
# تعریف نمودارهای شماتیک برای هر استراتژی
# =========================================================================

STRATEGY_ICONS = {
    # صعودی (Bullish) - سبز
    "covered_call": {
        "points": [(0, -2), (3, 1), (5, 1), (10, 1)],  # خط صعودی سپس افقی (سقف)
        "color": "#3fb950",
        "fill": True
    },
    "bull_call_spread": {
        "points": [(0, -2), (2, 0), (4, 1.5), (8, 1.5), (10, 0)],  # تپه محدود
        "color": "#3fb950",
        "fill": True
    },
    "bull_put_spread": {
        "points": [(0, 0), (1, 0.5), (4, 1.5), (8, 1.5), (10, 1)],  # صعودی تدریجی
        "color": "#3fb950",
        "fill": True
    },
    "long_call": {
        "points": [(0, -2), (2, -2), (5, 0), (10, 3)],  # L معکوس صعودی تند
        "color": "#3fb950",
        "fill": True
    },
    "short_put": {
        "points": [(0, 1), (5, 1), (8, -1), (10, -3)],  # افقی سپس ریزش
        "color": "#3fb950",
        "fill": False
    },
    "collar": {
        "points": [(0, -2), (2, 0), (4, 1), (6, 1), (8, 0.5), (10, -1)],  # محدود از دو طرف
        "color": "#3fb950",
        "fill": True
    },
    "married_put": {
        "points": [(0, -2), (1, -2), (3, 0), (8, 2), (10, 3)],  # صعودی عادی
        "color": "#3fb950",
        "fill": True
    },

    # نزولی (Bearish) - قرمز
    "bear_put_spread": {
        "points": [(0, 1), (2, 0.5), (5, -1), (8, -1.5), (10, -1)],  # نزولی محدود
        "color": "#f85149",
        "fill": True
    },
    "bear_call_spread": {
        "points": [(0, 0), (2, -0.5), (5, -1.5), (8, -1.5), (10, -0.5)],  # نزولی محدود
        "color": "#f85149",
        "fill": True
    },
    "long_put": {
        "points": [(0, 3), (2, 3), (5, 0), (10, -3)],  # L نزولی تند
        "color": "#f85149",
        "fill": True
    },
    "short_call": {
        "points": [(0, 0), (5, 0), (8, -1), (10, -3)],  # افقی سپس ریزش
        "color": "#f85149",
        "fill": False
    },

    # خنثی (Neutral) - بنفش
    "iron_condor": {
        "points": [(0, -1), (1.5, 0.5), (3, 1.5), (5, 1.5), (7, 1.5), (8.5, 0.5), (10, -1)],  # دو تپه
        "color": "#8a2be2",
        "fill": True
    },
    "iron_butterfly": {
        "points": [(0, -1), (2, 0), (4, 1.5), (5, 1.5), (6, 1.5), (8, 0), (10, -1)],  # یک تپه
        "color": "#8a2be2",
        "fill": True
    },
    "short_straddle": {
        "points": [(0, 1), (2, 0), (5, -1.5), (8, 0), (10, 1)],  # V معکوس
        "color": "#8a2be2",
        "fill": False
    },
    "short_strangle": {
        "points": [(0, 0.5), (2, 0), (5, -1), (8, 0), (10, 0.5)],  # V معکوس پهن‌تر
        "color": "#8a2be2",
        "fill": False
    },

    # نوسانی (Volatility) - آبی
    "strap": {
        "points": [(0, -1), (2, 0), (4, 0.5), (5, 1.5), (6, 0.5), (8, 0), (10, -1)],  # V با تعصب بالایی
        "color": "#58a6ff",
        "fill": True
    },
    "strip": {
        "points": [(0, -0.5), (2, 0), (4, 0), (5, 1), (6, 0), (8, 0), (10, -1.5)],  # V با تعصب پایینی
        "color": "#58a6ff",
        "fill": True
    },
    "long_straddle": {
        "points": [(0, 1), (2, 0), (4, -0.5), (5, -1.5), (6, -0.5), (8, 0), (10, 1)],  # V متقارن
        "color": "#58a6ff",
        "fill": True
    },
    "long_strangle": {
        "points": [(0, 0.5), (2, 0), (4, -0.5), (5, -1), (6, -0.5), (8, 0), (10, 0.5)],  # V پهن
        "color": "#58a6ff",
        "fill": True
    },
    "long_guts": {
        "points": [(0, 0.2), (2, 0), (4, -0.3), (5, -1), (6, -0.3), (8, 0), (10, 0.2)],  # V باریک
        "color": "#58a6ff",
        "fill": True
    },

    # آربیتراژ (Arbitrage) - طلایی
    "conversion": {
        "points": [(0, 0), (5, 0), (10, 0)],  # خط مستقیم افقی
        "color": "#f39c12",
        "fill": False
    },
    "long_box": {
        "points": [(0, 0.5), (5, 0.5), (10, 0.5)],  # خط افقی ثابت
        "color": "#f39c12",
        "fill": False
    },
}


def create_strategy_icon(strategy_key: str, icon_data: dict, output_path: Path, size: int = 48) -> None:
    """
    ایجاد تصویر PNG شماتیک برای یک استراتژی
    """
    fig, ax = plt.subplots(figsize=(size/100, size/100), dpi=100)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # داده‌های نمودار
    points = icon_data["points"]
    x_vals = [p[0] for p in points]
    y_vals = [p[1] for p in points]
    color = icon_data["color"]
    fill = icon_data.get("fill", True)

    # رسم نمودار
    ax.plot(x_vals, y_vals, color=color, linewidth=2.5, solid_capstyle='round', solid_joinstyle='round')

    # پر کردن زیر نمودار
    if fill:
        ax.fill_between(x_vals, y_vals, 0, color=color, alpha=0.3)

    # خط افقی صفر (مبدا)
    ax.axhline(y=0, color='#666666', linestyle='-', linewidth=0.8, alpha=0.5)

    # تنظیمات محور
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-3.5, 3.5)
    ax.axis('off')  # مخفی کردن محورها
    ax.margins(0)

    # ذخیره‌سازی
    fig.savefig(output_path / f"{strategy_key}.png", 
                dpi=100, bbox_inches='tight', pad_inches=0, facecolor='white', edgecolor='none')
    plt.close(fig)

    print(f"✓ ایجاد شده: {strategy_key}.png")


def generate_all_icons(output_dir: Path = None) -> None:
    """
    تولید تمام تصاویر PNG شماتیک
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / "strategies"

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🎨 تولید تصاویر شماتیک استراتژی‌ها...")
    print(f"📁 مسیر ذخیره: {output_dir}\n")

    for strategy_key, icon_data in STRATEGY_ICONS.items():
        create_strategy_icon(strategy_key, icon_data, output_dir)

    print(f"\n✅ تولید {len(STRATEGY_ICONS)} تصویر PNG کامل شد!")


if __name__ == "__main__":
    generate_all_icons()
