# ui/strategy_settings_dialog.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QDoubleSpinBox, QGroupBox, QTabWidget,
    QWidget, QScrollArea, QFrame, QMessageBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal

from ui.settings_manager import settings_manager
from filters.strategy_filters import get_default_filter_config
import config

logger = logging.getLogger("OptionScanner.UI.StrategySettingsDialog")

STRATEGY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # ۱. صعودی
    "covered_call": {"en": "Covered Call", "fa": "کاورکال", "cat": "bullish", "desc": "خرید سهام + فروش کال (کسب درآمد ماهانه)"},
    "bull_call_spread": {"en": "Bull Call Spread", "fa": "اسپرد صعودی خرید", "cat": "bullish", "desc": "خرید کال پایین + فروش کال بالا"},
    "bull_put_spread": {"en": "Bull Put Spread", "fa": "اسپرد صعودی فروش", "cat": "bullish", "desc": "فروش پوت بالا + خرید پوت پایین (اعتباری)"},
    "long_call": {"en": "Long Call", "fa": "خرید اختیار خرید", "cat": "bullish", "desc": "معامله اهرمی صعودی مستقیم"},
    "short_put": {"en": "Short Put", "fa": "فروش اختیار فروش", "cat": "bullish", "desc": "کسب پریمیوم در ثبات یا رشد سهم"},
    "collar": {"en": "Collar", "fa": "کالار", "cat": "bullish", "desc": "سهام + خرید پوت محافظ + فروش کال"},
    "married_put": {"en": "Married Put", "fa": "بیمه سهام", "cat": "bullish", "desc": "خرید سهام + خرید پوت همزمان"},

    # ۲. نزولی
    "bear_put_spread": {"en": "Bear Put Spread", "fa": "اسپرد نزولی خرید", "cat": "bearish", "desc": "خرید پوت بالا + فروش پوت پایین"},
    "bear_call_spread": {"en": "Bear Call Spread", "fa": "اسپرد نزولی فروش", "cat": "bearish", "desc": "فروش کال پایین + خرید کال بالا (اعتباری)"},
    "long_put": {"en": "Long Put", "fa": "خرید اختیار فروش", "cat": "bearish", "desc": "سودگیری اهرمی از ریزش سهم"},
    "short_call": {"en": "Short Call", "fa": "فروش اختیار خرید", "cat": "bearish", "desc": "کسب پریمیوم با تعهد فروش سهم"},

    # ۳. خنثی
    "iron_condor": {"en": "Iron Condor", "fa": "کندور آهنی", "cat": "neutral", "desc": "۴ پایه غیرهم‌مرکز برای سود در بازه آرامش"},
    "iron_butterfly": {"en": "Iron Butterfly", "fa": "پروانه آهنی", "cat": "neutral", "desc": "پروانه با استرایک مرکزی مشترک"},
    "short_straddle": {"en": "Short Straddle", "fa": "فروش استرادل", "cat": "neutral", "desc": "فروش همزمان کال و پوت هم‌قیمت"},
    "short_strangle": {"en": "Short Strangle", "fa": "فروش استرانگل", "cat": "neutral", "desc": "فروش کال OTM و پوت OTM"},

    # ۴. نوسانی
    "strap": {"en": "Strap", "fa": "استرپ", "cat": "volatility", "desc": "۲ کال خرید + ۱ پوت خرید (تعصب صعودی)"},
    "strip": {"en": "Strip", "fa": "استریپ", "cat": "volatility", "desc": "۲ پوت خرید + ۱ کال خرید (تعصب نزولی)"},
    "long_straddle": {"en": "Long Straddle", "fa": "خرید استرادل", "cat": "volatility", "desc": "خرید همزمان کال و پوت در انتظار انفجار قیمت"},
    "long_strangle": {"en": "Long Strangle", "fa": "خرید استرانگل", "cat": "volatility", "desc": "خرید کال و پوت خارج از سود با هزینه کمتر"},
    "long_guts": {"en": "Long Guts", "fa": "لانگ گاتس", "cat": "volatility", "desc": "خرید کال ITM و پوت ITM"},

    # ۵. آربیتراژ
    "conversion": {"en": "Conversion", "fa": "کانورژن آربیتراژ", "cat": "arbitrage", "desc": "سود قطعی بدون ریسک با سهام + پوت - کال"},
    "long_box": {"en": "Long Box", "fa": "آربیتراژ باکس", "cat": "arbitrage", "desc": "ترکیب بول اسپرد و بیر اسپرد بدون ریسک"},
}


class StrategySettingsDialog(QDialog):
    """
    پنجره یکپارچه تنظیم و فعال‌سازی استراتژی‌ها + تعیین دامنه بازه‌ها و شروط سودآوری
    با بازنشانی صحیح و همگام‌سازی کامل بین تب‌ها
    """
    strategies_updated = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🎯 تنظیمات و فیلترهای هوشمند استراتژی‌ها")
        self.resize(900, 680)
        self.setMinimumSize(800, 550)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._active_states: Dict[str, bool] = {}
        self._filter_configs: Dict[str, Dict[str, Any]] = {}
        self._card_controls: Dict[str, List[Dict[str, Any]]] = {}

        self._load_saved_data()
        self._init_ui()

    def _load_saved_data(self):
        cfg = settings_manager.get_active_settings()
        active_list = cfg.get("active_strategies", None)
        if active_list is None:
            active_list = getattr(config, "ACTIVE_STRATEGIES", list(STRATEGY_DEFINITIONS.keys()))
        active_set = set(active_list)

        for k in STRATEGY_DEFINITIONS.keys():
            self._active_states[k] = (k in active_set)

        saved_filters = cfg.get("strategy_filters", {})
        default_filters = get_default_filter_config()
        for k, v in default_filters.items():
            self._filter_configs[k] = dict(v)
            if k in saved_filters:
                self._filter_configs[k].update(saved_filters[k])

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # هدر بالایی
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #0d419d);
                border-radius: 5px;
                padding: 6px 10px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_title = QLabel("🎯 انتخاب استراتژی‌ها و تنظیم دامنه‌های سودآوری")
        lbl_title.setStyleSheet("color: white; font-size: 12px; font-weight: bold;")
        h_layout.addWidget(lbl_title)
        
        self.lbl_counter = QLabel()
        self.lbl_counter.setStyleSheet("color: #e6edf3; font-weight: bold; font-size: 11px;")
        h_layout.addWidget(self.lbl_counter, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(header_frame)

        # نوار ابزار انتخاب سریع
        quick_bar = QHBoxLayout()
        btn_all = QPushButton("✓ انتخاب همه")
        btn_all.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_all.clicked.connect(self._select_all)
        
        btn_none = QPushButton("✗ لغو انتخاب همه")
        btn_none.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_none.clicked.connect(self._deselect_all)
        
        quick_bar.addWidget(btn_all)
        quick_bar.addWidget(btn_none)
        quick_bar.addStretch()
        layout.addLayout(quick_bar)

        # تب‌های دسته‌بندی
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 5px; padding: 4px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 6px 14px; margin-right: 3px; border-radius: 4px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #1f6feb; color: white; }
        """)

        categories = [
            ("📑 همه استراتژی‌ها", None),
            ("📈 صعودی (Bullish)", "bullish"),
            ("📉 نزولی (Bearish)", "bearish"),
            ("⚖️ خنثی (Neutral)", "neutral"),
            ("⚡ نوسان‌گیری (Volatility)", "volatility"),
            ("🔒 آربیتراژ (Arbitrage)", "arbitrage"),
        ]

        for title, cat_key in categories:
            self.tab_widget.addTab(self._create_category_tab(cat_key), title)

        layout.addWidget(self.tab_widget, stretch=1)

        # نوار دکمه‌های پایین
        bottom_bar = QHBoxLayout()
        
        btn_save = QPushButton("💾 ذخیره و اعمال تغییرات")
        btn_save.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 20px; border-radius: 5px; font-size: 11px;")
        btn_save.clicked.connect(self._save_all)
        bottom_bar.addWidget(btn_save)

        btn_defaults = QPushButton("🔄 بازنشانی فیلترها به پیش‌فرض")
        btn_defaults.setStyleSheet("padding: 6px 12px; font-size: 11px;")
        btn_defaults.clicked.connect(self._reset_filters_to_defaults)
        bottom_bar.addWidget(btn_defaults)

        btn_cancel = QPushButton("انصراف")
        btn_cancel.setStyleSheet("padding: 6px 12px; font-size: 11px;")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)

        self._update_counter_label()

    def _create_category_tab(self, category_key: Optional[str]) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        filtered = [
            (k, v) for k, v in STRATEGY_DEFINITIONS.items()
            if category_key is None or v["cat"] == category_key
        ]

        for strat_key, strat_info in filtered:
            card = self._create_interactive_strategy_card(strat_key, strat_info)
            layout.addWidget(card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _create_interactive_strategy_card(self, strat_key: str, info: Dict[str, Any]) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1c2128;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 4px;
            }
        """)
        main_box = QVBoxLayout(frame)
        main_box.setSpacing(4)
        main_box.setContentsMargins(4, 4, 4, 4)

        # ۱. هدر کارت
        header_layout = QHBoxLayout()
        chk = QCheckBox()
        chk.setChecked(self._active_states.get(strat_key, True))
        chk.setStyleSheet("QCheckBox::indicator { width: 16px; height: 16px; }")

        lbl_title = QLabel(
            f"<span style='color: #58a6ff; font-weight: bold; font-size: 11px;'>{info['en']}</span> "
            f"<span style='color: #cdd9e5; font-weight: bold; font-size: 11px;'>({info['fa']})</span> "
            f"<span style='color: #8b949e; font-size: 10px;'>— {info['desc']}</span>"
        )
        lbl_title.setTextFormat(Qt.TextFormat.RichText)

        header_layout.addWidget(chk)
        header_layout.addWidget(lbl_title, stretch=1)
        main_box.addLayout(header_layout)

        # ۲. پنل تنظیم فیلترهای بازه
        sub_panel = QFrame()
        sub_panel.setStyleSheet("background-color: #161b22; border: 1px dashed #30363d; border-radius: 4px; padding: 2px;")
        grid = QGridLayout(sub_panel)
        grid.setContentsMargins(6, 4, 6, 4)
        grid.setSpacing(4)

        cfg = self._filter_configs.get(strat_key, {})
        rule_type = cfg.get("rule_type", "outside_range")

        ctrl_dict = {"chk": chk, "panel": sub_panel, "inputs": {}}

        if rule_type == "outside_range":
            lbl_rule = QLabel("💡 <b>بازه مجاز زیان:</b> از")
            spin_min = self._create_spin(-30.0, 0.0, cfg.get("loss_range_min", -5.0), " ٪", strat_key, "loss_range_min")
            lbl_to = QLabel("تا")
            spin_max = self._create_spin(0.0, 30.0, cfg.get("loss_range_max", 5.0), " ٪", strat_key, "loss_range_max")
            lbl_after = QLabel("(بیرون از این بازه، استراتژی باید سودده باشد)")
            lbl_profit = QLabel("حداقل درصد سود:")
            spin_prof = self._create_spin(0.0, 100.0, cfg.get("min_profit_pct", 2.0), " ٪", strat_key, "min_profit_pct")

            grid.addWidget(lbl_rule, 0, 0)
            grid.addWidget(spin_min, 0, 1)
            grid.addWidget(lbl_to, 0, 2)
            grid.addWidget(spin_max, 0, 3)
            grid.addWidget(lbl_after, 0, 4)

            grid.addWidget(lbl_profit, 1, 0)
            grid.addWidget(spin_prof, 1, 1)

            ctrl_dict["inputs"] = {
                "rule_type": "outside_range",
                "loss_range_min": spin_min,
                "loss_range_max": spin_max,
                "min_profit_pct": spin_prof,
                "use_dte_factor": True
            }

        elif rule_type == "inside_range":
            lbl_rule = QLabel("💡 <b>دامنه امن سودآوری:</b> از")
            spin_min = self._create_spin(-45.0, 0.0, cfg.get("profit_range_min", -8.0), " ٪", strat_key, "profit_range_min")
            lbl_to = QLabel("تا")
            spin_max = self._create_spin(0.0, 45.0, cfg.get("profit_range_max", 8.0), " ٪", strat_key, "profit_range_max")
            lbl_profit = QLabel("حداقل درصد سود داخل بازه:")
            spin_prof = self._create_spin(0.0, 100.0, cfg.get("min_profit_pct", 3.0), " ٪", strat_key, "min_profit_pct")

            grid.addWidget(lbl_rule, 0, 0)
            grid.addWidget(spin_min, 0, 1)
            grid.addWidget(lbl_to, 0, 2)
            grid.addWidget(spin_max, 0, 3)
            grid.addWidget(lbl_profit, 1, 0)
            grid.addWidget(spin_prof, 1, 1)

            ctrl_dict["inputs"] = {
                "rule_type": "inside_range",
                "profit_range_min": spin_min,
                "profit_range_max": spin_max,
                "min_profit_pct": spin_prof,
                "use_dte_factor": True
            }

        elif rule_type == "above_level":
            lbl_rule = QLabel("💡 <b>شرط سودآوری در تغییر قیمت بالاتر از:</b>")
            spin_above = self._create_spin(-30.0, 30.0, cfg.get("profit_above_pct", -4.5), " ٪", strat_key, "profit_above_pct")
            lbl_profit = QLabel("حداقل درصد بازدهی:")
            spin_prof = self._create_spin(0.0, 100.0, cfg.get("min_profit_pct", 2.5), " ٪", strat_key, "min_profit_pct")

            grid.addWidget(lbl_rule, 0, 0)
            grid.addWidget(spin_above, 0, 1)
            grid.addWidget(lbl_profit, 0, 2)
            grid.addWidget(spin_prof, 0, 3)

            ctrl_dict["inputs"] = {
                "rule_type": "above_level",
                "profit_above_pct": spin_above,
                "min_profit_pct": spin_prof,
                "use_dte_factor": True
            }

        elif rule_type == "below_level":
            lbl_rule = QLabel("💡 <b>شرط سودآوری در تغییر قیمت پایین‌تر از:</b>")
            spin_below = self._create_spin(-30.0, 30.0, cfg.get("profit_below_pct", -3.0), " ٪", strat_key, "profit_below_pct")
            lbl_profit = QLabel("حداقل درصد بازدهی:")
            spin_prof = self._create_spin(0.0, 100.0, cfg.get("min_profit_pct", 5.0), " ٪", strat_key, "min_profit_pct")

            grid.addWidget(lbl_rule, 0, 0)
            grid.addWidget(spin_below, 0, 1)
            grid.addWidget(lbl_profit, 0, 2)
            grid.addWidget(spin_prof, 0, 3)

            ctrl_dict["inputs"] = {
                "rule_type": "below_level",
                "profit_below_pct": spin_below,
                "min_profit_pct": spin_prof,
                "use_dte_factor": True
            }

        main_box.addWidget(sub_panel)

        # همگام‌سازی وضعیت چک‌باکس با تمام تب‌ها
        def _on_chk_toggled(checked: bool):
            self._active_states[strat_key] = checked
            for c in self._card_controls.get(strat_key, []):
                if c["chk"] is not chk:
                    c["chk"].blockSignals(True)
                    c["chk"].setChecked(checked)
                    c["chk"].blockSignals(False)
                c["panel"].setVisible(checked)
            self._update_counter_label()

        chk.toggled.connect(_on_chk_toggled)
        sub_panel.setVisible(chk.isChecked())

        if strat_key not in self._card_controls:
            self._card_controls[strat_key] = []
        self._card_controls[strat_key].append(ctrl_dict)

        return frame

    def _create_spin(self, min_v: float, max_v: float, val: float, suffix: str, strat_key: str, field_name: str) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(min_v, max_v)
        s.setValue(val)
        s.setSingleStep(0.5)
        s.setDecimals(1)
        s.setSuffix(suffix)
        s.setMaximumHeight(24)

        # همگام‌سازی اسپین‌باکس‌ها بین تب‌های مختلف
        def _sync_val(new_val: float):
            if strat_key not in self._filter_configs:
                self._filter_configs[strat_key] = {}
            self._filter_configs[strat_key][field_name] = new_val

            for c in self._card_controls.get(strat_key, []):
                other_spin = c["inputs"].get(field_name)
                if isinstance(other_spin, QDoubleSpinBox) and other_spin is not s:
                    other_spin.blockSignals(True)
                    other_spin.setValue(new_val)
                    other_spin.blockSignals(False)

        s.valueChanged.connect(_sync_val)
        return s

    def _update_counter_label(self):
        active_count = sum(1 for is_a in self._active_states.values() if is_a)
        total = len(STRATEGY_DEFINITIONS)
        self.lbl_counter.setText(f"استراتژی‌های فعال: {active_count} از {total}")

    def _select_all(self):
        for key in STRATEGY_DEFINITIONS.keys():
            self._active_states[key] = True
            for c in self._card_controls.get(key, []):
                c["chk"].blockSignals(True)
                c["chk"].setChecked(True)
                c["chk"].blockSignals(False)
                c["panel"].setVisible(True)
        self._update_counter_label()

    def _deselect_all(self):
        for key in STRATEGY_DEFINITIONS.keys():
            self._active_states[key] = False
            for c in self._card_controls.get(key, []):
                c["chk"].blockSignals(True)
                c["chk"].setChecked(False)
                c["chk"].blockSignals(False)
                c["panel"].setVisible(False)
        self._update_counter_label()

    def _save_all(self):
        active_strategies = [k for k, is_a in self._active_states.items() if is_a]
        if not active_strategies:
            QMessageBox.warning(self, "هشدار", "حداقل یک استراتژی باید برای اسکن انتخاب شود.")
            return

        new_filters = {}
        for key, ctrl_list in self._card_controls.items():
            if not ctrl_list:
                continue
            inputs = ctrl_list[0]["inputs"]
            entry = {"enabled": self._active_states.get(key, True)}
            for field, widget in inputs.items():
                if isinstance(widget, QDoubleSpinBox):
                    entry[field] = widget.value()
                else:
                    entry[field] = widget
            new_filters[key] = entry

        current_cfg = settings_manager.get_active_settings()
        current_cfg["active_strategies"] = active_strategies
        current_cfg["strategy_filters"] = new_filters
        settings_manager.save_settings(current_cfg)

        config.ACTIVE_STRATEGIES = active_strategies
        self.strategies_updated.emit(active_strategies)

        logger.info(f"Saved {len(active_strategies)} active strategies and custom profit intervals")
        QMessageBox.information(
            self,
            "ذخیره موفق",
            f"✅ استراتژی‌ها ({len(active_strategies)} مورد) و دامنه‌های سودآوری با موفقیت ذخیره شدند."
        )
        self.accept()

    def _reset_filters_to_defaults(self):
        defaults = get_default_filter_config()
        self._filter_configs = {k: dict(v) for k, v in defaults.items()}

        for key, ctrl_list in self._card_controls.items():
            d = defaults.get(key, {})
            self._active_states[key] = True

            for c in ctrl_list:
                c["chk"].blockSignals(True)
                c["chk"].setChecked(True)
                c["chk"].blockSignals(False)
                c["panel"].setVisible(True)

                inputs = c["inputs"]
                for field, widget in inputs.items():
                    if isinstance(widget, QDoubleSpinBox) and field in d:
                        widget.blockSignals(True)
                        widget.setValue(float(d[field]))
                        widget.blockSignals(False)

        self._update_counter_label()
        logger.info("All strategy filters and states successfully reset to defaults")
        QMessageBox.information(
            self,
            "بازنشانی موفق",
            "🔄 تمام تنظیمات و دامنه‌های سودآوری به حالت پیش‌فرض بازنشانی شدند."
        )