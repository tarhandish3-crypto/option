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
from ui import theme as ui_theme
from filters.strategy_filters import get_default_filter_config

logger = logging.getLogger("OptionScanner.UI.StrategyFilterDialog")


class StrategyFilterDialog(QDialog):
    filters_updated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(
            "🎛️ تنظیمات فیلترهای هوشمند و شرایط سودآوری استراتژی‌ها")
        self.resize(880, 720)
        self.setMinimumSize(780, 600)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._theme_mode = getattr(ui_theme, "current_mode", lambda: "dark")()
        self._controls: Dict[str, Dict[str, Any]] = {}
        self._current_filters = self._load_current_filters()

        self._init_ui()

    def _load_current_filters(self) -> Dict[str, Any]:
        """بارگذاری با پشتیبانی همزمان از کلیدهای قدیمی و جدید (Backward Compatibility)"""
        saved = settings_manager.get_active_settings().get("strategy_filters", {})
        defaults = get_default_filter_config()
        merged = {}

        for k, def_val in defaults.items():
            merged[k] = dict(def_val)
            if k in saved and isinstance(saved[k], dict):
                user_val = dict(saved[k])
                # نگاشت کلیدهای قدیمی در صورت وجود
                if "min_cap_return" in user_val and "profit_above_pct" not in user_val:
                    user_val["profit_above_pct"] = user_val.pop(
                        "min_cap_return")
                if "min_target_return" in user_val and "min_profit_pct" not in user_val:
                    user_val["min_profit_pct"] = user_val.pop(
                        "min_target_return")
                if "min_roi" in user_val and "min_profit_pct" not in user_val:
                    user_val["min_profit_pct"] = user_val.pop("min_roi")
                if "min_safe_range_pct" in user_val and "profit_range_max" not in user_val:
                    r = float(user_val.pop("min_safe_range_pct"))
                    user_val["profit_range_min"] = -abs(r)
                    user_val["profit_range_max"] = abs(r)

                merged[k].update(user_val)

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
            "🎛️ غربالگری هوشمند و فیلترهای سودآوری اختصاصی استراتژی‌ها")
        lbl_title.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold;")
        lbl_desc = QLabel(
            "تنظیم بازه‌های سودآوری، حد افت مجاز و حداقل درصد بازدهی برای فیلتر دقیق فرصت‌ها.")
        lbl_desc.setStyleSheet("color: #e6edf3; font-size: 11px;")

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(lbl_desc)
        layout.addWidget(header_frame)

        # ۲. تب‌های ۵ گانه دسته‌بندی استراتژی‌ها
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 6px; padding: 6px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 8px 16px; margin-right: 3px; border-radius: 4px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #1f6feb; color: white; }
        """)

        self.tab_widget.addTab(self._create_bullish_tab(), "📈 صعودی (Bullish)")
        self.tab_widget.addTab(self._create_bearish_tab(), "📉 نزولی (Bearish)")
        self.tab_widget.addTab(self._create_neutral_tab(),
                               "⚖️ خنثی و بدون جهت (Neutral)")
        self.tab_widget.addTab(
            self._create_volatility_tab(), "⚡ نوسان‌گیری (Volatility)")
        self.tab_widget.addTab(
            self._create_arbitrage_tab(), "🔒 آربیتراژ (Arbitrage)")

        layout.addWidget(self.tab_widget, stretch=1)

        # ۳. نوار دکمه‌های پایین با استایل یکپارچه تم
        btn_bar = QHBoxLayout()
        mode = self._theme_mode

        btn_save = QPushButton("💾 ذخیره و اعمال فیلترها")
        btn_save.setStyleSheet(ui_theme.get_button_style(mode, role="success"))
        btn_save.clicked.connect(self._save_settings)
        btn_bar.addWidget(btn_save)

        btn_defaults = QPushButton("🔄 بازنشانی به پیش‌فرض")
        btn_defaults.setStyleSheet(
            ui_theme.get_button_style(mode, role="warning"))
        btn_defaults.clicked.connect(self._reset_to_defaults)
        btn_bar.addWidget(btn_defaults)

        btn_cancel = QPushButton("انصراف")
        btn_cancel.setStyleSheet(
            ui_theme.get_button_style(mode, role="secondary"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    # ==================== سازنده‌های تب‌ها ====================

    def _create_bullish_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_above_level_box(
                "covered_call", "🎯 کاورکال (Covered Call)", -4.5, 2.5),
            self._create_above_level_box(
                "long_call", "📈 خرید اختیار خرید (Long Call)", 4.0, 15.0),
            self._create_above_level_box(
                "short_put", "📈 فروش اختیار فروش (Short Put)", -5.0, 2.5),
            self._create_above_level_box(
                "bull_call_spread", "📈 اسپرد صعودی خرید (Bull Call Spread)", 3.0, 5.0),
            self._create_above_level_box(
                "bull_put_spread", "📈 اسپرد صعودی فروش (Bull Put Spread)", -4.0, 3.0),
            self._create_above_level_box(
                "collar", "🛡️ کالار (Collar)", -5.0, 2.0),
            self._create_above_level_box(
                "married_put", "🛡️ مرید پوت (Married Put)", 2.0, 4.0),
        ])

    def _create_bearish_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_below_level_box(
                "bear_put_spread", "📉 اسپرد نزولی خرید (Bear Put Spread)", -3.0, 5.0),
            self._create_below_level_box(
                "bear_call_spread", "📉 اسپرد نزولی فروش (Bear Call Spread)", 4.0, 3.0),
            self._create_below_level_box(
                "long_put", "📉 خرید اختیار فروش (Long Put)", -4.0, 15.0),
            self._create_below_level_box(
                "short_call", "📉 فروش اختیار خرید (Short Call)", 5.0, 2.5),
        ])

    def _create_neutral_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_inside_range_box(
                "iron_condor", "⚖️ کندور آهنی (Iron Condor)", -8.0, 8.0, 3.0),
            self._create_inside_range_box(
                "iron_butterfly", "⚖️ پروانه آهنی (Iron Butterfly)", -6.0, 6.0, 4.0),
            self._create_inside_range_box(
                "short_straddle", "⚖️ فروش استرادل (Short Straddle)", -6.0, 6.0, 4.0),
            self._create_inside_range_box(
                "short_strangle", "⚖️ فروش استرانگل (Short Strangle)", -8.0, 8.0, 3.5),
        ])

    def _create_volatility_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_outside_range_box(
                "long_straddle", "⚡ خرید استرادل (Long Straddle)", -7.0, 7.0, 2.0),
            self._create_outside_range_box(
                "long_strangle", "⚡ خرید استرانگل (Long Strangle)", -9.0, 9.0, 2.0),
            self._create_outside_range_box(
                "long_guts", "⚡ لانگ گاتس (Long Guts)", -8.0, 8.0, 2.0),
            self._create_outside_range_box(
                "strap", "⚡ استرپ (Strap)", -5.0, 5.0, 2.0),
            self._create_outside_range_box(
                "strip", "⚡ استریپ (Strip)", -5.0, 5.0, 2.0),
        ])

    def _create_arbitrage_tab(self) -> QWidget:
        return self._wrap_scroll([
            self._create_inside_range_box(
                "conversion", "🔒 کانورژن آربیتراژ (Conversion)", -45.0, 45.0, 0.0, use_dte=False),
            self._create_inside_range_box(
                "long_box", "🔒 آربیتراژ باکس (Long Box)", -45.0, 45.0, 0.0, use_dte=False),
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

    # ==================== تولیدکنندگان ویجت ====================

    def _create_above_level_box(self, key: str, title: str, def_above: float, def_profit: float) -> QGroupBox:
        grp = QGroupBox(title)
        layout = QGridLayout(grp)
        cfg = self._current_filters.get(key, {})

        chk = QCheckBox(f"فعال‌سازی فیلتر {title}")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_above = self._create_double_spin(-30.0, 50.0,
                                              cfg.get("profit_above_pct", def_above), " ٪")
        layout.addWidget(QLabel("سوددهی در تغییرات قیمت بالاتر از:"), 1, 0)
        layout.addWidget(spin_above, 1, 1)

        spin_profit = self._create_double_spin(
            0.0, 100.0, cfg.get("min_profit_pct", def_profit), " ٪")
        layout.addWidget(QLabel("حداقل درصد بازدهی در محدوده مجاز:"), 2, 0)
        layout.addWidget(spin_profit, 2, 1)

        self._controls[key] = {
            "chk": chk,
            "rule_type": "above_level",
            "profit_above_pct": spin_above,
            "min_profit_pct": spin_profit,
            "use_dte_factor": cfg.get("use_dte_factor", True)
        }
        return grp

    def _create_below_level_box(self, key: str, title: str, def_below: float, def_profit: float) -> QGroupBox:
        grp = QGroupBox(title)
        layout = QGridLayout(grp)
        cfg = self._current_filters.get(key, {})

        chk = QCheckBox(f"فعال‌سازی فیلتر {title}")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_below = self._create_double_spin(-50.0, 30.0,
                                              cfg.get("profit_below_pct", def_below), " ٪")
        layout.addWidget(QLabel("سوددهی در تغییرات قیمت پایین‌تر از:"), 1, 0)
        layout.addWidget(spin_below, 1, 1)

        spin_profit = self._create_double_spin(
            0.0, 100.0, cfg.get("min_profit_pct", def_profit), " ٪")
        layout.addWidget(QLabel("حداقل درصد بازدهی در محدوده مجاز:"), 2, 0)
        layout.addWidget(spin_profit, 2, 1)

        self._controls[key] = {
            "chk": chk,
            "rule_type": "below_level",
            "profit_below_pct": spin_below,
            "min_profit_pct": spin_profit,
            "use_dte_factor": cfg.get("use_dte_factor", True)
        }
        return grp

    def _create_inside_range_box(self, key: str, title: str, def_min: float, def_max: float, def_profit: float, use_dte: bool = True) -> QGroupBox:
        grp = QGroupBox(title)
        layout = QGridLayout(grp)
        cfg = self._current_filters.get(key, {})

        chk = QCheckBox(f"فعال‌سازی فیلتر {title}")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_min = self._create_double_spin(-50.0, 0.0,
                                            cfg.get("profit_range_min", def_min), " ٪")
        layout.addWidget(QLabel("کف بازه امن سوددهی (حداکثر افت):"), 1, 0)
        layout.addWidget(spin_min, 1, 1)

        spin_max = self._create_double_spin(
            0.0, 50.0, cfg.get("profit_range_max", def_max), " ٪")
        layout.addWidget(QLabel("سقف بازه امن سوددهی (حداکثر رشد):"), 2, 0)
        layout.addWidget(spin_max, 2, 1)

        spin_profit = self._create_double_spin(
            0.0, 100.0, cfg.get("min_profit_pct", def_profit), " ٪")
        layout.addWidget(QLabel("حداقل درصد بازدهی در این بازه:"), 3, 0)
        layout.addWidget(spin_profit, 3, 1)

        self._controls[key] = {
            "chk": chk,
            "rule_type": "inside_range",
            "profit_range_min": spin_min,
            "profit_range_max": spin_max,
            "min_profit_pct": spin_profit,
            "use_dte_factor": use_dte
        }
        return grp

    def _create_outside_range_box(self, key: str, title: str, def_min: float, def_max: float, def_profit: float) -> QGroupBox:
        grp = QGroupBox(title)
        layout = QGridLayout(grp)
        cfg = self._current_filters.get(key, {})

        chk = QCheckBox(f"فعال‌سازی فیلتر {title}")
        chk.setChecked(cfg.get("enabled", True))
        layout.addWidget(chk, 0, 0, 1, 2)

        spin_min = self._create_double_spin(-50.0, 0.0,
                                            cfg.get("loss_range_min", def_min), " ٪")
        layout.addWidget(
            QLabel("کف محدوده زیان (شروع سود در افت بیشتر از):"), 1, 0)
        layout.addWidget(spin_min, 1, 1)

        spin_max = self._create_double_spin(
            0.0, 50.0, cfg.get("loss_range_max", def_max), " ٪")
        layout.addWidget(
            QLabel("سقف محدوده زیان (شروع سود در رشد بیشتر از):"), 2, 0)
        layout.addWidget(spin_max, 2, 1)

        spin_profit = self._create_double_spin(
            0.0, 100.0, cfg.get("min_profit_pct", def_profit), " ٪")
        layout.addWidget(QLabel("حداقل بازده مورد انتظار در نوسان:"), 3, 0)
        layout.addWidget(spin_profit, 3, 1)

        self._controls[key] = {
            "chk": chk,
            "rule_type": "outside_range",
            "loss_range_min": spin_min,
            "loss_range_max": spin_max,
            "min_profit_pct": spin_profit,
            "use_dte_factor": cfg.get("use_dte_factor", True)
        }
        return grp

    def _create_double_spin(self, min_v: float, max_v: float, val: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(float(val))
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        spin.setSuffix(suffix)
        return spin

    def _save_settings(self):
        new_filters = {}
        active_strategies = []

        for key, ctrl in self._controls.items():
            entry = {}
            is_enabled = False
            if "chk" in ctrl:
                is_enabled = ctrl["chk"].isChecked()
                entry["enabled"] = is_enabled

            if is_enabled:
                active_strategies.append(key)

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
        current_cfg["active_strategies"] = active_strategies
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
