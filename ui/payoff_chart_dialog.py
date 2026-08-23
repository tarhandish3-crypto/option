# ui/payoff_chart_dialog.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any, Optional, List, Tuple, Dict
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QCheckBox, QSlider, QSizePolicy, 
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

# تنظیم Backend متناسب با PySide6
import matplotlib
try:
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from matplotlib.figure import Figure
import matplotlib.ticker as ticker

from ui import theme as ui_theme

# ─── اتصال مستقیم به لایه Analytics و Config ───
from config import FEATURE_FLAGS
from analytics.payoff_calculator import (
    IranMarketPayoffCalculator,
    calc_pure_gross_payoff_numba,
    calculate_initial_cash_flow_and_capital,
)
from analytics.cost_calculator import IranMarketCostCalculator
from core.enums import OptionType, Side
from core.models import LegDefinition

logger = logging.getLogger("OptionScanner.UI.PayoffDialog")


# =========================================================================
# توابع کمکی تبدیل ایمن داده‌ها
# =========================================================================

def _safe_to_list(val: Any) -> List[Any]:
    if val is None:
        return []
    if isinstance(val, np.ndarray):
        return val.flatten().tolist()
    if hasattr(val, "tolist"):
        try:
            return val.tolist()
        except Exception:
            pass
    if isinstance(val, (list, tuple)):
        return list(val)
    return [val]


def _safe_to_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if hasattr(val, "item"):
        try:
            return float(val.item())
        except Exception:
            pass
    if isinstance(val, (list, tuple, np.ndarray)):
        val_list = _safe_to_list(val)
        if len(val_list) > 0:
            try:
                return float(val_list[0])
            except Exception:
                return default
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# =========================================================================
# ویجت تولتیپ HUD مدرن (طراحی الهام‌گرفته از OptionBaaz)
# =========================================================================

class OptionBaazTooltipWidget(QFrame):
    """
    کارت شناور HUD روی نمودار با پشتیبانی ۱۰۰٪ نیتیو از تایپوگرافی فارسی
    و نمایش هوشمند وضعیت نقطه قیمت فعلی دارایی پایه
    """
    def __init__(self, parent: Optional[FigureCanvas] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 22, 28, 0.96);
                border: 1px solid #3b4252;
                border-radius: 8px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self.lbl_content = QLabel(self)
        self.lbl_content.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_content.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.lbl_content)

        self.hide()

    def update_data(
        self, 
        price: float, 
        price_change_pct: float, 
        pnl: float, 
        pnl_pct: Optional[float] = None,
        is_spot: bool = False
    ):
        pnl_color = "#3fb950" if pnl >= 0 else "#f85149"
        pnl_title = "سود خالص" if pnl >= 0 else "زیان خالص"
        pnl_sign = "+" if pnl > 0 else ""
        dev_sign = "+" if price_change_pct > 0 else ""
        
        dev_badge_bg = "rgba(63, 185, 80, 0.15)" if price_change_pct >= 0 else "rgba(248, 81, 73, 0.15)"
        dev_badge_color = "#3fb950" if price_change_pct >= 0 else "#f85149"

        pct_text = f" ({pnl_pct:+.1f}%)" if pnl_pct is not None else ""

        spot_badge = ""
        if is_spot:
            spot_badge = """
            <div style="background: rgba(243, 156, 18, 0.2); color: #f39c12; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px; margin-bottom: 4px; text-align: center; border: 1px solid rgba(243, 156, 18, 0.4);">
                📌 قیمت فعلی نماد پایه (Spot Price)
            </div>
            """

        price_title = "قیمت فعلی دارایی پایه:" if is_spot else "قیمت در سررسید:"

        html = f"""
        <div style="font-family: 'Vazirmatn', 'Segoe UI', Tahoma; min-width: 200px;">
            {spot_badge}
            <div style="border-bottom: 1px solid #2d333b; padding-bottom: 4px; margin-bottom: 5px;">
                <span style="color: #8c9bae; font-size: 11px;">{price_title}</span>
                <span style="color: #e6edf3; font-weight: bold; font-size: 12px; margin-right: 4px;">{price:,.0f} ریال</span>
                <span style="background: {dev_badge_bg}; color: {dev_badge_color}; font-size: 10px; font-weight: bold; padding: 1px 4px; border-radius: 3px;">
                    {dev_sign}{price_change_pct:.1f}%
                </span>
            </div>
            
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #8c9bae; font-size: 11px;">{pnl_title}:</span>
                <span style="color: {pnl_color}; font-weight: bold; font-size: 13px;">
                    {pnl_sign}{pnl:,.0f} ریال{pct_text}
                </span>
            </div>
        </div>
        """
        self.lbl_content.setText(html)
        self.adjustSize()


# =========================================================================
# کلاس اصلی دیالوگ رسم نمودار Payoff
# =========================================================================

class PayoffChartDialog(QDialog):
    """
    پنجره مستقل و فوق‌پیشرفته نمایش نمودار Payoff با تنظیمات کارمزد و تسویه فیزیکی
    و نمایش نقطه توپر قیمت فعلی سهم همراه با تولتیپ هوشمند
    """
    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("📊 تحلیل پیشرفته سود و زیان استراتژی (Payoff Explorer)")
        self.resize(1080, 720)
        self.setMinimumSize(920, 600)

        self.strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"

        self._prices_array: np.ndarray = np.array([])
        self._payoff_array: np.ndarray = np.array([])
        self._underlying_price: float = 0.0
        self._capital_base: float = 0.0
        self._current_span_pct: float = 50.0  # مقدار دیفالت بازه ۵۰٪±
        
        self._cursor_line = None
        self._cursor_dot = None
        self._spot_dot = None
        self.ax = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        # ── ۱. نوار هدر فوقانی (عنوان و نشانگرهای وضعیت) ──
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #161b22, stop:1 #0d1117);
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel("در حال بارگذاری استراتژی...")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        self.lbl_spot_info = QLabel("قیمت فعلی: -")
        self.lbl_spot_info.setStyleSheet("""
            background-color: rgba(243, 156, 18, 0.12);
            color: #f39c12;
            font-weight: bold;
            font-size: 11px;
            border: 1px solid rgba(243, 156, 18, 0.3);
            border-radius: 5px;
            padding: 3px 8px;
            margin-left: 6px;
        """)
        header_layout.addWidget(self.lbl_spot_info)

        self.lbl_be_points = QLabel("نقاط سربه‌سر: -")
        self.lbl_be_points.setStyleSheet("""
            background-color: rgba(210, 153, 34, 0.12);
            color: #e3b341;
            font-weight: bold;
            font-size: 11px;
            border: 1px solid rgba(210, 153, 34, 0.3);
            border-radius: 5px;
            padding: 3px 8px;
            margin-left: 6px;
        """)
        header_layout.addWidget(self.lbl_be_points)

        self.lbl_max_pnl = QLabel("حداکثر سود/ریسک: -")
        self.lbl_max_pnl.setStyleSheet("""
            background-color: rgba(63, 185, 80, 0.12);
            color: #3fb950;
            font-weight: bold;
            font-size: 11px;
            border: 1px solid rgba(63, 185, 80, 0.3);
            border-radius: 5px;
            padding: 3px 8px;
        """)
        header_layout.addWidget(self.lbl_max_pnl)

        layout.addWidget(header_frame)

        # ── ۲. نوار ابزار مدرن کنترل بازه قیمتی، کارمزد و تسویه فیزیکی ──
        control_frame = QFrame()
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 4px 10px;
            }
        """)
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(10)

        lbl_range_icon = QLabel("🔍 دامنه نوسان قیمت:")
        lbl_range_icon.setStyleSheet("font-weight: bold; color: #cdd9e5; font-size: 12px;")
        control_layout.addWidget(lbl_range_icon)

        # کشویی تنظیم درصد بازه (پیش‌فرض ۵۰٪)
        self.slider_range = QSlider(Qt.Orientation.Horizontal)
        self.slider_range.setRange(10, 100)
        self.slider_range.setValue(50)
        self.slider_range.setFixedWidth(180)
        self.slider_range.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 5px;
                background: #21262d;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #58a6ff);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #58a6ff;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #58a6ff;
                border: 2px solid #ffffff;
            }
        """)
        self.slider_range.valueChanged.connect(self._on_slider_range_changed)
        control_layout.addWidget(self.slider_range)

        # نشانگر درصد بازه انتخابی
        self.lbl_range_val = QLabel("±۵۰٪")
        self.lbl_range_val.setStyleSheet("""
            color: #58a6ff;
            font-weight: bold;
            font-size: 12px;
            min-width: 45px;
        """)
        control_layout.addWidget(self.lbl_range_val)

        # دکمه‌های بازه سریع
        for pct in (15, 30, 50, 100):
            btn_preset = QPushButton(f"±{pct}٪")
            btn_preset.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_preset.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    padding: 2px 7px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    color: #58a6ff;
                    border-color: #58a6ff;
                }
            """)
            btn_preset.clicked.connect(lambda checked=False, p=pct: self._set_range_preset(p))
            control_layout.addWidget(btn_preset)

        control_layout.addStretch()

        # چک‌باکس ۱: اعمال کارمزدهای بورس
        self.chk_apply_fees = QCheckBox("اعمال کارمزدهای بورس")
        self.chk_apply_fees.setChecked(True)
        self.chk_apply_fees.setStyleSheet("""
            QCheckBox { font-weight: bold; color: #e6edf3; margin-left: 10px; }
            QCheckBox::indicator { width: 15px; height: 15px; }
        """)
        self.chk_apply_fees.stateChanged.connect(self._on_fees_toggled)
        control_layout.addWidget(self.chk_apply_fees)

        # چک‌باکس ۲: تسویه فیزیکی
        default_is_physical = FEATURE_FLAGS.get("exercise_settlement_type", "PHYSICAL") == "PHYSICAL"
        self.chk_physical_settlement = QCheckBox("تسویه فیزیکی (مالیات واگذاری)")
        self.chk_physical_settlement.setChecked(default_is_physical)
        self.chk_physical_settlement.setToolTip("در صورت فعال بودن، مالیات ۰.۵٪ انتقال فیزیکی سهم در سررسید از واگذارکننده کسر می‌شود.")
        self.chk_physical_settlement.setStyleSheet("""
            QCheckBox { font-weight: bold; color: #79c0ff; }
            QCheckBox::indicator { width: 15px; height: 15px; }
        """)
        self.chk_physical_settlement.stateChanged.connect(self._on_fees_toggled)
        control_layout.addWidget(self.chk_physical_settlement)

        layout.addWidget(control_frame)

        # ── ۳. بوم رسم نمودار Matplotlib و تولتیپ OptionBaaz ──
        self.figure = Figure(figsize=(9, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        self.hud_tooltip = OptionBaazTooltipWidget(self.canvas)

        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect("axes_leave_event", self._on_mouse_leave)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

        # ── ۴. فوتر پایین: نام استراتژی، پایه‌ها و قیمت‌های خرید/فروش ──
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(5, 4, 5, 4)

        self.lbl_legs_summary = QLabel("پایه‌ها: در حال بارگذاری...")
        self.lbl_legs_summary.setStyleSheet("font-size: 12px; color: #adbac7; font-weight: 500;")
        self.lbl_legs_summary.setWordWrap(True)
        bottom_layout.addWidget(self.lbl_legs_summary, stretch=1)

        self.btn_close = QPushButton("بستن")
        self.btn_close.setFixedWidth(90)
        self.btn_close.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        layout.addWidget(bottom_frame)

    # =========================================================================
    # اسلات‌های کنترلی بازه و کارمزد
    # =========================================================================

    def _on_slider_range_changed(self, value: int):
        self._current_span_pct = float(value)
        self.lbl_range_val.setText(f"±{value}٪")
        if self.strategy:
            self._plot_payoff()

    def _set_range_preset(self, pct: int):
        self.slider_range.setValue(pct)

    def _on_fees_toggled(self):
        self.chk_physical_settlement.setEnabled(self.chk_apply_fees.isChecked())
        if self.strategy:
            self._plot_payoff()

    # =========================================================================
    # بارگذاری و رسم نمودار
    # =========================================================================

    def load_strategy(self, strategy: Any, theme_mode: ui_theme.ThemeMode = "dark") -> None:
        self.strategy = strategy
        self._theme_mode = theme_mode
        
        strat_name = str(getattr(strategy, 'strategy_name', 'استراتژی') or 'استراتژی')
        ticker_name = str(getattr(strategy, 'underlying_ticker', '-') or '-')
        self.lbl_title.setText(f"📈 نمودار سررسید استراتژی {strat_name} ({ticker_name})")

        legs_text = self._build_legs_summary_text(strategy)
        self.lbl_legs_summary.setText(f"📌 <b>استراتژی:</b> {strat_name} | <b>پایه‌ها:</b> {legs_text}")

        self._plot_payoff()

    def _build_legs_summary_text(self, strategy: Any) -> str:
        legs = _safe_to_list(getattr(strategy, 'legs', []))
        if not legs:
            return "اطلاعات پایه‌ها موجود نیست"

        parts = []
        for leg in legs:
            contract = getattr(leg, 'contract', None)
            ticker = contract.ticker if contract else getattr(strategy, 'underlying_ticker', 'سهام')
            side_fa = "خرید" if getattr(leg, 'side', Side.BUY) == Side.BUY else "فروش"
            ratio = int(_safe_to_float(getattr(leg, 'ratio', 1), 1.0))
            
            entry_price = getattr(leg, 'entry_price', None)
            if entry_price is None and contract:
                entry_price = getattr(contract, 'last_price', 0.0) or getattr(contract, 'close_price', 0.0)
            entry_price_str = f"@{ui_theme.format_rial(_safe_to_float(entry_price))} ریال" if entry_price else ""

            if contract:
                is_call = contract.option_type == OptionType.CALL
                opt_type = "اختیار خرید" if is_call else ("اختیار فروش" if contract.option_type == OptionType.PUT else "سهام پایه")
                strike_str = f"| اعمال: {ui_theme.format_rial(contract.strike_price)}" if contract.strike_price > 0 else ""
                parts.append(f"<b>{ticker}</b> ({ratio}× {side_fa} {opt_type} {entry_price_str} {strike_str})")
            else:
                parts.append(f"<b>{ticker}</b> ({ratio}× {side_fa} سهام پایه {entry_price_str})")

        return " ، ".join(parts)

    def _plot_payoff(self) -> None:
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)

        is_dark = (self._theme_mode == "dark")
        bg_color = "#1a1d24" if is_dark else "#ffffff"
        text_color = "#cdd9e5" if is_dark else "#24292e"
        grid_color = "#2d333b" if is_dark else "#e1e4e8"

        self.figure.patch.set_facecolor(bg_color)
        self.ax.set_facecolor(bg_color)

        legs: List[LegDefinition] = _safe_to_list(getattr(self.strategy, 'legs', []))
        if not legs:
            self.canvas.draw()
            return

        # ۱. استخراج نماد و قیمت دارایی پایه
        self._underlying_price = _safe_to_float(getattr(self.strategy, 'underlying_price', 0.0))
        metadata = getattr(self.strategy, 'metadata', {})
        if self._underlying_price <= 0 and isinstance(metadata, dict):
            self._underlying_price = _safe_to_float(metadata.get('underlying_price', 0.0))

        first_opt = next((l for l in legs if l.contract and l.contract.option_type != OptionType.STOCK), None)
        underlying_ticker = first_opt.contract.underlying_ticker if first_opt else getattr(self.strategy, 'underlying_ticker', '')

        # ۲. آماده‌سازی آرایه‌ها برای تابع Numba
        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)
        has_contract = np.zeros(num_legs, dtype=np.int32)

        base_option_size = 1000

        for idx, leg in enumerate(legs):
            weights[idx] = float(getattr(leg, 'ratio', 1.0))
            sides[idx] = 1 if getattr(leg, 'side', Side.BUY) == Side.BUY else -1
            contract = getattr(leg, 'contract', None)

            if contract is not None:
                strikes[idx] = float(getattr(contract, 'strike_price', 0.0) or 0.0)
                has_contract[idx] = 1

                if contract.option_type == OptionType.STOCK:
                    option_types[idx] = 0
                    contract_sizes[idx] = base_option_size
                elif contract.option_type == OptionType.CALL:
                    option_types[idx] = 1
                    contract_sizes[idx] = int(getattr(contract, 'contract_size', base_option_size) or base_option_size)
                else:
                    option_types[idx] = 2
                    contract_sizes[idx] = int(getattr(contract, 'contract_size', base_option_size) or base_option_size)

                ep = getattr(leg, 'entry_price', None)
                if ep and ep > 0:
                    entry_prices[idx] = ep
                else:
                    lp = getattr(contract, 'last_price', 0.0) or getattr(contract, 'close_price', 0.0)
                    entry_prices[idx] = lp if lp > 0 else (self._underlying_price if self._underlying_price > 0 else strikes[idx])
            else:
                ep = getattr(leg, 'entry_price', None)
                entry_prices[idx] = ep if (ep and ep > 0) else self._underlying_price
                option_types[idx] = 0
                contract_sizes[idx] = base_option_size
                has_contract[idx] = 1

        if self._underlying_price <= 0.0:
            valid_strikes = strikes[strikes > 0]
            self._underlying_price = float(valid_strikes[0]) if len(valid_strikes) > 0 else 10000.0

        # ۳. محاسبه بازه افقی X بر اساس مقدار کشویی (پیش‌فرض ±۵۰٪)
        span_ratio = self._current_span_pct / 100.0
        min_p = float(self._underlying_price * (1.0 - span_ratio))
        max_p = float(self._underlying_price * (1.0 + span_ratio))
        
        if min_p <= 0:
            min_p = 10.0

        self._prices_array = np.linspace(min_p, max_p, 500, dtype=np.float64)

        # ۴. محاسبه سود ناخالص از طریق تابع Numba
        gross_profits = calc_pure_gross_payoff_numba(
            self._prices_array, weights, strikes, entry_prices,
            option_types, sides, contract_sizes
        )

        net_profits = gross_profits.copy()
        apply_fees = self.chk_apply_fees.isChecked()
        is_physical = self.chk_physical_settlement.isChecked()
        option_entry_fees = 0.0

        # ۵. اعمال کارمزدها و تسویه فیزیکی/نقدی
        if apply_fees and underlying_ticker:
            try:
                costs = IranMarketCostCalculator.calculate_strategy_costs(
                    underlying_symbol=underlying_ticker,
                    legs=legs,
                    spot_price=self._underlying_price,
                    contract_sizes=contract_sizes
                )
                net_profits -= costs.total_entry_cost
                option_entry_fees = costs.total_entry_cost

                prev_settlement = FEATURE_FLAGS.get("exercise_settlement_type", "PHYSICAL")
                FEATURE_FLAGS["exercise_settlement_type"] = "PHYSICAL" if is_physical else "CASH"

                try:
                    exercise_costs = IranMarketCostCalculator.generate_exercise_cost_vector(
                        underlying_symbol=underlying_ticker,
                        legs=legs,
                        price_levels=self._prices_array,
                        include_exercise_fee=True
                    )
                    net_profits -= exercise_costs
                finally:
                    FEATURE_FLAGS["exercise_settlement_type"] = prev_settlement

            except Exception as e:
                logger.warning(f"Cost calculation error: {e}")

        self._payoff_array = net_profits

        # ۶. محاسبه سرمایه درگیر واقعی
        net_opt_prem, stock_inv = calculate_initial_cash_flow_and_capital(
            weights=weights,
            entry_prices=entry_prices,
            option_types=option_types,
            sides=sides,
            contract_sizes=contract_sizes,
            has_contract=has_contract
        )

        req_margin = _safe_to_float(getattr(self.strategy, 'required_margin', 0.0))
        if req_margin <= 0 and isinstance(metadata, dict):
            req_margin = _safe_to_float(metadata.get('required_margin', 0.0))

        self._capital_base = req_margin + net_opt_prem + stock_inv + option_entry_fees
        if self._capital_base <= 0:
            self._capital_base = 1.0

        # ۷. نقاط سربه‌سر و حداکثر سود/زیان
        be_points = IranMarketPayoffCalculator._find_break_even_points(self._prices_array, self._payoff_array)
        if len(be_points) > 0:
            be_str = " | ".join(ui_theme.format_rial(p) for p in be_points)
            self.lbl_be_points.setText(f"نقاط سربه‌سر: {be_str}")
        else:
            self.lbl_be_points.setText("نقاط سربه‌سر: -")

        max_profit_val = float(np.max(self._payoff_array))
        max_loss_val = float(np.min(self._payoff_array))
        self.lbl_max_pnl.setText(
            f"سود حداکثر: {ui_theme.format_rial(max_profit_val)} | ریسک: {ui_theme.format_rial(abs(max_loss_val))}"
        )

        # به‌روزرسانی هدر با قیمت فعلی
        if self._underlying_price > 0:
            spot_pnl = float(np.interp(self._underlying_price, self._prices_array, self._payoff_array))
            spot_pct = (spot_pnl / self._capital_base) * 100.0 if self._capital_base > 0 else 0.0
            self.lbl_spot_info.setText(f"قیمت فعلی: {self._underlying_price:,.0f} ({spot_pct:+.1f}٪)")

        # ۸. ترسیم المان‌های گرافیکی
        self.ax.axhline(0, color="#8c9bae", linestyle="--", linewidth=1.2, alpha=0.7)

        pos_mask = np.asarray(self._payoff_array >= 0.0, dtype=bool)
        neg_mask = np.asarray(self._payoff_array < 0.0, dtype=bool)

        self.ax.fill_between(self._prices_array, self._payoff_array, 0, where=pos_mask, color="#3fb950", alpha=0.25, interpolate=True)
        self.ax.fill_between(self._prices_array, self._payoff_array, 0, where=neg_mask, color="#f85149", alpha=0.25, interpolate=True)

        if apply_fees:
            fee_desc = "با کارمزد + تسویه فیزیکی" if is_physical else "با کارمزد + تسویه نقدی"
        else:
            fee_desc = "بدون کارمزد"

        # رسم خط اصلی Payoff
        self.ax.plot(self._prices_array, self._payoff_array, color="#58a6ff", linewidth=2.5, label=f"سود/زیان سررسید ({fee_desc})", zorder=4)

        # استرایک‌ها
        for k in sorted(list(set(strikes[strikes > 0]))):
            if min_p <= k <= max_p:
                self.ax.axvline(k, color="#805ad5", linestyle="--", linewidth=0.9, alpha=0.6)

        # ── نقطه توپر دائمی قیمت فعلی و خط‌چین عمودی ──
        if self._underlying_price > 0.0 and min_p <= self._underlying_price <= max_p:
            spot_pnl = float(np.interp(self._underlying_price, self._prices_array, self._payoff_array))
            
            # خط‌چین عمودی قیمت فعلی
            self.ax.axvline(
                self._underlying_price, 
                color="#f39c12", 
                linestyle=":", 
                linewidth=1.8, 
                alpha=0.85, 
                zorder=5,
                label=f"قیمت فعلی ({self._underlying_price:,.0f})"
            )

            # دایره توپر برجسته (Solid Dot)
            self._spot_dot = self.ax.scatter(
                [self._underlying_price], 
                [spot_pnl], 
                color="#f39c12", 
                edgecolors="#ffffff", 
                s=130, 
                linewidths=2.0, 
                zorder=7
            )

            # برچسب دائمی کنار نقطه قیمت فعلی
            spot_pct = (spot_pnl / self._capital_base) * 100.0 if self._capital_base > 0 else 0.0
            callout_text = f"Spot: {self._underlying_price:,.0f}\n({spot_pct:+.1f}%)"
            y_offset = 14 if spot_pnl >= 0 else -28
            self.ax.annotate(
                callout_text,
                xy=(self._underlying_price, spot_pnl),
                xytext=(0, y_offset),
                textcoords="offset points",
                ha='center',
                fontsize=9,
                fontweight='bold',
                color="#f39c12",
                bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec="#f39c12", lw=1.2, alpha=0.9),
                zorder=8
            )

        # مکان‌نما (Cursor)
        self._cursor_line = self.ax.axvline(self._prices_array[0], color="#a0aec0", linestyle="--", linewidth=1.0, alpha=0.8, visible=False)
        self._cursor_dot, = self.ax.plot([self._prices_array[0]], [0], marker="o", markersize=7, markeredgecolor="white", markeredgewidth=1.5, visible=False, zorder=9)

        self.ax.set_title("Expiration Payoff Curve", color=text_color, fontsize=12, fontweight="bold", pad=10)
        self.ax.set_xlabel("Underlying Price at Expiration (Rials)", color=text_color, fontsize=10, labelpad=8)
        self.ax.set_ylabel("Net Profit / Loss (Rials)", color=text_color, fontsize=10, labelpad=8)

        self.ax.grid(True, linestyle=":", color=grid_color, alpha=0.6)
        self.ax.tick_params(colors=text_color, labelsize=9)

        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))
        self.ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))

        self.ax.set_xlim(min_p, max_p)

        for spine in self.ax.spines.values():
            spine.set_color(grid_color)

        self.ax.legend(facecolor=bg_color, edgecolor=grid_color, labelcolor=text_color, loc="best")
        
        self.figure.tight_layout()
        self.canvas.draw()

    # =========================================================================
    # مدیریت تعاملی حرکت موس و کارت تولتیپ OptionBaaz
    # =========================================================================

    def _on_mouse_move(self, event) -> None:
        if event.inaxes != self.ax or len(self._prices_array) == 0:
            self._hide_tooltip()
            return

        x = event.xdata
        if x is None:
            self._hide_tooltip()
            return

        if x < self._prices_array[0] or x > self._prices_array[-1]:
            self._hide_tooltip()
            return

        # بررسی نزدیکی به قیمت فعلی (در شعاع ۱.۵٪ بازه قیمتی)
        price_span = self._prices_array[-1] - self._prices_array[0]
        spot_threshold = price_span * 0.015
        is_near_spot = False
        
        if self._underlying_price > 0 and abs(x - self._underlying_price) <= spot_threshold:
            # اسنپ روی قیمت دقیق دارایی پایه
            x_target = self._underlying_price
            is_near_spot = True
        else:
            x_target = x

        y = float(np.interp(x_target, self._prices_array, self._payoff_array))

        if self._underlying_price > 0:
            price_change_pct = ((x_target - self._underlying_price) / self._underlying_price) * 100.0
        else:
            price_change_pct = 0.0

        pnl_pct = (y / self._capital_base) * 100.0 if self._capital_base > 0 else None
        
        if is_near_spot:
            dot_color = "#f39c12"
            dot_size = 10
        else:
            dot_color = "#3fb950" if y >= 0 else "#f85149"
            dot_size = 7

        self._cursor_line.set_xdata([x_target, x_target])
        self._cursor_dot.set_data([x_target], [y])
        self._cursor_dot.set_color(dot_color)
        self._cursor_dot.set_markersize(dot_size)

        self.hud_tooltip.update_data(
            price=x_target, 
            price_change_pct=price_change_pct, 
            pnl=y, 
            pnl_pct=pnl_pct,
            is_spot=is_near_spot
        )

        canvas_h = self.canvas.height()
        canvas_w = self.canvas.width()
        
        mouse_x = int(event.x)
        mouse_y = int(canvas_h - event.y)

        tt_w = self.hud_tooltip.width()
        tt_h = self.hud_tooltip.height()

        pos_x = mouse_x + 15
        if pos_x + tt_w > canvas_w - 15:
            pos_x = mouse_x - tt_w - 15

        pos_y = mouse_y - (tt_h // 2)
        if pos_y < 10:
            pos_y = 10
        elif pos_y + tt_h > canvas_h - 10:
            pos_y = canvas_h - tt_h - 10

        self.hud_tooltip.move(pos_x, pos_y)
        self.hud_tooltip.show()

        self._cursor_line.set_visible(True)
        self._cursor_dot.set_visible(True)
        self.canvas.draw_idle()

    def _on_mouse_leave(self, event) -> None:
        self._hide_tooltip()

    def _hide_tooltip(self) -> None:
        if self.hud_tooltip.isVisible():
            self.hud_tooltip.hide()
        if self._cursor_line and self._cursor_line.get_visible():
            self._cursor_line.set_visible(False)
        if self._cursor_dot and self._cursor_dot.get_visible():
            self._cursor_dot.set_visible(False)
        self.canvas.draw_idle()