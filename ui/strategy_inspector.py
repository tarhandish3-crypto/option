# ui/strategy_inspector.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.StrategyInspector")


class StrategyInspectorWidget(QGroupBox):
    """
    پنل متمرکز، تمیز و سبک تحلیل عمیق و مشخصات استراتژی
    (شامل خلاصه پارامترهای مالی، حساسیت‌های یونانی و جدول تفکیک پایه‌ها)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("🔍 تحلیل عمیق و مشخصات استراتژی", parent)
        self.current_strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 14, 12, 12)

        # ۱. هدر عنوان استراتژی
        self.lbl_strategy_title = QLabel("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_strategy_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #58a6ff;")
        self.lbl_strategy_title.setWordWrap(True)
        layout.addWidget(self.lbl_strategy_title)

        # ۲. بخش خلاصه پارامترهای مالی و ریسک
        metrics_group = QGroupBox("خلاصه مالی و ریسک")
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setSpacing(6)

        self.lbl_margin = QLabel("وجه تضمین: -")
        self.lbl_roi = QLabel("بازده روی مارجین: -")
        self.lbl_max_profit = QLabel("حداکثر سود: -")
        self.lbl_max_risk = QLabel("حداکثر ریسک: -")
        self.lbl_breakeven = QLabel("نقطه سربه‌سر: -")
        self.lbl_pop = QLabel("احتمال سود (PoP): -")

        self.lbl_margin.setStyleSheet("color: #d29922; font-weight: bold;")
        self.lbl_roi.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.lbl_max_profit.setStyleSheet("color: #3fb950;")
        self.lbl_max_risk.setStyleSheet("color: #f85149;")

        metrics_layout.addWidget(self.lbl_margin, 0, 0)
        metrics_layout.addWidget(self.lbl_roi, 0, 1)
        metrics_layout.addWidget(self.lbl_max_profit, 1, 0)
        metrics_layout.addWidget(self.lbl_max_risk, 1, 1)
        metrics_layout.addWidget(self.lbl_breakeven, 2, 0)
        metrics_layout.addWidget(self.lbl_pop, 2, 1)
        layout.addWidget(metrics_group)

        # ۳. بخش پارامترهای یونانی (Option Greeks)
        greeks_group = QGroupBox("پارامترهای حساسیت یونانی (Greeks)")
        greeks_layout = QHBoxLayout(greeks_group)
        greeks_layout.setContentsMargins(6, 6, 6, 6)

        self.lbl_delta = QLabel("Δ دلتا: -")
        self.lbl_gamma = QLabel("Γ گاما: -")
        self.lbl_theta = QLabel("Θ تتا: -")
        self.lbl_vega = QLabel("ν وگا: -")

        for lbl in (self.lbl_delta, self.lbl_gamma, self.lbl_theta, self.lbl_vega):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-weight: bold; background-color: rgba(255,255,255,0.04); border-radius: 4px; padding: 4px;")
            greeks_layout.addWidget(lbl)

        layout.addWidget(greeks_group)

        # ۴. جدول تفکیک پایه‌ها (Legs Breakdown)
        lbl_legs = QLabel("📌 پایه‌های معاملاتی (Legs Breakdown):")
        lbl_legs.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl_legs)

        self.legs_table = QTableWidget(0, 5)
        self.legs_table.setHorizontalHeaderLabels(["نوع", "قرارداد / سررسید", "قیمت", "تعداد", "سمت"])
        self.legs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.legs_table.setFixedHeight(140)
        self.legs_table.setAlternatingRowColors(True)
        self.legs_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.legs_table)

        layout.addStretch()

    def set_theme_mode(self, mode: ui_theme.ThemeMode) -> None:
        self._theme_mode = mode
        self.setStyleSheet(ui_theme.get_inspector_frame_style(mode))

    def load_strategy(self, strategy: Any) -> None:
        """بارگذاری اطلاعات استراتژی انتخاب‌شده"""
        self.current_strategy = strategy
        if not strategy:
            self.clear_inspector()
            return

        strat_name = str(getattr(strategy, 'strategy_name', 'استراتژی') or 'استراتژی')
        ticker = str(getattr(strategy, 'underlying_ticker', '-') or '-')
        rank = getattr(strategy, 'rank', None)
        rank_str = f" [رتبه {rank}]" if rank is not None else ""
        self.lbl_strategy_title.setText(f"🎯 {strat_name} روی {ticker}{rank_str}")

        margin_req = getattr(strategy, 'margin_required', 0)
        roi_val = getattr(strategy, 'return_on_margin', 0.0)
        max_p = getattr(strategy, 'max_profit', 0)
        max_l = getattr(strategy, 'max_loss', 0)
        pop_val = getattr(strategy, 'probability_of_profit', None)

        metadata = getattr(strategy, 'metadata', {})
        if isinstance(metadata, dict):
            margin_req = margin_req or metadata.get('margin_required', 0)
            roi_val = roi_val or metadata.get('return_on_margin', 0.0)
            max_p = max_p or metadata.get('max_profit', 0)
            max_l = max_l or metadata.get('max_loss', 0)
            pop_val = pop_val or metadata.get('pop', None)

        self.lbl_margin.setText(f"وجه تضمین: {ui_theme.format_rial(margin_req, unit='ریال')}")
        self.lbl_roi.setText(f"بازده روی مارجین: {ui_theme.format_percent(roi_val)}")
        self.lbl_max_profit.setText(f"حداکثر سود: {ui_theme.format_rial(max_p, unit='ریال')}")
        self.lbl_max_risk.setText(f"حداکثر ریسک: {ui_theme.format_rial(max_l, unit='ریال')}")

        pop_str = f"{pop_val * 100:.1f}%" if pop_val is not None else "محاسبه‌نشده"
        self.lbl_pop.setText(f"احتمال سود: {pop_str}")

        # نقاط سربه‌سر
        be_list = getattr(strategy, 'break_even_points', [])
        if not be_list and isinstance(metadata, dict):
            be_list = metadata.get('break_even_points', [])
        be_str = ", ".join(ui_theme.format_rial(p) for p in be_list) if be_list else "-"
        self.lbl_breakeven.setText(f"سربه‌سر: {be_str}")

        # پارامترهای یونانی
        greeks = getattr(strategy, 'greeks', {})
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

        # پر کردن جدول پایه‌ها
        legs = getattr(strategy, 'legs', [])
        self.legs_table.setRowCount(len(legs))
        for r, leg in enumerate(legs):
            contract = getattr(leg, 'contract', None)
            symbol_str = contract.ticker if contract else getattr(strategy, 'underlying_ticker', 'سهام پایه')
            expiry_str = ui_theme.format_jalali_date(getattr(contract, 'expiry_date', '')) if contract else '-'
            price_val = getattr(leg, 'entry_price', getattr(contract, 'close_price', 0))
            ratio_val = getattr(leg, 'ratio', 1)
            side_fa = "خرید" if str(getattr(leg, 'side', '')).upper() in ("BUY", "SIDE.BUY") else "فروش"
            opt_type = str(getattr(contract, 'option_type', 'STOCK'))

            self.legs_table.setItem(r, 0, QTableWidgetItem(opt_type))
            self.legs_table.setItem(r, 1, QTableWidgetItem(f"{symbol_str} | {expiry_str}"))
            self.legs_table.setItem(r, 2, QTableWidgetItem(ui_theme.format_rial(price_val)))
            self.legs_table.setItem(r, 3, QTableWidgetItem(str(ratio_val)))
            
            side_item = QTableWidgetItem(side_fa)
            side_item.setForeground(QBrush(QColor("#3fb950" if side_fa == "خرید" else "#f85149")))
            self.legs_table.setItem(r, 4, side_item)

    def clear_inspector(self) -> None:
        self.current_strategy = None
        self.lbl_strategy_title.setText("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_margin.setText("وجه تضمین: -")
        self.lbl_roi.setText("بازده روی مارجین: -")
        self.lbl_max_profit.setText("حداکثر سود: -")
        self.lbl_max_risk.setText("حداکثر ریسک: -")
        self.lbl_breakeven.setText("نقطه سربه‌سر: -")
        self.lbl_pop.setText("احتمال سود (PoP): -")
        self.lbl_delta.setText("Δ دلتا: -")
        self.lbl_gamma.setText("Γ گاما: -")
        self.lbl_theta.setText("Θ تتا: -")
        self.lbl_vega.setText("ν وگا: -")
        self.legs_table.setRowCount(0)