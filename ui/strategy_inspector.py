# ui/strategy_inspector.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QFrame, QPushButton, QToolTip, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QCursor

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.StrategyInspector")


class StrategyInspectorWidget(QGroupBox):
    """
    پنل تحلیل عمیق و مشخصات استراتژی فشرده‌شده با حداکثر فضای اختصاصی برای جدول پایه‌ها
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("🔍 تحلیل عمیق و مشخصات استراتژی", parent)
        self.current_strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"
        
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        # حداقل حاشیه و فاصله برای لایوت اصلی جهت حذف فضاهای پرت بالا و اطراف
        main_layout.setSpacing(1)
        main_layout.setContentsMargins(2, 8, 2, 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        self._inspector_container = container
        layout = QHBoxLayout(container)
        layout.setSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)

        # استایل کاملاً فشرده برای گروه‌ها جهت حذف فضاهای پرت داخلی
        group_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 10px;
                margin-top: 2px;
                padding: 0px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top right;
                padding: 0 2px;
            }
        """

        # ۱. هدر عنوان استراتژی
        self.lbl_strategy_title = QLabel("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_strategy_title.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #58a6ff; margin: 0px; padding: 0px;")
        self.lbl_strategy_title.setWordWrap(True)
        main_layout.addWidget(self.lbl_strategy_title)

        # ۲. خلاصه مالی و ریسک
        metrics_group = QGroupBox("مالی و ریسک")
        metrics_group.setStyleSheet(group_style)
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setSpacing(1)
        metrics_layout.setContentsMargins(2, 2, 2, 2)

        self.lbl_margin = QLabel("وجه: -")
        self.lbl_roi = QLabel("ROI: -")
        self.lbl_max_profit = QLabel("حداکثر سود: -")
        self.lbl_max_risk = QLabel("حداکثر ریسک: -")
        self.lbl_breakeven = QLabel("سربه‌سر: -")
        self.lbl_pop = QLabel("PoP: -")

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

        layout.addWidget(metrics_group, stretch=2)

        # ۳. پارامترهای یونانی
        greeks_group = QGroupBox("Greeks")
        greeks_group.setStyleSheet(group_style)
        greeks_layout = QHBoxLayout(greeks_group)
        greeks_layout.setContentsMargins(2, 2, 2, 2)
        greeks_layout.setSpacing(2)

        self.lbl_delta = QLabel("Δ: -")
        self.lbl_gamma = QLabel("Γ: -")
        self.lbl_theta = QLabel("Θ: -")
        self.lbl_vega = QLabel("ν: -")

        for lbl in (self.lbl_delta, self.lbl_gamma, self.lbl_theta, self.lbl_vega):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(ui_theme.get_greek_label_style(self._theme_mode))
            greeks_layout.addWidget(lbl)

        layout.addWidget(greeks_group, stretch=3)

        # ۴. جدول پایه‌ها (تنظیم جدید: قرارداد، سمت، قیمت (ریال)، تعداد)
        legs_group = QGroupBox("پایه‌ها")
        legs_group.setStyleSheet(group_style)
        legs_layout = QVBoxLayout(legs_group)
        legs_layout.setContentsMargins(0, 1, 0, 0)
        legs_layout.setSpacing(0)

        self.legs_table = QTableWidget(0, 4)
        self.legs_table.setHorizontalHeaderLabels(
            ["قرارداد", "سمت", "قیمت (ریال)", "تعداد"])

        # فعال بودن اسکرول عمودی برای استراتژی‌های با تعداد لگ بالا (۶+ پایه)
        self.legs_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.legs_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        header = self.legs_table.horizontalHeader()
        header.setFixedHeight(24)
        header.setStyleSheet("""
            QHeaderView::section {
                font-weight: bold;
                font-size: 10px;
                padding: 2px 2px;
            }
        """)

        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive)  # قرارداد
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive)  # سمت
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Interactive)  # قیمت (ریال)
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.Interactive)  # تعداد

        # تنظیم نسبت متناسب عرض ستون‌ها
        self.legs_table.setColumnWidth(0, 200)  # قرارداد
        self.legs_table.setColumnWidth(1, 100)  # سمت
        self.legs_table.setColumnWidth(2, 130)  # قیمت (ریال)
        self.legs_table.setColumnWidth(3, 100)  # تعداد

        self.legs_table.setAlternatingRowColors(True)
        self.legs_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.legs_table.verticalHeader().setVisible(False)

        legs_layout.addWidget(self.legs_table)
        layout.addWidget(legs_group, stretch=4)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def set_theme_mode(self, mode: ui_theme.ThemeMode) -> None:
        self._theme_mode = mode
        self.setStyleSheet(ui_theme.get_inspector_frame_style(mode))
        for lbl in (self.lbl_delta, self.lbl_gamma, self.lbl_theta, self.lbl_vega):
            lbl.setStyleSheet(ui_theme.get_greek_label_style(mode))

    def _copy_contract_to_clipboard(self, symbol_str: str) -> None:
        """کپی نام نماد قرارداد به کلیپ بورد و نمایش Tooltip"""
        clipboard = QApplication.clipboard()
        clipboard.setText(symbol_str)

        pos = QCursor.pos()
        QToolTip.showText(pos, f"📋 قرارداد '{symbol_str}' کپی شد", None)

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

        self.lbl_margin.setText(
            f"وجه: {ui_theme.format_rial(margin_req, unit='')}")
        self.lbl_roi.setText(f"ROI: {ui_theme.format_percent(roi_val)}")
        self.lbl_max_profit.setText(
            f"حداکثر سود: {ui_theme.format_rial(max_p, unit='')}")
        self.lbl_max_risk.setText(
            f"حداکثر ریسک: {ui_theme.format_rial(max_l, unit='')}")

        pop_str = f"{pop_val * 100:.1f}%" if pop_val is not None else "محاسبه‌نشده"
        self.lbl_pop.setText(f"PoP: {pop_str}")

        be_list = getattr(strategy, 'break_even_points', [])
        if not be_list and isinstance(metadata, dict):
            be_list = metadata.get('break_even_points', [])
        be_str = ", ".join(ui_theme.format_rial(p) for p in be_list) if be_list else "-"
        self.lbl_breakeven.setText(f"سربه‌سر: {be_str}")

        greeks = getattr(strategy, 'greeks', {})
        if not greeks and isinstance(metadata, dict):
            greeks = metadata.get('greeks', {})

        delta_val = greeks.get('delta', getattr(strategy, 'delta', None)) if isinstance(greeks, dict) else None
        gamma_val = greeks.get('gamma', getattr(strategy, 'gamma', None)) if isinstance(greeks, dict) else None
        theta_val = greeks.get('theta', getattr(strategy, 'theta', None)) if isinstance(greeks, dict) else None
        vega_val  = greeks.get('vega', getattr(strategy, 'vega', None)) if isinstance(greeks, dict) else None

        self.lbl_delta.setText(f"Δ: {ui_theme.format_greek(delta_val)}")
        self.lbl_gamma.setText(
            f"Γ: {ui_theme.format_greek(gamma_val, decimals=4)}")
        self.lbl_theta.setText(f"Θ: {ui_theme.format_greek(theta_val)}")
        self.lbl_vega.setText(f"ν: {ui_theme.format_greek(vega_val)}")

        legs = getattr(strategy, 'legs', [])
        self.legs_table.setRowCount(len(legs))

        for r, leg in enumerate(legs):
            self.legs_table.setRowHeight(r, 22)
            contract = getattr(leg, 'contract', None)
            symbol_str = contract.ticker if contract else getattr(
                strategy, 'underlying_ticker', 'سهام')
            price_val = getattr(leg, 'entry_price', getattr(contract, 'close_price', 0))
            ratio_val = getattr(leg, 'ratio', 1)
            side_fa = "خرید" if str(getattr(leg, 'side', '')).upper() in ("BUY", "SIDE.BUY") else "فروش"

            # ستون ۰: قرارداد + دکمه کپی
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(1, 0, 1, 0)
            cell_layout.setSpacing(2)

            lbl_symbol = QLabel(symbol_str)
            lbl_symbol.setStyleSheet("font-weight: bold; font-size: 11px;")

            btn_copy = QPushButton(" 📋 ")
            btn_copy.setFixedSize(16, 16)
            btn_copy.setToolTip(f"کپی نام {symbol_str}")
            btn_copy.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    font-size: 10px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    border-radius: 2px;
                }
            """)
            btn_copy.clicked.connect(
                lambda _, sym=symbol_str: self._copy_contract_to_clipboard(sym))

            cell_layout.addWidget(lbl_symbol)
            cell_layout.addWidget(btn_copy)
            cell_layout.addStretch()

            self.legs_table.setCellWidget(r, 0, cell_widget)

            # ستون ۱: سمت
            side_item = QTableWidgetItem(side_fa)
            side_item.setForeground(QBrush(QColor("#3fb950" if side_fa == "خرید" else "#f85149")))
            self.legs_table.setItem(r, 1, side_item)

            # ستون ۲: قیمت (ریال)
            self.legs_table.setItem(r, 2, QTableWidgetItem(
                ui_theme.format_rial(price_val, unit='')))

            # ستون ۳: تعداد
            self.legs_table.setItem(r, 3, QTableWidgetItem(str(ratio_val)))

    def clear_inspector(self) -> None:
        self.current_strategy = None
        self.lbl_strategy_title.setText("هیچ استراتژی‌ای انتخاب نشده است")
        self.lbl_margin.setText("وجه: -")
        self.lbl_roi.setText("ROI: -")
        self.lbl_max_profit.setText("حداکثر سود: -")
        self.lbl_max_risk.setText("حداکثر ریسک: -")
        self.lbl_breakeven.setText("سربه‌سر: -")
        self.lbl_pop.setText("PoP: -")
        self.lbl_delta.setText("Δ: -")
        self.lbl_gamma.setText("Γ: -")
        self.lbl_theta.setText("Θ: -")
        self.lbl_vega.setText("ν: -")
        self.legs_table.setRowCount(0)