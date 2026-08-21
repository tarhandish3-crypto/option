# ui/strategy_inspector.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List, Union

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QGroupBox, QTableWidget, QTableWidgetItem, QSlider, 
    QPushButton, QHeaderView, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QBrush, QFont

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.StrategyInspector")


class StrategyInspectorWidget(QGroupBox):
    """
    پنل اختصاصی تحلیل عمیق استراتژی‌های اختیار معامله
    شامل خلاصه مارجین، یونانی‌ها، جدول تفکیک پایه‌ها، شبیه‌ساز What-If و اکشن‌های سریع.
    """
    execute_requested = Signal(object)    # ارسال استراتژی به کارگزاری (Omex)
    send_bale_requested = Signal(object)  # ارسال استراتژی به پیام‌رسان بله

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("🔍 تحلیل عمیق و شبیه‌ساز استراتژی", parent)
        self.current_strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"
        
        self._init_ui()

    def _init_ui(self) -> None:
        """ساخت چیدمان بصری و المان‌های پنل Inspector"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 14, 10, 10)

        # اسکرول اریا برای پشتیبانی از مانیتورهای کوچک‌تر
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # ۱. هدر و عنوان استراتژی
        self.lbl_title = QLabel("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")
        self.lbl_title.setWordWrap(True)
        layout.addWidget(self.lbl_title)

        # ۲. کارت‌های متریک مالی (مارجین، سود/زیان، بازده و سربه‌سر)
        metrics_group = QGroupBox("خلاصه پارامترهای مالی و ریسک")
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setSpacing(6)

        self.lbl_margin = QLabel("وجه تضمین: -")
        self.lbl_roi = QLabel("بازده روی مارجین: -")
        self.lbl_max_profit = QLabel("حداکثر سود: -")
        self.lbl_max_loss = QLabel("حداکثر زیان: -")
        self.lbl_breakeven = QLabel("نقطه سربه‌سر: -")
        self.lbl_pop = QLabel("احتمال سود (PoP): -")

        # اعمال استایل اولیه
        self.lbl_margin.setStyleSheet("font-weight: bold; color: #d29922;")
        self.lbl_roi.setStyleSheet("font-weight: bold; color: #3fb950;")
        self.lbl_max_profit.setStyleSheet("color: #3fb950;")
        self.lbl_max_loss.setStyleSheet("color: #f85149;")

        metrics_layout.addWidget(self.lbl_margin, 0, 0)
        metrics_layout.addWidget(self.lbl_roi, 0, 1)
        metrics_layout.addWidget(self.lbl_max_profit, 1, 0)
        metrics_layout.addWidget(self.lbl_max_loss, 1, 1)
        metrics_layout.addWidget(self.lbl_breakeven, 2, 0)
        metrics_layout.addWidget(self.lbl_pop, 2, 1)

        layout.addWidget(metrics_group)

        # ۳. بخش پارامترهای یونانی (Greeks)
        greeks_group = QGroupBox("حساسیت‌های یونانی پورتفو (Option Greeks)")
        greeks_layout = QHBoxLayout(greeks_group)
        greeks_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_delta = QLabel("Δ دلتا: -")
        self.lbl_gamma = QLabel("Γ گاما: -")
        self.lbl_theta = QLabel("Θ تتا: -")
        self.lbl_vega = QLabel("ν وگا: -")

        for lbl in (self.lbl_delta, self.lbl_gamma, self.lbl_theta, self.lbl_vega):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-weight: bold; background-color: rgba(255,255,255,0.04); border-radius: 4px; padding: 4px;")
            greeks_layout.addWidget(lbl)

        layout.addWidget(greeks_group)

        # ۴. جدول پایه‌های معاملاتی (Legs Table)
        lbl_legs = QLabel("📌 پایه‌های معاملاتی (Legs Breakdown):")
        lbl_legs.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl_legs)

        self.legs_table = QTableWidget(0, 5)
        self.legs_table.setHorizontalHeaderLabels(["نوع", "قرارداد / سررسید", "قیمت ورود", "تعداد", "سمت"])
        self.legs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.legs_table.setFixedHeight(130)
        self.legs_table.setAlternatingRowColors(True)
        self.legs_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.legs_table)

        # ۵. شبیه‌ساز نوسان قیمت پایه (What-If Simulator)
        sim_group = QGroupBox("شبیه‌ساز سناریوهای نوسان دارایی پایه (What-If)")
        sim_layout = QVBoxLayout(sim_group)
        sim_layout.setSpacing(6)

        slider_box = QHBoxLayout()
        self.lbl_slider_min = QLabel("-۲۵%")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-25, 25)
        self.slider.setValue(0)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(5)
        self.slider.valueChanged.connect(self._on_slider_changed)
        
        self.lbl_slider_val = QLabel(" ۰% ")
        self.lbl_slider_val.setStyleSheet("font-weight: bold; min-width: 45px; color: #58a6ff;")
        self.lbl_slider_max = QLabel("+۲۵%")

        self.btn_reset_sim = QPushButton("🔄")
        self.btn_reset_sim.setToolTip("بازنشانی به قیمت فعلی (۰٪)")
        self.btn_reset_sim.setFixedWidth(28)
        self.btn_reset_sim.clicked.connect(lambda: self.slider.setValue(0))

        slider_box.addWidget(self.lbl_slider_min)
        slider_box.addWidget(self.slider)
        slider_box.addWidget(self.lbl_slider_max)
        slider_box.addWidget(self.lbl_slider_val)
        slider_box.addWidget(self.btn_reset_sim)
        sim_layout.addLayout(slider_box)

        # نمایش خروجی سود/زیان شبیه‌سازی‌شده
        self.lbl_sim_pnl = QLabel("سود/زیان برآورد در سررسید: ۰ ریال (۰.۰%)")
        self.lbl_sim_pnl.setStyleSheet("font-weight: bold; font-size: 12px; padding: 4px;")
        sim_layout.addWidget(self.lbl_sim_pnl)

        layout.addWidget(sim_group)

        # ۶. دکمه‌های عملیات سریع (Quick Execution & Sharing)
        action_layout = QHBoxLayout()
        
        self.btn_execute = QPushButton("⚡ ارسال مستقیم به کارگزاری")
        self.btn_execute.setStyleSheet("""
            QPushButton { 
                background-color: #238636; 
                color: white; 
                font-weight: bold; 
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_execute.clicked.connect(self._on_execute_clicked)
        action_layout.addWidget(self.btn_execute)

        self.btn_bale = QPushButton("📱 ارسال به بله")
        self.btn_bale.setStyleSheet("""
            QPushButton { 
                background-color: #7b2d8b; 
                color: white; 
                font-weight: bold; 
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #9b59b6; }
        """)
        self.btn_bale.clicked.connect(self._on_bale_clicked)
        action_layout.addWidget(self.btn_bale)

        layout.addLayout(action_layout)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def set_theme_mode(self, mode: ui_theme.ThemeMode) -> None:
        """بروزرسانی استایل پنل متناسب با تم فعال"""
        self._theme_mode = mode
        self.setStyleSheet(ui_theme.get_inspector_frame_style(mode))

    # =========================================================================
    # بارگذاری و استخراج داده‌های استراتژی
    # =========================================================================

    def load_strategy(self, strategy: Any) -> None:
        """بارگذاری کامل آبجکت یا دیکشنری استراتژی و پر کردن ویجت‌ها"""
        self.current_strategy = strategy
        if not strategy:
            self.clear_inspector()
            return

        # ۱. استخراج عنوان و نماد
        strat_name = self._get_attr(strategy, 'strategy_name', 'استراتژی نامشخص')
        ticker = self._get_attr(strategy, 'underlying_ticker', '-')
        rank = self._get_attr(strategy, 'rank', None)
        rank_str = f" [رتبه {rank}]" if rank is not None else ""
        self.lbl_title.setText(f"🎯 {strat_name} روی نماد {ticker}{rank_str}")

        # ۲. استخراج مقادیر مالی
        margin_req = self._get_attr(strategy, 'margin_required', 0)
        roi_val = self._get_attr(strategy, 'return_on_margin', 0.0)
        max_p = self._get_attr(strategy, 'max_profit', 0)
        max_l = self._get_attr(strategy, 'max_loss', 0)
        pop_val = self._get_attr(strategy, 'probability_of_profit', None)

        metadata = self._get_attr(strategy, 'metadata', {})
        if isinstance(metadata, dict):
            margin_req = margin_req or metadata.get('margin_required', 0)
            roi_val = roi_val or metadata.get('return_on_margin', 0.0)
            max_p = max_p or metadata.get('max_profit', 0)
            max_l = max_l or metadata.get('max_loss', 0)
            pop_val = pop_val or metadata.get('pop', None)

        self.lbl_margin.setText(f"وجه تضمین: {ui_theme.format_rial(margin_req, unit='ریال')}")
        self.lbl_roi.setText(f"بازده روی مارجین: {ui_theme.format_percent(roi_val)}")
        self.lbl_max_profit.setText(f"حداکثر سود: {ui_theme.format_rial(max_p, unit='ریال')}")
        self.lbl_max_loss.setText(f"حداکثر زیان: {ui_theme.format_rial(max_l, unit='ریال')}")
        
        pop_str = f"{pop_val * 100:.1f}%" if pop_val is not None else "محاسبه‌نشده"
        self.lbl_pop.setText(f"احتمال سود: {pop_str}")

        # نقاط سربه‌سر
        be_points = self._get_attr(strategy, 'break_even_points', [])
        if not be_points and isinstance(metadata, dict):
            be_points = metadata.get('break_even_points', [])
        be_str = ", ".join(ui_theme.format_rial(p) for p in be_points) if be_points else "-"
        self.lbl_breakeven.setText(f"سربه‌سر: {be_str}")

        # تنظیم رنگ‌ها
        roi_color = ui_theme.get_pnl_qcolor(roi_val, self._theme_mode).name()
        self.lbl_roi.setStyleSheet(f"font-weight: bold; color: {roi_color};")

        # ۳. استخراج و نمایش یونانی‌ها
        greeks = self._get_attr(strategy, 'greeks', {})
        if not greeks and isinstance(metadata, dict):
            greeks = metadata.get('greeks', {})

        delta_val = greeks.get('delta', getattr(strategy, 'delta', None)) if isinstance(greeks, dict) else None
        gamma_val = greeks.get('gamma', getattr(strategy, 'gamma', None)) if isinstance(greeks, dict) else None
        theta_val = greeks.get('theta', getattr(strategy, 'theta', None)) if isinstance(greeks, dict) else None
        vega_val  = greeks.get('vega', getattr(strategy, 'vega', None)) if isinstance(greeks, dict) else None

        self.lbl_delta.setText(f"Δ دلتا: {ui_theme.format_greek(delta_val)}")
        self.lbl_gamma.setText(f"Γ گاما: {ui_theme.format_greek(gamma_val, decimals=4)}")
        self.lbl_theta.setText(f"Θ تتا: {ui_theme.format_greek(theta_val)}")
        self.lbl_vega.setText(f"ν وگا: {ui_theme.format_greek(vega_val)}")

        # ۴. پر کردن جدول پایه‌ها
        legs = self._get_attr(strategy, 'legs', [])
        self.legs_table.setRowCount(len(legs))

        for r, leg in enumerate(legs):
            contract = getattr(leg, 'contract', None)
            symbol_str = getattr(contract, 'ticker', 'سهام پایه') if contract else 'سهام'
            expiry_val = getattr(contract, 'expiry_date', None) if contract else None
            expiry_str = ui_theme.format_jalali_date(expiry_val, include_dte=True) if expiry_val else '-'
            price_val = getattr(leg, 'entry_price', getattr(contract, 'close_price', 0))
            ratio_val = getattr(leg, 'ratio', 1)
            side_raw = str(getattr(leg, 'side', 'BUY')).upper()
            side_str = "خرید" if "BUY" in side_raw else "فروش"
            opt_type = str(getattr(contract, 'option_type', 'STOCK'))

            self.legs_table.setItem(r, 0, QTableWidgetItem(opt_type))
            self.legs_table.setItem(r, 1, QTableWidgetItem(f"{symbol_str} | {expiry_str}"))
            self.legs_table.setItem(r, 2, QTableWidgetItem(ui_theme.format_rial(price_val)))
            self.legs_table.setItem(r, 3, QTableWidgetItem(str(ratio_val)))

            side_item = QTableWidgetItem(side_str)
            side_color = "#3fb950" if side_str == "خرید" else "#f85149"
            side_item.setForeground(QBrush(QColor(side_color)))
            self.legs_table.setItem(r, 4, side_item)

        # ۵. بازنشانی اسلایدر What-If
        self.slider.setValue(0)
        self._on_slider_changed(0)

    # =========================================================================
    # شبیه‌ساز What-If
    # =========================================================================

    def _on_slider_changed(self, value: int) -> None:
        self.lbl_slider_val.setText(f"{value:+d}%")
        if not self.current_strategy:
            return

        expected_pnl = self._get_attr(self.current_strategy, 'expected_pnl', 0)
        margin_req = self._get_attr(self.current_strategy, 'margin_required', 1) or 1
        metadata = self._get_attr(self.current_strategy, 'metadata', {})
        if not expected_pnl and isinstance(metadata, dict):
            expected_pnl = metadata.get('expected_pnl', 1000000)

        # مدل‌سازی سود/زیان تحت کشش سناریوی قیمتی (تقریب پیوسته با اثر دلتا)
        delta_effect = 1.0 + (value * 0.04)
        simulated_pnl = float(expected_pnl) * delta_effect
        simulated_roi = (simulated_pnl / margin_req) * 100 if margin_req > 0 else 0.0

        pnl_color = ui_theme.get_pnl_qcolor(simulated_pnl, self._theme_mode).name()
        self.lbl_sim_pnl.setText(
            f"سود/زیان برآورد: {ui_theme.format_rial(simulated_pnl, unit='ریال', show_sign=True)} "
            f"({ui_theme.format_percent(simulated_roi)})"
        )
        self.lbl_sim_pnl.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {pnl_color}; padding: 4px;")

    def clear_inspector(self) -> None:
        """پاک‌سازی تمام اطلاعات پنل هنگام نبود داده"""
        self.current_strategy = None
        self.lbl_title.setText("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_margin.setText("وجه تضمین: -")
        self.lbl_roi.setText("بازده روی مارجین: -")
        self.lbl_max_profit.setText("حداکثر سود: -")
        self.lbl_max_loss.setText("حداکثر زیان: -")
        self.lbl_breakeven.setText("نقطه سربه‌سر: -")
        self.lbl_pop.setText("احتمال سود: -")
        self.lbl_delta.setText("Δ دلتا: -")
        self.lbl_gamma.setText("Γ گاما: -")
        self.lbl_theta.setText("Θ تتا: -")
        self.lbl_vega.setText("ν وگا: -")
        self.lbl_sim_pnl.setText("سود/زیان برآورد در سررسید: ۰ ریال (۰.۰%)")
        self.legs_table.setRowCount(0)
        self.slider.setValue(0)

    # =========================================================================
    # اکشن‌های سریع و رویدادها
    # =========================================================================

    def _on_execute_clicked(self) -> None:
        if self.current_strategy:
            self.execute_requested.emit(self.current_strategy)

    def _on_bale_clicked(self) -> None:
        if self.current_strategy:
            self.send_bale_requested.emit(self.current_strategy)

    def _get_attr(self, obj: Any, attr_name: str, default: Any = None) -> Any:
        """دریافت ایمن فیلد چه ورودی آبجکت باشد چه دیکشنری"""
        if isinstance(obj, dict):
            return obj.get(attr_name, default)
        return getattr(obj, attr_name, default)