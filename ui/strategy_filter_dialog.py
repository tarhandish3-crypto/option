# ui/strategy_filter_dialog.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QDoubleSpinBox, QGroupBox, QTabWidget,
    QWidget, QScrollArea, QFrame, QMessageBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal

from ui.settings_manager import settings_manager
from filters.strategy_filters import get_default_filter_config

logger = logging.getLogger("OptionScanner.UI.StrategyFilterDialog")


class StrategyFilterDialog(QDialog):
    """
    دیالوگ جامع تنظیم پارامترهای فیلتر هوشمند و شرایط سودآوری
    برای تمامی استراتژی‌های موجود در سیستم
    """
    filters_updated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(
            "🎛️ تنظیمات فیلترهای هوشمند و شرایط سودآوری استراتژی‌ها")
        self.resize(880, 720)
        self.setMinimumSize(780, 600)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._controls: Dict[str, Dict[str, Any]] = {}
        self._current_filters = self._load_current_filters()

        self._init_ui()

    def _load_current_filters(self) -> Dict[str, Any]:
        saved = settings_manager.get_active_settings().get("strategy_filters", {})
        defaults = get_default_filter_config()
        merged = {}
        for k, v in defaults.items():
            merged[k] = dict(v)
            if k in saved:
                merged[k].update(saved[k])
        return merged

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # ۱. هدر توضیحات
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #0d419d);
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel(
            "🎛️ غربالگری هوشمند و فیلترهای سودآوری اختصاصی تمام استراتژی‌ها")
        lbl_title.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold;")
        lbl_desc = QLabel(
            "با فعال‌سازی و تنظیم شروط هر استراتژی، تنها فرصت‌هایی که دارای سود مناسب، نسبت ریسک به ریوارد بالا و حاشیه امنیت مطلوب هستند استخراج می‌گردند.")
        lbl_desc.setStyleSheet("color: #e6edf3; font-size: 11px;")

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(lbl_desc)
        layout.addWidget(header_frame)

        # ۲. تب‌های ۵ گانه دسته‌بندی تمام استراتژی‌ها
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 6px; padding: 6px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 8px 16px; margin-right: 3px; border-radius: 4px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #1f6feb; color: white; }
        """)

        self.tab_widget.addTab(self._create_bullish_tab(), "📈 صعودی (Bullish)")
        self.tab_widget.addTab(self._create_bearish_tab(), "📉 نزولی (Bearish)")
        self.tab_widget.addTab(self._create_neutral_tab(),
                               "⚖️ خنثی و درآمدی (Neutral)")
        self.tab_widget.addTab(
            self._create_volatility_tab(), "⚡ نوسان‌گیری (Volatility)")
        self.tab_widget.addTab(
            self._create_arbitrage_tab(), "🔒 آربیتراژ (Arbitrage)")

        layout.addWidget(self.tab_widget, stretch=1)

        # ۳. نوار دکمه‌های پایین
        btn_bar = QHBoxLayout()

        btn_save = QPushButton("💾 ذخیره و اعمال فیلترها")
        btn_save.setStyleSheet(
            "background-color: #238636; color: white; font-weight: bold; padding: 8px 20px; border-radius: 5px;")
        btn_save.clicked.connect(self._save_settings)
        btn_bar.addWidget(btn_save)

        btn_defaults = QPushButton("🔄 بازنشانی به پیش‌فرض")
        btn_defaults.setStyleSheet("padding: 8px 14px;")
        btn_defaults.clicked.connect(self._reset_to_defaults)
        btn_bar.addWidget(btn_defaults)

        btn_cancel = QPushButton("انصراف")
        btn_cancel.setStyleSheet("padding: 8px 14px;")
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    # ==================== تب‌های دسته‌بندی ====================

    def _create_bullish_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_covered_call_box(),
            self._create_long_call_box(),
            self._create_short_put_box(),
            self._create_bull_call_spread_box(),
            self._create_bull_put_spread_box(),
            self._create_collar_box(),
            self._create_married_put_box(),
        ])

    def _create_bearish_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_long_put_box(),
            self._create_short_call_box(),
            self._create_bear_put_spread_box(),
            self._create_bear_call_spread_box(),
        ])

    def _create_neutral_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_iron_condor_box(),
            self._create_iron_butterfly_box(),
            self._create_short_straddle_box(),
            self._create_short_strangle_box(),
        ])

    def _create_volatility_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_long_straddle_box(),
            self._create_long_strangle_box(),
            self._create_long_guts_box(),
            self._create_strap_box(),
            self._create_strip_box(),
        ])

    def _create_arbitrage_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_conversion_box(),
            self._create_long_box_box(),
        ])

    def _wrap_scroll(self, widgets: list) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        box = QVBoxLayout(container)
        box.setSpacing(10)
        box.setContentsMargins(8, 8, 8, 8)
        for w in widgets:
            box.addWidget(w)
        box.addStretch()
        scroll.setWidget(container)
        return scroll

    # ==================== ۱. استراتژی‌های صعودی ====================

    def _create_covered_call_box(self) -> QGroupBox:
        grp = QGroupBox("🎯 کاورکال (Covered Call)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("covered_call", {})

        chk = QCheckBox("فعال‌سازی فیلتر هوشمند کاورکال")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            0.0, 50.0, cfg.get("min_cap_return", 3.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در سقف (ثبات یا رشد سهم):"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_buffer = self._create_double_spin(
            -30.0, 0.0, cfg.get("min_downside_buffer", -4.5), " ٪")
        layout.addWidget(
            QLabel("حداقل حاشیه امنیت افت سهم تا نقطه سربه‌سر:"), 2, 0)
        layout.addWidget(spin_buffer, 2, 1)

        self._controls["covered_call"] = {
            "chk": chk, "min_cap_return": spin_cap, "min_downside_buffer": spin_buffer, "use_dte_factor": True
        }
        return grp

    def _create_long_call_box(self) -> QGroupBox:
        grp = QGroupBox("📈 خرید اختیار خرید (Long Call)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_call", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ کال")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_rr = self._create_double_spin(
            0.5, 10.0, cfg.get("min_rr_ratio", 2.0), " برابر")
        layout.addWidget(QLabel("حداقل نسبت سود به ریسک (R/R):"), 1, 0)
        layout.addWidget(spin_rr, 1, 1)

        spin_target = self._create_double_spin(
            5.0, 200.0, cfg.get("min_target_return", 25.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در صورت رشد سهم:"), 2, 0)
        layout.addWidget(spin_target, 2, 1)

        self._controls["long_call"] = {
            "chk": chk, "min_rr_ratio": spin_rr, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    def _create_short_put_box(self) -> QGroupBox:
        grp = QGroupBox("📈 فروش اختیار فروش (Short Put)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("short_put", {})

        chk = QCheckBox("فعال‌سازی فیلتر شورت پوت")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            1.0, 40.0, cfg.get("min_cap_return", 3.5), " ٪")
        layout.addWidget(QLabel("حداقل پریمیوم دریافتی نسبت به مارجین:"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_buffer = self._create_double_spin(
            -30.0, 0.0, cfg.get("min_downside_buffer", -5.0), " ٪")
        layout.addWidget(QLabel("حداقل حاشیه امنیت افت سهم:"), 2, 0)
        layout.addWidget(spin_buffer, 2, 1)

        self._controls["short_put"] = {
            "chk": chk, "min_cap_return": spin_cap, "min_downside_buffer": spin_buffer, "use_dte_factor": True
        }
        return grp

    def _create_bull_call_spread_box(self) -> QGroupBox:
        grp = QGroupBox("📈 اسپرد صعودی خرید (Bull Call Spread)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("bull_call_spread", {})

        chk = QCheckBox("فعال‌سازی فیلتر بول کال اسپرد")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_rr = self._create_double_spin(
            0.5, 10.0, cfg.get("min_rr_ratio", 1.2), " برابر")
        layout.addWidget(QLabel("حداقل نسبت سود به ریسک (R/R):"), 1, 0)
        layout.addWidget(spin_rr, 1, 1)

        spin_target = self._create_double_spin(
            2.0, 100.0, cfg.get("min_target_return", 10.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در هدف صعودی:"), 2, 0)
        layout.addWidget(spin_target, 2, 1)

        self._controls["bull_call_spread"] = {
            "chk": chk, "min_rr_ratio": spin_rr, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    def _create_bull_put_spread_box(self) -> QGroupBox:
        grp = QGroupBox("📈 اسپرد صعودی فروش (Bull Put Spread / Credit)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("bull_put_spread", {})

        chk = QCheckBox("فعال‌سازی فیلتر بول پوت اسپرد")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            1.0, 40.0, cfg.get("min_cap_return", 4.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_buffer = self._create_double_spin(
            -30.0, 0.0, cfg.get("min_downside_buffer", -5.0), " ٪")
        layout.addWidget(QLabel("حداقل حاشیه امنیت افت سهم:"), 2, 0)
        layout.addWidget(spin_buffer, 2, 1)

        self._controls["bull_put_spread"] = {
            "chk": chk, "min_cap_return": spin_cap, "min_downside_buffer": spin_buffer, "use_dte_factor": True
        }
        return grp

    def _create_collar_box(self) -> QGroupBox:
        grp = QGroupBox("🛡️ کالار (Collar)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("collar", {})

        chk = QCheckBox("فعال‌سازی فیلتر کالار")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            0.0, 30.0, cfg.get("min_cap_return", 2.5), " ٪")
        layout.addWidget(QLabel("حداقل سود در سقف:"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_loss = self._create_double_spin(-30.0,
                                             0.0, cfg.get("max_allowed_loss", -5.0), " ٪")
        layout.addWidget(QLabel("حداکثر زیان مجاز تحت ریزش شدید:"), 2, 0)
        layout.addWidget(spin_loss, 2, 1)

        self._controls["collar"] = {
            "chk": chk, "min_cap_return": spin_cap, "max_allowed_loss": spin_loss, "use_dte_factor": True
        }
        return grp

    def _create_married_put_box(self) -> QGroupBox:
        grp = QGroupBox("🛡️ مرید پوت و بیمه سهم (Married Put)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("married_put", {})

        chk = QCheckBox("فعال‌سازی فیلتر مرید پوت")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_loss = self._create_double_spin(-30.0,
                                             0.0, cfg.get("max_allowed_loss", -6.0), " ٪")
        layout.addWidget(QLabel("حداکثر زیان در بدترین سناریو:"), 1, 0)
        layout.addWidget(spin_loss, 1, 1)

        spin_target = self._create_double_spin(
            2.0, 100.0, cfg.get("min_target_return", 8.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در صورت رشد ۵٪ سهم:"), 2, 0)
        layout.addWidget(spin_target, 2, 1)

        self._controls["married_put"] = {
            "chk": chk, "max_allowed_loss": spin_loss, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    # ==================== ۲. استراتژی‌های نزولی ====================

    def _create_long_put_box(self) -> QGroupBox:
        grp = QGroupBox("📉 خرید اختیار فروش (Long Put)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_put", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ پوت")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_rr = self._create_double_spin(
            0.5, 10.0, cfg.get("min_rr_ratio", 2.0), " برابر")
        layout.addWidget(QLabel("حداقل نسبت سود به ریسک (R/R):"), 1, 0)
        layout.addWidget(spin_rr, 1, 1)

        spin_target = self._create_double_spin(
            5.0, 200.0, cfg.get("min_target_return", 25.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در افت قیمت:"), 2, 0)
        layout.addWidget(spin_target, 2, 1)

        self._controls["long_put"] = {
            "chk": chk, "min_rr_ratio": spin_rr, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    def _create_short_call_box(self) -> QGroupBox:
        grp = QGroupBox("📉 فروش اختیار خرید (Short Call)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("short_call", {})

        chk = QCheckBox("فعال‌سازی فیلتر شورت کال")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            1.0, 30.0, cfg.get("min_cap_return", 3.5), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_buffer = self._create_double_spin(
            0.0, 30.0, cfg.get("min_upside_buffer", 6.0), " ٪")
        layout.addWidget(QLabel("حداقل حاشیه امنیت رشد سهم تا سربه‌سر:"), 2, 0)
        layout.addWidget(spin_buffer, 2, 1)

        self._controls["short_call"] = {
            "chk": chk, "min_cap_return": spin_cap, "min_upside_buffer": spin_buffer, "use_dte_factor": True
        }
        return grp

    def _create_bear_put_spread_box(self) -> QGroupBox:
        grp = QGroupBox("📉 اسپرد نزولی خرید (Bear Put Spread)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("bear_put_spread", {})

        chk = QCheckBox("فعال‌سازی فیلتر بیر پوت اسپرد")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_rr = self._create_double_spin(
            0.5, 10.0, cfg.get("min_rr_ratio", 1.2), " برابر")
        layout.addWidget(QLabel("حداقل نسبت سود به ریسک:"), 1, 0)
        layout.addWidget(spin_rr, 1, 1)

        spin_target = self._create_double_spin(
            2.0, 100.0, cfg.get("min_target_return", 10.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در هدف نزولی:"), 2, 0)
        layout.addWidget(spin_target, 2, 1)

        self._controls["bear_put_spread"] = {
            "chk": chk, "min_rr_ratio": spin_rr, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    def _create_bear_call_spread_box(self) -> QGroupBox:
        grp = QGroupBox("📉 اسپرد نزولی فروش (Bear Call Spread / Credit)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("bear_call_spread", {})

        chk = QCheckBox("فعال‌سازی فیلتر بیر کال اسپرد")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_cap = self._create_double_spin(
            1.0, 40.0, cfg.get("min_cap_return", 4.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_cap, 1, 1)

        spin_buffer = self._create_double_spin(
            0.0, 30.0, cfg.get("min_upside_buffer", 5.0), " ٪")
        layout.addWidget(QLabel("حداقل حاشیه امنیت رشد سهم:"), 2, 0)
        layout.addWidget(spin_buffer, 2, 1)

        self._controls["bear_call_spread"] = {
            "chk": chk, "min_cap_return": spin_cap, "min_upside_buffer": spin_buffer, "use_dte_factor": True
        }
        return grp

    # ==================== ۳. استراتژی‌های خنثی ====================

    def _create_iron_condor_box(self) -> QGroupBox:
        grp = QGroupBox("⚖️ کندور آهنی (Iron Condor)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("iron_condor", {})

        chk = QCheckBox("فعال‌سازی فیلتر کندور آهنی")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_roi = self._create_double_spin(
            1.0, 50.0, cfg.get("min_roi", 6.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین (ROI):"), 1, 0)
        layout.addWidget(spin_roi, 1, 1)

        spin_range = self._create_double_spin(
            3.0, 30.0, cfg.get("min_safe_range_pct", 8.0), " ±٪")
        layout.addWidget(QLabel("حداقل دامنه امن نوسان سهم:"), 2, 0)
        layout.addWidget(spin_range, 2, 1)

        self._controls["iron_condor"] = {
            "chk": chk, "min_roi": spin_roi, "min_safe_range_pct": spin_range, "use_dte_factor": True
        }
        return grp

    def _create_iron_butterfly_box(self) -> QGroupBox:
        grp = QGroupBox("⚖️ پروانه آهنی (Iron Butterfly)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("iron_butterfly", {})

        chk = QCheckBox("فعال‌سازی فیلتر پروانه آهنی")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_roi = self._create_double_spin(
            1.0, 60.0, cfg.get("min_roi", 8.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_roi, 1, 1)

        spin_range = self._create_double_spin(
            2.0, 25.0, cfg.get("min_safe_range_pct", 6.0), " ±٪")
        layout.addWidget(QLabel("حداقل پهنای بازه سربه‌سر:"), 2, 0)
        layout.addWidget(spin_range, 2, 1)

        self._controls["iron_butterfly"] = {
            "chk": chk, "min_roi": spin_roi, "min_safe_range_pct": spin_range, "use_dte_factor": True
        }
        return grp

    def _create_short_straddle_box(self) -> QGroupBox:
        grp = QGroupBox("⚖️ فروش استرادل (Short Straddle)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("short_straddle", {})

        chk = QCheckBox("فعال‌سازی فیلتر شورت استرادل")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_roi = self._create_double_spin(
            1.0, 50.0, cfg.get("min_roi", 8.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_roi, 1, 1)

        spin_range = self._create_double_spin(
            2.0, 25.0, cfg.get("min_safe_range_pct", 6.0), " ±٪")
        layout.addWidget(QLabel("حداقل بازه امن سربه‌سر:"), 2, 0)
        layout.addWidget(spin_range, 2, 1)

        self._controls["short_straddle"] = {
            "chk": chk, "min_roi": spin_roi, "min_safe_range_pct": spin_range, "use_dte_factor": True
        }
        return grp

    def _create_short_strangle_box(self) -> QGroupBox:
        grp = QGroupBox("⚖️ فروش استرانگل (Short Strangle)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("short_strangle", {})

        chk = QCheckBox("فعال‌سازی فیلتر شورت استرانگل")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_roi = self._create_double_spin(
            1.0, 50.0, cfg.get("min_roi", 7.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده روی مارجین:"), 1, 0)
        layout.addWidget(spin_roi, 1, 1)

        spin_range = self._create_double_spin(
            3.0, 30.0, cfg.get("min_safe_range_pct", 8.0), " ±٪")
        layout.addWidget(QLabel("حداقل فاصله دو نقطه سربه‌سر:"), 2, 0)
        layout.addWidget(spin_range, 2, 1)

        self._controls["short_strangle"] = {
            "chk": chk, "min_roi": spin_roi, "min_safe_range_pct": spin_range, "use_dte_factor": True
        }
        return grp

    # ==================== ۴. استراتژی‌های نوسان‌گیری ====================

    def _create_long_straddle_box(self) -> QGroupBox:
        grp = QGroupBox("⚡ خرید استرادل (Long Straddle)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_straddle", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ استرادل")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_move = self._create_double_spin(
            2.0, 30.0, cfg.get("max_breakeven_move_pct", 9.0), " ٪")
        layout.addWidget(QLabel("حداکثر حرکت لازم سهم تا ورود به سود:"), 1, 0)
        layout.addWidget(spin_move, 1, 1)

        self._controls["long_straddle"] = {
            "chk": chk, "max_breakeven_move_pct": spin_move, "use_dte_factor": True
        }
        return grp

    def _create_long_strangle_box(self) -> QGroupBox:
        grp = QGroupBox("⚡ خرید استرانگل (Long Strangle)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_strangle", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ استرانگل")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_move = self._create_double_spin(
            3.0, 35.0, cfg.get("max_breakeven_move_pct", 12.0), " ٪")
        layout.addWidget(QLabel("حداکثر حرکت لازم سهم تا ورود به سود:"), 1, 0)
        layout.addWidget(spin_move, 1, 1)

        self._controls["long_strangle"] = {
            "chk": chk, "max_breakeven_move_pct": spin_move, "use_dte_factor": True
        }
        return grp

    def _create_long_guts_box(self) -> QGroupBox:
        grp = QGroupBox("⚡ استراتژی لانگ گاتس (Long Guts)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_guts", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ گاتس")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_move = self._create_double_spin(
            2.0, 30.0, cfg.get("max_breakeven_move_pct", 10.0), " ٪")
        layout.addWidget(QLabel("حداکثر فاصله سربه‌سر تا قیمت روز:"), 1, 0)
        layout.addWidget(spin_move, 1, 1)

        self._controls["long_guts"] = {
            "chk": chk, "max_breakeven_move_pct": spin_move, "use_dte_factor": True
        }
        return grp

    def _create_strap_box(self) -> QGroupBox:
        grp = QGroupBox("⚡ استراتژی استرپ (Strap - تعصب صعودی)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("strap", {})

        chk = QCheckBox("فعال‌سازی فیلتر استرپ")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_target = self._create_double_spin(
            5.0, 100.0, cfg.get("min_target_return", 15.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در نوسان صعودی:"), 1, 0)
        layout.addWidget(spin_target, 1, 1)

        self._controls["strap"] = {
            "chk": chk, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    def _create_strip_box(self) -> QGroupBox:
        grp = QGroupBox("⚡ استراتژی استریپ (Strip - تعصب نزولی)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("strip", {})

        chk = QCheckBox("فعال‌سازی فیلتر استریپ")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_target = self._create_double_spin(
            5.0, 100.0, cfg.get("min_target_return", 15.0), " ٪")
        layout.addWidget(QLabel("حداقل بازده در نوسان نزولی:"), 1, 0)
        layout.addWidget(spin_target, 1, 1)

        self._controls["strip"] = {
            "chk": chk, "min_target_return": spin_target, "use_dte_factor": True
        }
        return grp

    # ==================== ۵. استراتژی‌های آربیتراژ ====================

    def _create_conversion_box(self) -> QGroupBox:
        grp = QGroupBox("🔒 کانورژن آربیتراژ (Conversion)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("conversion", {})

        chk = QCheckBox("فعال‌سازی فیلتر کانورژن")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_annual = self._create_double_spin(
            10.0, 100.0, cfg.get("min_annualized_roi", 25.0), " ٪ سالانه")
        layout.addWidget(QLabel("حداقل سود خالص سالانه تضمینی:"), 1, 0)
        layout.addWidget(spin_annual, 1, 1)

        self._controls["conversion"] = {
            "chk": chk, "min_annualized_roi": spin_annual, "require_zero_loss": True
        }
        return grp

    def _create_long_box_box(self) -> QGroupBox:
        grp = QGroupBox("🔒 آربیتراژ باکس (Long Box Spread)")
        layout = QGridLayout(grp)
        cfg = self._current_filters.get("long_box", {})

        chk = QCheckBox("فعال‌سازی فیلتر لانگ باکس")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_annual = self._create_double_spin(
            10.0, 100.0, cfg.get("min_annualized_roi", 25.0), " ٪ سالانه")
        layout.addWidget(QLabel("حداقل سود خالص سالانه تضمینی:"), 1, 0)
        layout.addWidget(spin_annual, 1, 1)

        self._controls["long_box"] = {
            "chk": chk, "min_annualized_roi": spin_annual, "require_zero_loss": True
        }
        return grp

    # ==================== ابزارهای کمکی ====================

    def _create_double_spin(self, min_v: float, max_v: float, val: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(val)
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        spin.setSuffix(suffix)
        return spin

    def _save_settings(self):
        new_filters = {}
        for key, ctrl in self._controls.items():
            entry = {}
            if "chk" in ctrl:
                entry["enabled"] = ctrl["chk"].isChecked()
            for field, widget in ctrl.items():
                if field == "chk":
                    continue
                if isinstance(widget, QDoubleSpinBox):
                    entry[field] = widget.value()
                else:
                    entry[field] = widget
            new_filters[key] = entry

        current_cfg = settings_manager.get_active_settings()
        current_cfg["strategy_filters"] = new_filters
        settings_manager.save_settings(current_cfg)

        self.filters_updated.emit(new_filters)
        logger.info(
            f"All strategy filters ({len(new_filters)}) updated and saved permanently")

        QMessageBox.information(
            self, "ذخیره موفق", f"✅ تنظیمات فیلترهای سودآوری برای تمام {len(new_filters)} استراتژی با موفقیت ذخیره شد."
        )
        self.accept()

    def _reset_to_defaults(self):
        defaults = get_default_filter_config()
        self._current_filters = defaults
        for key, ctrl in self._controls.items():
            d = defaults.get(key, {})
            if "chk" in ctrl and "enabled" in d:
                ctrl["chk"].setChecked(d["enabled"])
            for field, widget in ctrl.items():
                if field != "chk" and isinstance(widget, QDoubleSpinBox) and field in d:
                    widget.setValue(float(d[field]))
        logger.info("All strategy filters reset to default parameters")
