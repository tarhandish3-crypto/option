# ui/strategy_settings_dialog.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QFrame, QScrollArea, 
    QWidget, QGridLayout, QMessageBox, QTabWidget
)
from PySide6.QtCore import Qt, Signal

from ui.settings_manager import settings_manager
import config

logger = logging.getLogger("OptionScanner.UI.StrategySettings")

# =========================================================================
# تعاریف استاندارد استراتژی‌ها با نام انگلیسی، نام فارسی، توضیحات و دسته‌بندی
# =========================================================================

STRATEGY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "covered_call": {
        "en": "Covered Call",
        "fa": "کاور کال",
        "desc": "خرید سهام پایه + فروش اختیار خرید",
        "categories": ["bullish", "neutral_income"]
    },
    "bull_call_spread": {
        "en": "Bull Call Spread",
        "fa": "اسپرد صعودی خرید",
        "desc": "خرید کال با اعمال پایین‌تر + فروش کال با اعمال بالاتر",
        "categories": ["bullish"]
    },
    "bear_put_spread": {
        "en": "Bear Put Spread",
        "fa": "اسپرد نزولی فروش",
        "desc": "خرید پوت با اعمال بالاتر + فروش پوت با اعمال پایین‌تر",
        "categories": ["bearish"]
    },
    "iron_condor": {
        "en": "Iron Condor",
        "fa": "کندور آهنی",
        "desc": "فروش همزمان اسپرد کال و پوت جهت کسب درآمد در بازار خنثی",
        "categories": ["neutral_income"]
    },
    "long_straddle": {
        "en": "Long Straddle",
        "fa": "استرادل خرید",
        "desc": "خرید همزمان کال و پوت ATM جهت نوسان‌گیری شدید در هر دو جهت",
        "categories": ["volatility"]
    },
    "long_strangle": {
        "en": "Long Strangle",
        "fa": "استرانگل خرید",
        "desc": "خرید همزمان کال OTM و پوت OTM با هزینه کمتر جهت نوسان‌گیری شدید",
        "categories": ["volatility"]
    },
    "collar": {
        "en": "Collar",
        "fa": "کالار",
        "desc": "خرید سهم + خرید پوت بیمه + فروش کال جهت پوشش هزینه بیمه",
        "categories": ["bullish", "neutral_income"]
    },
    "conversion": {
        "en": "Conversion",
        "fa": "کانورژن",
        "desc": "خرید سهم + خرید پوت + فروش کال جهت آربیتراژ قطعی بدون ریسک",
        "categories": ["arbitrage"]
    },
    "married_put": {
        "en": "Married Put",
        "fa": "مرید پوت",
        "desc": "خرید همزمان سهم پایه + پوت بیمه جهت حفظ ۱۰۰٪ اصل سرمایه",
        "categories": ["bullish"]
    },
    "long_box": {
        "en": "Long Box",
        "fa": "باکس خرید",
        "desc": "ترکیب بول اسپرد و بیر اسپرد برای آربیتراژ نرخ بهره بدون ریسک",
        "categories": ["arbitrage"]
    },
    "long_guts": {
        "en": "Long Guts",
        "fa": "گاتس خرید",
        "desc": "خرید همزمان کال ITM و پوت ITM جهت نوسان‌گیری عمیق",
        "categories": ["volatility"]
    },
    "strap": {
        "en": "Strap",
        "fa": "استرپ",
        "desc": "خرید ۲ واحد کال + ۱ واحد پوت جهت نوسان‌گیری با گرایش صعودی",
        "categories": ["volatility", "bullish"]
    },
    "strip": {
        "en": "Strip",
        "fa": "استریپ",
        "desc": "خرید ۲ واحد پوت + ۱ واحد کال جهت نوسان‌گیری با گرایش نزولی",
        "categories": ["volatility", "bearish"]
    },
    "long_call": {
        "en": "Long Call",
        "fa": "خرید اختیار خرید",
        "desc": "سود از جهش صعودی با اهرم بالا و ریسک محدود به پریمیوم",
        "categories": ["bullish"]
    },
    "short_call": {
        "en": "Short Call",
        "fa": "فروش اختیار خرید عریان",
        "desc": "کسب درآمد پریمیوم با تعهد فروش سهم (ریسک نامحدود)",
        "categories": ["bearish", "neutral_income"]
    },
    "long_put": {
        "en": "Long Put",
        "fa": "خرید اختیار فروش",
        "desc": "سود از ریزش قیمت دارایی پایه با ریسک محدود به پریمیوم",
        "categories": ["bearish"]
    },
    "short_put": {
        "en": "Short Put",
        "fa": "فروش اختیار فروش عریان",
        "desc": "کسب درآمد پریمیوم یا خرید سهم با تخفیف در قیمت‌های پایین",
        "categories": ["bullish", "neutral_income"]
    },
}


class StrategySettingsDialog(QDialog):
    """
    پنجره مدیریت و فعال/غیرفعال‌سازی استراتژی‌های معاملاتی با ساختار تب‌بندی‌شده و نامگذاری استاندارد
    """
    strategies_updated = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🎯 تنظیمات و فیلتر استراتژی‌های اسکنر")
        self.resize(780, 620)
        self.setMinimumSize(680, 520)

        # نگهداری وضعیت مرکزی تیک‌ها و نمونه‌های چک‌باکس در تب‌های مختلف
        self._strategy_states: Dict[str, bool] = {}
        self._checkbox_instances: Dict[str, List[QCheckBox]] = {k: [] for k in STRATEGY_DEFINITIONS.keys()}

        self._init_ui()
        self._load_active_strategies()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── ۱. هدر شیشه‌ای و توضیحات ──
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #1158c7);
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)

        info_box = QVBoxLayout()
        lbl_title = QLabel("🎯 مدیریت و گزینش استراتژی‌های فعال اسکنر")
        lbl_title.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        lbl_desc = QLabel("استراتژی‌های مدنظر خود را بر اساس رویکرد بازار انتخاب کنید تا در چرخه اسکن محاسبه شوند.")
        lbl_desc.setStyleSheet("color: #e6edf3; font-size: 11px;")
        info_box.addWidget(lbl_title)
        info_box.addWidget(lbl_desc)
        header_layout.addLayout(info_box)

        header_layout.addStretch()

        self.lbl_active_counter = QLabel("فعال: ۰ از ۱۷")
        self.lbl_active_counter.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.25);
            color: #ffffff;
            font-weight: bold;
            font-size: 12px;
            border-radius: 5px;
            padding: 4px 10px;
        """)
        header_layout.addWidget(self.lbl_active_counter)

        layout.addWidget(header_frame)

        # ── ۲. نوار ابزار انتخاب سریع ──
        quick_bar = QHBoxLayout()
        
        btn_select_all = QPushButton("✓ انتخاب همه")
        btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_select_all.setStyleSheet("padding: 5px 12px; font-size: 11px; font-weight: bold;")
        btn_select_all.clicked.connect(self._select_all)
        
        btn_deselect_all = QPushButton("✗ لغو انتخاب همه")
        btn_deselect_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_deselect_all.setStyleSheet("padding: 5px 12px; font-size: 11px; font-weight: bold;")
        btn_deselect_all.clicked.connect(self._deselect_all)

        quick_bar.addWidget(btn_select_all)
        quick_bar.addWidget(btn_deselect_all)
        quick_bar.addStretch()
        layout.addLayout(quick_bar)

        # ── ۳. ساخت تب‌های دسته‌بندی استراتژی‌ها ──
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #30363d;
                background: #161b22;
                border-radius: 6px;
                padding: 4px;
            }
            QTabBar::tab {
                background: #21262d;
                color: #8b949e;
                padding: 8px 14px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #388bfd;
                color: #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background: #30363d;
                color: #cdd9e5;
            }
        """)

        categories = [
            ("📑 همه استراتژی‌ها", None),
            ("📈 صعودی (Bullish)", "bullish"),
            ("📉 نزولی (Bearish)", "bearish"),
            ("⚖️ خنثی و درآمدی (Neutral)", "neutral_income"),
            ("⚡ نوسان‌گیری شدید (Volatility)", "volatility"),
            ("🔒 آربیتراژ و بدون ریسک (Arbitrage)", "arbitrage"),
        ]

        for tab_title, cat_filter in categories:
            tab_widget = self._create_category_tab(cat_filter)
            self.tab_widget.addTab(tab_widget, tab_title)

        layout.addWidget(self.tab_widget, stretch=1)

        # ── ۴. دکمه‌های تایید و ذخیره ──
        bottom_bar = QHBoxLayout()
        
        self.btn_save = QPushButton("💾 ذخیره و اعمال تنظیمات")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_save.clicked.connect(self._save_settings)
        bottom_bar.addWidget(self.btn_save)

        btn_cancel = QPushButton("انصراف")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("padding: 8px 16px; border-radius: 5px;")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)

    def _create_category_tab(self, category_key: Optional[str]) -> QWidget:
        """ساخت محتوای هر تب با فیلتر دسته‌بندی مشخص"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: #161b22;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        filtered_items = [
            (k, v) for k, v in STRATEGY_DEFINITIONS.items()
            if category_key is None or category_key in v["categories"]
        ]

        for strat_key, strat_info in filtered_items:
            card = self._create_strategy_item_card(strat_key, strat_info)
            layout.addWidget(card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _create_strategy_item_card(self, strat_key: str, strat_info: Dict[str, Any]) -> QFrame:
        """ساخت کارت نمایش استراتژی با فرمت: نام انگلیسی (نام فارسی) — توضیحات"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1c2128;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QFrame:hover {
                border-color: #58a6ff;
                background-color: #22272e;
            }
        """)
        card_layout = QHBoxLayout(frame)
        card_layout.setContentsMargins(6, 4, 6, 4)

        chk = QCheckBox()
        chk.setStyleSheet("QCheckBox::indicator { width: 17px; height: 17px; }")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._checkbox_instances[strat_key].append(chk)
        chk.toggled.connect(lambda checked, k=strat_key: self._on_checkbox_toggled(k, checked))

        lbl_text = QLabel()
        lbl_text.setTextFormat(Qt.TextFormat.RichText)
        lbl_text.setText(
            f"<span style='color: #58a6ff; font-weight: bold; font-size: 12px;'>{strat_info['en']}</span> "
            f"<span style='color: #cdd9e5; font-weight: 500;'>({strat_info['fa']})</span> "
            f"<span style='color: #768390;'>— {strat_info['desc']}</span>"
        )
        lbl_text.setStyleSheet("background: transparent; border: none;")

        card_layout.addWidget(chk)
        card_layout.addWidget(lbl_text, stretch=1)
        return frame

    def _on_checkbox_toggled(self, strat_key: str, checked: bool):
        """همگام‌سازی وضعیت چک‌باکس یک استراتژی در تمام تب‌ها"""
        self._strategy_states[strat_key] = checked
        for chk in self._checkbox_instances.get(strat_key, []):
            chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(False)
        self._update_counter_label()

    def _update_counter_label(self):
        active_count = sum(1 for is_active in self._strategy_states.values() if is_active)
        total_count = len(STRATEGY_DEFINITIONS)
        self.lbl_active_counter.setText(f"فعال: {active_count} از {total_count}")

    def _load_active_strategies(self):
        """بارگذاری استراتژی‌های فعال از تنظیمات ذخیره‌شده"""
        active = settings_manager.get_active_settings().get("active_strategies", None)
        if active is None:
            active = getattr(config, "ACTIVE_STRATEGIES", list(STRATEGY_DEFINITIONS.keys()))

        active_set = set(active)
        for key in STRATEGY_DEFINITIONS.keys():
            is_active = (key in active_set)
            self._strategy_states[key] = is_active
            for chk in self._checkbox_instances.get(key, []):
                chk.blockSignals(True)
                chk.setChecked(is_active)
                chk.blockSignals(False)

        self._update_counter_label()

    def _select_all(self):
        for key in STRATEGY_DEFINITIONS.keys():
            self._on_checkbox_toggled(key, True)

    def _deselect_all(self):
        for key in STRATEGY_DEFINITIONS.keys():
            self._on_checkbox_toggled(key, False)

    def _save_settings(self):
        """ذخیره دائمی تنظیمات و نمایش پیغام تایید کاربرپسند"""
        selected = [key for key, is_active in self._strategy_states.items() if is_active]
        if not selected:
            QMessageBox.warning(self, "هشدار", "حداقل یک استراتژی باید برای اسکن فعال باشد.")
            return

        current_cfg = settings_manager.get_active_settings()
        current_cfg["active_strategies"] = selected
        settings_manager.save_settings(current_cfg)

        config.ACTIVE_STRATEGIES = selected

        self.strategies_updated.emit(selected)
        logger.info(f"Active strategies saved successfully: {selected}")

        QMessageBox.information(
            self,
            "ذخیره موفق",
            f"✅ تنظیمات با موفقیت ذخیره شد.\n\nتعداد {len(selected)} استراتژی برای فرآیند اسکن بازار فعال گردید."
        )
        self.accept()