# position_saver/ui/dialogs.py
# -*- coding: utf-8 -*-

import re
import sys
import time
import logging
import jdatetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QMessageBox, QHeaderView,
    QGroupBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QDialogButtonBox, QRadioButton, QAbstractSpinBox,
)
from PySide6.QtCore import Qt, QEvent, QPoint, QRegularExpression
from PySide6.QtGui import (
    QRegularExpressionValidator,
)

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,
)
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.theme import (
    CURRENCY, QSS,
    fmt_money, fmt_pct, fmt_int, pnl_tone,
    set_kind, set_tone, set_invalid,
)

from position_saver.providers import get_market_snapshot, get_setting
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.Dialogs")


# =====================================================
# کارگزاری‌های پیش‌فرض
# =====================================================

BROKER_NAMES = ["مفید", "خبرگان سهام", "پیشرو", "پارسیان", "سایر"]
DEFAULT_BROKER = "مفید"


# =====================================================
# تغییر زبان کیبورد (ویندوز) — قابل غیرفعال‌سازی
# =====================================================

# اگر این متغیر True باشد، دیالوگ‌ها کیبورد را به فارسی تغییر می‌دهند.
# می‌توان از بیرون (مثلاً از تنظیمات کاربر) آن را False کرد.
AUTO_SWITCH_KEYBOARD = True


def switch_to_persian_keyboard() -> None:
    """تغییر زبان کیبورد به فارسی — فقط اگر فعال باشد"""
    if not AUTO_SWITCH_KEYBOARD:
        return
    if sys.platform == "win32":
        try:
            import win32api
            import win32con
            PERSIAN_LAYOUT_ID = 0x0429
            win32api.LoadKeyboardLayout(
                f"{PERSIAN_LAYOUT_ID:08x}", win32con.KLF_ACTIVATE)
        except Exception as e:
            logger.debug(f"[Keyboard] Failed to switch: {e}")


# =====================================================
# نرمال‌سازی و پاکسازی ورودی نماد
# =====================================================

def normalize_symbol(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    s = s.replace('ي', 'ی').replace('ك', 'ک')
    s = s.replace("\u200c", " ")
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


_SYMBOL_INVALID_CHARS = re.compile(r'[^\u0600-\u06FF\u200cA-Za-z0-9 ]')


def sanitize_symbol_input(text: str) -> str:
    if not text:
        return text
    return _SYMBOL_INVALID_CHARS.sub('', text)


# =====================================================
# تابع کمکی: قیمت پایانی سهم پایه از snapshot
# =====================================================

def _get_underlying_closing_price(
    snapshot, underlying_ticker: str
) -> float:
    """گرفتن قیمت پایانی سهم پایه (اول close_price)"""
    if snapshot is None or not underlying_ticker:
        return 0.0
    try:
        ua = snapshot.get_underlying_assets(underlying_ticker)
        if ua is not None:
            if hasattr(ua, 'close_price') and ua.close_price > 0:
                return float(ua.close_price)
            if hasattr(ua, 'last_price') and ua.last_price > 0:
                return float(ua.last_price)
    except Exception as e:
        logger.debug(f"Failed to get closing price: {e}")
    return 0.0


# =====================================================
# شناسه ستون‌ها
# =====================================================

COL_SYMBOL = 0
COL_KIND = 1
COL_SIDE = 2
COL_STRIKE = 3
COL_QTY = 4
COL_ENTRY = 5
COL_CURRENT = 6
COL_EXPIRY = 7
N_LEG_COLS = 8


# =====================================================
# اعتبارسنجی تاریخ شمسی
# =====================================================

def _make_date_validator() -> QRegularExpressionValidator:
    """ساخت Validator برای تاریخ شمسی YYYY/MM/DD"""
    pattern = QRegularExpression(
        r'^\d{0,4}(/\d{0,2}(/\d{0,2})?)?$'
    )
    return QRegularExpressionValidator(pattern)


# =====================================================
# ✅ بازنویسی detect_strategy_name — حالا فقط wrapper است
# =====================================================

def detect_strategy_name(legs: List[OptionLeg]) -> str:
    """
    تشخیص خودکار نام استراتژی — به PositionPnLCalculator واگذار شده.

    این تابع فقط برای backward compatibility نگه داشته شده.
    در کد جدید از PositionPnLCalculator.suggest_strategy_name استفاده کنید.
    """
    return PositionPnLCalculator.suggest_strategy_name(legs)


# =====================================================
# لیست Autocomplete
# =====================================================

class SymbolCompleter(QListWidget):
    """لیست شناور برای autocomplete نمادها"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.ToolTip |
            Qt.FramelessWindowHint |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)

        self._on_select_callback = None
        self._all_items: List[Dict[str, Any]] = []
        self._last_symbols: List[str] = []

        self.itemClicked.connect(self._on_item_activated)
        self.itemActivated.connect(self._on_item_activated)

    def set_source(self, items: List[Dict[str, Any]]):
        self._all_items = items

    def attach_callback(self, on_select):
        self._on_select_callback = on_select

    def filter_and_show(self, prefix: str, global_pos: QPoint, width: int):
        prefix = prefix.strip()
        if not prefix:
            self._hide_list()
            return

        prefix_lower = prefix.lower()

        matches = [
            item for item in self._all_items
            if item["search_key"].startswith(prefix_lower)
        ]
        matches.sort(key=lambda x: x["symbol"])
        matches = matches[:30]

        if not matches:
            self._hide_list()
            return

        new_symbols = [m["symbol"] for m in matches]

        if new_symbols != self._last_symbols:
            self.blockSignals(True)
            self.clear()
            for item in matches:
                list_item = QListWidgetItem(item["symbol"])
                list_item.setData(Qt.UserRole, item)
                self.addItem(list_item)
            self.setCurrentRow(0)
            self.blockSignals(False)
            self._last_symbols = new_symbols

        self.setFixedWidth(max(width, 220))
        row_height = 24
        visible_rows = min(len(matches), 10)
        self.setFixedHeight(visible_rows * row_height + 8)
        self.move(global_pos)

        if not self.isVisible():
            self.show()
            self.raise_()

    def _hide_list(self):
        if self.isVisible():
            self.hide()
        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)
        self._last_symbols = []
        self.setCurrentRow(-1)

    def _on_item_activated(self, list_item: QListWidgetItem):
        data = list_item.data(Qt.UserRole)
        if data and self._on_select_callback:
            self._on_select_callback(data)
        self._hide_list()

    def select_current(self):
        if not self.isVisible():
            return
        current = self.currentItem()
        if current:
            self._on_item_activated(current)

    def move_selection(self, delta: int):
        if not self.isVisible() or self.count() == 0:
            return
        row = self.currentRow() + delta
        if 0 <= row < self.count():
            self.setCurrentRow(row)
        elif row < 0:
            self.setCurrentRow(0)
        elif row >= self.count():
            self.setCurrentRow(self.count() - 1)

    def is_open(self) -> bool:
        return self.isVisible()


# =====================================================
# دیالوگ ثبت / ویرایش موقعیت
# =====================================================

class PositionEditDialog(QDialog):
    """پنجره ثبت / ویرایش موقعیت استراتژی اختیار معامله"""

    def __init__(
        self,
        parent=None,
        position: Optional[StrategyPosition] = None,
        snapshot=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("ثبت / ویرایش موقعیت استراتژی")
        self.setMinimumSize(1100, 620)
        self.setLayoutDirection(Qt.RightToLeft)

        switch_to_persian_keyboard()

        self.position = position or StrategyPosition()
        self.is_new = (position is None)
        self.snapshot = snapshot

        self.symbol_items: List[Dict[str, Any]] = self._build_symbol_items()

        self._completer = SymbolCompleter(self)
        self._completer.attach_callback(self._on_symbol_selected)
        self._completer.set_source(self.symbol_items)

        self._active_line_edit: Optional[QLineEdit] = None

        self.init_ui()
        self.load_position_data()

    # =====================================================
    # Override: پاکسازی هنگام بستن
    # =====================================================

    def closeEvent(self, event):
        self._hide_completer()
        super().closeEvent(event)

    def reject(self):
        self._hide_completer()
        super().reject()

    def accept(self):
        self._hide_completer()
        super().accept()

    def done(self, result):
        self._hide_completer()
        super().done(result)

    # =====================================================
    # کمکی‌ها
    # =====================================================

    def _refresh_row_indices(self):
        for r in range(self.table_legs.rowCount()):
            w = self.table_legs.cellWidget(r, COL_SYMBOL)
            if isinstance(w, QLineEdit):
                w.setProperty("row_index", r)

    def _get_row_of_widget(self, widget) -> int:
        if widget is None:
            return -1

        if isinstance(widget, QLineEdit):
            val = widget.property("row_index")
            if val is not None:
                try:
                    r = int(val)
                    if 0 <= r < self.table_legs.rowCount():
                        return r
                except (TypeError, ValueError):
                    pass

        try:
            pos = widget.mapTo(
                self.table_legs.viewport(), QPoint(0, 0))
            idx = self.table_legs.indexAt(pos)
            return idx.row() if idx.isValid() else -1
        except Exception:
            return -1

    def _hide_completer(self):
        try:
            self._completer._hide_list()
        except Exception:
            pass

    # =====================================================
    # ساخت لیست نمادها
    # =====================================================

    def _build_symbol_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        if self.snapshot is None:
            return items

        seen_options = set()
        for contract in self.snapshot.option_contracts:
            if not contract.ticker:
                continue
            symbol = normalize_symbol(contract.ticker)
            if not symbol or symbol in seen_options:
                continue
            seen_options.add(symbol)

            items.append({
                "symbol": symbol,
                "search_key": symbol.lower(),
                "data": {
                    "is_option": True,
                    "option_kind": contract.option_type,
                    "strike_price": float(contract.strike_price),
                    "contract_size": int(contract.contract_size),
                    "expiry_date": str(contract.expiry_date)
                    if contract.expiry_date else "",
                    "current_price": float(
                        contract.close_price or contract.last_price),
                    "bid_price": float(
                        getattr(contract, 'bid', 0.0) or 0.0),
                    "ask_price": float(
                        getattr(contract, 'ask', 0.0) or 0.0),
                    "last_price": float(
                        getattr(contract, 'last_price', 0.0) or 0.0),
                    "close_price": float(
                        getattr(contract, 'close_price', 0.0) or 0.0),
                    "ins_code": str(contract.instrument_code or ""),
                    "underlying_ticker": normalize_symbol(
                        contract.underlying_ticker or ""),
                },
            })

        underlying_set = set()
        for contract in self.snapshot.option_contracts:
            if contract.underlying_ticker:
                underlying_set.add(
                    normalize_symbol(contract.underlying_ticker))
        for ua_key in self.snapshot.underlying_assets.keys():
            underlying_set.add(normalize_symbol(ua_key))

        for underlying in sorted(underlying_set):
            if not underlying:
                continue
            price = self._lookup_underlying_price(underlying)
            items.append({
                "symbol": underlying,
                "search_key": underlying.lower(),
                "data": {
                    "is_option": False,
                    "option_kind": OptionType.STOCK,
                    "strike_price": 0.0,
                    "contract_size": 1,
                    "expiry_date": "",
                    "current_price": float(price),
                    "bid_price": 0.0,
                    "ask_price": 0.0,
                    "last_price": float(price),
                    "close_price": float(price),
                    "ins_code": "",
                    "underlying_ticker": underlying,
                },
            })

        return items

    def _lookup_underlying_price(self, normalized_ticker: str) -> float:
        if self.snapshot is None:
            return 0.0
        for ua_key, ua in self.snapshot.underlying_assets.items():
            if normalize_symbol(ua_key) == normalized_ticker:
                if hasattr(ua, 'close_price') and ua.close_price > 0:
                    return float(ua.close_price)
                if hasattr(ua, 'last_price') and ua.last_price > 0:
                    return float(ua.last_price)
        return 0.0

    # =====================================================
    # ساخت UI
    # =====================================================

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ─── هشدار منبع ایمپورت (اگر از اکسل آمده) ───
        if self.position.source == "excel_import":
            warning = QLabel(
                f"📥 این موقعیت از ایمپورت اکسل آمده است "
                f"(batch: {self.position.import_batch_id})"
            )
            set_tone(warning, "primary")
            main_layout.addWidget(warning)

        # ─── اطلاعات کلی ───
        info_group = QGroupBox("اطلاعات کلی")
        form_layout = QFormLayout(info_group)

        self.txt_strategy = QLineEdit()
        self.txt_strategy.setPlaceholderText(
            "مثلاً: Covered Call / Bull Call Spread / Long Call")

        # ردیف تشخیص خودکار
        detected_row = QHBoxLayout()

        self.lbl_detected_strategy = QLabel("(پیشنهاد خودکار: —)")
        set_tone(self.lbl_detected_strategy, "muted")

        self.btn_use_suggestion = QPushButton("← استفاده")
        self.btn_use_suggestion.setFixedWidth(90)
        self.btn_use_suggestion.setEnabled(False)
        self.btn_use_suggestion.clicked.connect(self._apply_suggested_strategy)

        detected_row.addWidget(self.lbl_detected_strategy)
        detected_row.addWidget(self.btn_use_suggestion)
        detected_row.addStretch()

        # کارگزاری
        self.cmb_broker = QComboBox()
        self.cmb_broker.setEditable(True)
        self.cmb_broker.addItems(BROKER_NAMES)
        self.cmb_broker.setCurrentText(DEFAULT_BROKER)
        self.cmb_broker.setMinimumWidth(180)
        self.cmb_broker.setInsertPolicy(QComboBox.NoInsert)

        # تاریخ اجرا
        self.txt_exec_date = QLineEdit()
        self.txt_exec_date.setPlaceholderText("1403/01/15")
        self.txt_exec_date.setValidator(_make_date_validator())
        self.txt_exec_date.textChanged.connect(
            self._validate_date_field)

        # حد هشدار
        self.spin_alert_roi = QDoubleSpinBox()
        self.spin_alert_roi.setRange(0.0, 1000.0)
        self.spin_alert_roi.setSuffix(" ٪")
        self.spin_alert_roi.setValue(10.0)
        self.spin_alert_roi.setButtonSymbols(QAbstractSpinBox.NoButtons)

        form_layout.addRow("نام استراتژی:", self.txt_strategy)
        form_layout.addRow("", detected_row)
        form_layout.addRow("کارگزاری:", self.cmb_broker)
        form_layout.addRow("تاریخ اجرا:", self.txt_exec_date)
        form_layout.addRow("حد هشدار بله:", self.spin_alert_roi)

        main_layout.addWidget(info_group)

        # ─── جدول لگ‌ها ───
        legs_group = QGroupBox("لنگه‌های موقعیت")
        legs_layout = QVBoxLayout(legs_group)

        self.table_legs = QTableWidget(0, N_LEG_COLS)
        self.table_legs.setHorizontalHeaderLabels([
            "نماد", "نوع", "موقعیت", "قیمت اعمال",
            "تعداد", "قیمت ورود", "قیمت لحظه‌ای", "تاریخ سررسید",
        ])
        self.table_legs.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_legs.horizontalHeader().setStretchLastSection(True)
        self.table_legs.setColumnWidth(COL_SYMBOL, 240)
        self.table_legs.setColumnWidth(COL_KIND, 80)
        self.table_legs.setColumnWidth(COL_SIDE, 80)
        self.table_legs.setColumnWidth(COL_STRIKE, 110)
        self.table_legs.setColumnWidth(COL_QTY, 80)
        self.table_legs.setColumnWidth(COL_ENTRY, 110)
        self.table_legs.setColumnWidth(COL_CURRENT, 110)
        self.table_legs.setSelectionBehavior(QTableWidget.SelectRows)
        legs_layout.addWidget(self.table_legs)

        # دکمه افزودن لنگه
        btn_row = QHBoxLayout()
        btn_add_leg = QPushButton("➕ افزودن لنگه")
        btn_add_leg.clicked.connect(self.add_leg_row)

        btn_remove_leg = QPushButton("➖ حذف لگ انتخاب‌شده")
        btn_remove_leg.clicked.connect(self.remove_leg_row)

        btn_row.addWidget(btn_add_leg)
        btn_row.addWidget(btn_remove_leg)
        btn_row.addStretch()
        legs_layout.addLayout(btn_row)

        main_layout.addWidget(legs_group)

        # ─── خلاصه زنده ───
        self.lbl_live_summary = QLabel("—")
        set_tone(self.lbl_live_summary, "muted")
        main_layout.addWidget(self.lbl_live_summary)

        # ─── دکمه‌های پایین ───
        bottom_layout = QHBoxLayout()
        btn_save = QPushButton("💾 ذخیره موقعیت")
        btn_save.clicked.connect(self.save_and_close)
        set_kind(btn_save, "primary")

        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)
        main_layout.addLayout(bottom_layout)

    # =====================================================
    # اعتبارسنجی تاریخ
    # =====================================================

    def _validate_date_field(self, text: str):
        if not text.strip():
            set_invalid(self.txt_exec_date, False)
            return

        is_valid = bool(re.match(
            r'^\d{4}/\d{1,2}/\d{1,2}$', text.strip()))

        set_invalid(self.txt_exec_date, not is_valid)

    # =====================================================
    # مدیریت ردیف‌های لگ
    # =====================================================

    def add_leg_row(self, leg: Optional[OptionLeg] = None):
        self._hide_completer()

        row = self.table_legs.rowCount()
        self.table_legs.insertRow(row)

        # ─── ستون ۰: نماد ───
        line_symbol = QLineEdit(leg.symbol if leg else "")
        line_symbol.setPlaceholderText("نام نماد...")

        if leg:
            line_symbol.setProperty("ins_code", leg.ins_code or "")
            line_symbol.setProperty("contract_size", leg.contract_size or 0)
            line_symbol.setProperty("underlying_ticker", "")

        line_symbol.editingFinished.connect(
            lambda le=line_symbol: self._sanitize_symbol_text(le, le.text()))

        line_symbol.textEdited.connect(
            lambda text, le=line_symbol:
                self._on_symbol_text_edited_dynamic(le, text))

        line_symbol.installEventFilter(self)
        line_symbol.focusInEvent = (
            lambda event, le=line_symbol:
                self._on_line_focus_in_dynamic(event, le))

        self.table_legs.setCellWidget(row, COL_SYMBOL, line_symbol)

        # ─── ستون ۱: نوع ───
        cmb_kind = QComboBox()
        cmb_kind.addItem("کال", OptionType.CALL)
        cmb_kind.addItem("پوت", OptionType.PUT)
        cmb_kind.addItem("سهام", OptionType.STOCK)
        if leg:
            idx = cmb_kind.findData(leg.option_kind)
            if idx >= 0:
                cmb_kind.setCurrentIndex(idx)
        cmb_kind.currentIndexChanged.connect(
            lambda _, cmb=cmb_kind: self._on_kind_changed_dynamic(cmb))
        self.table_legs.setCellWidget(row, COL_KIND, cmb_kind)

        # ─── ستون ۲: موقعیت ───
        cmb_side = QComboBox()
        cmb_side.addItem(LegType.BUY.label_fa, LegType.BUY)
        cmb_side.addItem(LegType.SELL.label_fa, LegType.SELL)
        if leg:
            idx = cmb_side.findData(leg.leg_type)
            if idx >= 0:
                cmb_side.setCurrentIndex(idx)
        cmb_side.currentIndexChanged.connect(
            lambda _: self._update_live_summary())
        cmb_side.currentIndexChanged.connect(
            lambda _: self._update_detected_strategy_label())
        cmb_side.currentIndexChanged.connect(
            lambda _, cmb=cmb_side:
                self._update_live_price_for_row(
                    self._get_row_of_widget(cmb)))
        self.table_legs.setCellWidget(row, COL_SIDE, cmb_side)

        # ─── ستون ۳: قیمت اعمال ───
        spin_strike = QSpinBox()
        spin_strike.setRange(0, 1_000_000_000)
        spin_strike.setSingleStep(50)
        spin_strike.setGroupSeparatorShown(True)
        spin_strike.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_strike.setValue(int(leg.strike_price) if leg else 0)
        spin_strike.valueChanged.connect(
            lambda _: self._update_live_summary())
        self.table_legs.setCellWidget(row, COL_STRIKE, spin_strike)

        # ─── ستون ۴: تعداد ───
        spin_qty = QSpinBox()
        spin_qty.setRange(1, 100_000_000)
        spin_qty.setGroupSeparatorShown(True)
        spin_qty.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_qty.setValue(int(leg.quantity) if leg else 1)
        spin_qty.valueChanged.connect(
            lambda _: self._update_live_summary())
        self.table_legs.setCellWidget(row, COL_QTY, spin_qty)

        # ─── ستون ۵: قیمت ورود ───
        spin_entry = QSpinBox()
        spin_entry.setRange(0, 1_000_000_000)
        spin_entry.setSingleStep(10)
        spin_entry.setGroupSeparatorShown(True)
        spin_entry.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_entry.setValue(int(leg.entry_price) if leg else 0)
        spin_entry.valueChanged.connect(
            lambda _: self._update_live_summary())
        self.table_legs.setCellWidget(row, COL_ENTRY, spin_entry)

        # ─── ستون ۶: قیمت لحظه‌ای (خواندنی) ───
        spin_current = QSpinBox()
        spin_current.setRange(0, 1_000_000_000)
        spin_current.setSingleStep(10)
        spin_current.setGroupSeparatorShown(True)
        spin_current.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_current.setEnabled(False)
        spin_current.setValue(int(leg.current_price) if leg else 0)
        self.table_legs.setCellWidget(row, COL_CURRENT, spin_current)

        # ─── ستون ۷: تاریخ سررسید ───
        line_expiry = QLineEdit(leg.expiry_date if leg else "")
        line_expiry.setPlaceholderText("1403/06/20")
        line_expiry.setValidator(_make_date_validator())
        self.table_legs.setCellWidget(row, COL_EXPIRY, line_expiry)

        self._apply_leg_row_state(row)
        self._refresh_row_indices()
        self._update_detected_strategy_label()
        self._update_live_summary()

    def remove_leg_row(self):
        row = self.table_legs.currentRow()
        if row >= 0:
            self._hide_completer()
            self.table_legs.removeRow(row)
            self._refresh_row_indices()
            self._update_detected_strategy_label()
            self._update_live_summary()

    # =====================================================
    # به‌روزرسانی قیمت لحظه‌ای
    # =====================================================

    def _update_live_price_for_row(self, row: int):
        if row < 0 or row >= self.table_legs.rowCount():
            return

        spin_current: QSpinBox = self.table_legs.cellWidget(row, COL_CURRENT)
        if spin_current is None:
            return

        line_symbol: QLineEdit = self.table_legs.cellWidget(row, COL_SYMBOL)
        if line_symbol is None or not line_symbol.text().strip():
            return

        cmb_side: QComboBox = self.table_legs.cellWidget(row, COL_SIDE)
        if cmb_side is None:
            return

        symbol = normalize_symbol(line_symbol.text())
        item_data = None
        for it in self.symbol_items:
            if it["symbol"] == symbol:
                item_data = it["data"]
                break

        if item_data is None:
            return

        leg_type = cmb_side.currentData() or LegType.BUY
        is_option = item_data.get("is_option", False)

        if is_option:
            if leg_type == LegType.BUY:
                price = item_data.get("ask_price", 0)
            else:
                price = item_data.get("bid_price", 0)

            if price <= 0:
                price = item_data.get("last_price", 0)
            if price <= 0:
                price = item_data.get("close_price", 0)
        else:
            price = item_data.get("close_price", 0)
            if price <= 0:
                price = item_data.get("last_price", 0)

        spin_current.setValue(int(price))

    # =====================================================
    # خلاصه زنده
    # =====================================================

    def _update_live_summary(self):
        legs = self._collect_full_legs()
        if not legs:
            self.lbl_live_summary.setText(
                "💡 برای مشاهده خلاصه، لنگه‌ها را وارد کنید")
            set_tone(self.lbl_live_summary, "muted")
            return

        temp_pos = StrategyPosition(
            strategy_name="temp",
            underlying_symbol="",
            legs=legs,
        )

        net_cost = PositionPnLCalculator.calculate_net_entry_cost(temp_pos)

        if net_cost > 0:
            kind = "دبیت (پرداختی)"
            tone = "loss"
        elif net_cost < 0:
            kind = "کردیت (دریافتی)"
            tone = "profit"
        else:
            kind = "خنثی"
            tone = "muted"

        text = (
            f"💰 هزینه خالص ورود: {fmt_money(net_cost)} {CURRENCY}  |  "
            f"نوع: {kind}"
        )
        self.lbl_live_summary.setText(text)
        set_tone(self.lbl_live_summary, tone)

    # =====================================================
    # افزودن سطر جدید و فوکوس
    # =====================================================

    def _add_new_row_and_focus(self):
        self._hide_completer()
        self.add_leg_row()

        new_row = self.table_legs.rowCount() - 1
        new_symbol = self.table_legs.cellWidget(new_row, COL_SYMBOL)
        if isinstance(new_symbol, QLineEdit):
            self.table_legs.setCurrentCell(new_row, COL_SYMBOL)
            new_symbol.setFocus()
            new_symbol.selectAll()
        self.table_legs.scrollToBottom()

    # =====================================================
    # استخراج لگ‌ها
    # =====================================================

    def _collect_legs_from_table(self) -> List[OptionLeg]:
        legs: List[OptionLeg] = []
        for r in range(self.table_legs.rowCount()):
            line_symbol: QLineEdit = self.table_legs.cellWidget(r, COL_SYMBOL)
            cmb_kind: QComboBox = self.table_legs.cellWidget(r, COL_KIND)
            cmb_side: QComboBox = self.table_legs.cellWidget(r, COL_SIDE)
            spin_strike: QSpinBox = self.table_legs.cellWidget(r, COL_STRIKE)

            if line_symbol is None or not line_symbol.text().strip():
                continue

            symbol = normalize_symbol(
                sanitize_symbol_input(line_symbol.text()))
            option_kind = cmb_kind.currentData() or OptionType.STOCK
            leg_type = cmb_side.currentData() or LegType.BUY
            is_option = (option_kind != OptionType.STOCK)

            leg = OptionLeg(
                symbol=symbol,
                is_option=is_option,
                option_kind=option_kind,
                leg_type=leg_type,
                strike_price=spin_strike.value() if is_option else 0.0,
                contract_size=1000 if is_option else 1,
                quantity=1,
                entry_price=0,
                current_price=0,
                expiry_date="",
            )
            legs.append(leg)
        return legs

    def _collect_full_legs(self) -> List[OptionLeg]:
        legs: List[OptionLeg] = []
        for r in range(self.table_legs.rowCount()):
            line_symbol: QLineEdit = self.table_legs.cellWidget(r, COL_SYMBOL)
            cmb_kind: QComboBox = self.table_legs.cellWidget(r, COL_KIND)
            cmb_side: QComboBox = self.table_legs.cellWidget(r, COL_SIDE)
            spin_strike: QSpinBox = self.table_legs.cellWidget(r, COL_STRIKE)
            spin_qty: QSpinBox = self.table_legs.cellWidget(r, COL_QTY)
            spin_entry: QSpinBox = self.table_legs.cellWidget(r, COL_ENTRY)

            if line_symbol is None or not line_symbol.text().strip():
                continue

            symbol = normalize_symbol(
                sanitize_symbol_input(line_symbol.text()))
            option_kind = cmb_kind.currentData() or OptionType.STOCK
            leg_type = cmb_side.currentData() or LegType.BUY
            is_option = (option_kind != OptionType.STOCK)

            cs_prop = line_symbol.property("contract_size")
            try:
                cs_value = int(cs_prop) if cs_prop is not None else 0
            except (TypeError, ValueError):
                cs_value = 0

            contract_size = cs_value if cs_value > 0 else (
                1000 if is_option else 1)

            leg = OptionLeg(
                symbol=symbol,
                is_option=is_option,
                option_kind=option_kind,
                leg_type=leg_type,
                strike_price=spin_strike.value() if is_option else 0.0,
                contract_size=int(contract_size),
                quantity=spin_qty.value(),
                entry_price=spin_entry.value(),
                current_price=spin_entry.value(),
                expiry_date="",
            )
            legs.append(leg)
        return legs

    # =====================================================
    # به‌روزرسانی لیبل پیشنهاد
    # =====================================================

    def _update_detected_strategy_label(self):
        legs = self._collect_legs_from_table()
        if not legs:
            self.lbl_detected_strategy.setText("(پیشنهاد خودکار: —)")
            set_tone(self.lbl_detected_strategy, "muted")
            self.btn_use_suggestion.setEnabled(False)
            return

        suggested = PositionPnLCalculator.suggest_strategy_name(legs)
        if suggested:
            self.lbl_detected_strategy.setText(
                f"(پیشنهاد خودکار: {suggested})")
            set_tone(self.lbl_detected_strategy, "primary")
            self.btn_use_suggestion.setEnabled(True)
        else:
            self.lbl_detected_strategy.setText("(پیشنهاد خودکار: —)")
            set_tone(self.lbl_detected_strategy, "muted")
            self.btn_use_suggestion.setEnabled(False)

    def _apply_suggested_strategy(self):
        legs = self._collect_legs_from_table()
        if not legs:
            return
        suggested = PositionPnLCalculator.suggest_strategy_name(legs)
        if suggested:
            self.txt_strategy.setText(suggested)

    # =====================================================
    # Sanitize
    # =====================================================

    def _sanitize_symbol_text(self, line_edit: QLineEdit, text: str):
        if not text:
            return
        cleaned = sanitize_symbol_input(text)
        if cleaned != text:
            cursor_pos = line_edit.cursorPosition()
            line_edit.blockSignals(True)
            line_edit.setText(cleaned)
            line_edit.setCursorPosition(min(cursor_pos, len(cleaned)))
            line_edit.blockSignals(False)

    # =====================================================
    # تغییر نوع لگ
    # =====================================================

    def _on_kind_changed_dynamic(self, cmb_kind: QComboBox):
        row = self._get_row_of_widget(cmb_kind)
        if row >= 0:
            self._apply_leg_row_state(row)
        self._update_detected_strategy_label()
        self._update_live_summary()

    def _apply_leg_row_state(self, row: int):
        cmb_kind: QComboBox = self.table_legs.cellWidget(row, COL_KIND)
        spin_strike: QSpinBox = self.table_legs.cellWidget(row, COL_STRIKE)
        line_expiry: QLineEdit = self.table_legs.cellWidget(row, COL_EXPIRY)

        if cmb_kind is None or spin_strike is None or line_expiry is None:
            return

        option_kind = cmb_kind.currentData()

        if option_kind == OptionType.STOCK:
            spin_strike.setEnabled(False)
            spin_strike.setValue(0)
            line_expiry.setEnabled(False)
            line_expiry.setText("")
        else:
            spin_strike.setEnabled(True)
            line_expiry.setEnabled(True)

    # =====================================================
    # Autocomplete
    # =====================================================

    def _on_line_focus_in_dynamic(self, event, line_edit: QLineEdit):
        self._active_line_edit = line_edit

        text = line_edit.text().strip()
        if text and self._should_open_list(text):
            self._show_completer_for(line_edit, text)
        else:
            self._hide_completer()

        QLineEdit.focusInEvent(line_edit, event)

    def _should_open_list(self, text: str) -> bool:
        if not text:
            return False
        if text[0] in ("ض", "ط"):
            return len(text) >= 2
        return len(text) >= 1

    def _on_symbol_text_edited_dynamic(self, line_edit: QLineEdit, text: str):
        line_edit.setProperty("ins_code", "")
        line_edit.setProperty("contract_size", 0)
        line_edit.setProperty("underlying_ticker", "")

        self._active_line_edit = line_edit

        if not self._should_open_list(text):
            self._hide_completer()
            return

        self._show_completer_for(line_edit, text)

    def _show_completer_for(self, line_edit: QLineEdit, prefix: str):
        if self.snapshot is None or not self.symbol_items:
            return

        global_pos = line_edit.mapToGlobal(QPoint(0, line_edit.height()))
        width = line_edit.width()
        self._completer.filter_and_show(prefix, global_pos, width)

    def _on_symbol_selected(self, item: Dict[str, Any]):
        line_edit = self._active_line_edit
        if line_edit is None:
            return

        row = self._get_row_of_widget(line_edit)
        if row < 0:
            self._hide_completer()
            return

        data = item.get("data", {})
        symbol = item.get("symbol", "")

        line_edit.blockSignals(True)
        line_edit.setText(symbol)
        line_edit.blockSignals(False)

        cmb_kind: QComboBox = self.table_legs.cellWidget(row, COL_KIND)
        option_kind = data.get("option_kind", OptionType.STOCK)
        idx = cmb_kind.findData(option_kind)
        if idx >= 0:
            cmb_kind.setCurrentIndex(idx)

        spin_strike: QSpinBox = self.table_legs.cellWidget(row, COL_STRIKE)
        spin_strike.setValue(int(data.get("strike_price", 0)))

        spin_entry: QSpinBox = self.table_legs.cellWidget(row, COL_ENTRY)
        cur_price = int(data.get("current_price", 0))
        if cur_price > 0:
            spin_entry.setValue(cur_price)

        line_expiry: QLineEdit = self.table_legs.cellWidget(row, COL_EXPIRY)
        line_expiry.setText(data.get("expiry_date", ""))

        self._apply_leg_row_state(row)

        line_edit.setProperty("ins_code", data.get("ins_code", ""))
        line_edit.setProperty("underlying_ticker",
                              data.get("underlying_ticker", ""))
        line_edit.setProperty("contract_size",
                              data.get("contract_size", 1000))

        self._update_live_price_for_row(row)

        self._hide_completer()
        self._update_detected_strategy_label()
        self._update_live_summary()

    # =====================================================
    # Event Filter
    # =====================================================

    def eventFilter(self, obj, event):
        if obj is not self._active_line_edit:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.KeyPress:
            key = event.key()

            if self._completer.is_open():
                if key == Qt.Key_Down:
                    self._completer.move_selection(+1)
                    return True
                if key == Qt.Key_Up:
                    self._completer.move_selection(-1)
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    self._completer.select_current()
                    return True
                if key == Qt.Key_Escape:
                    self._hide_completer()
                    return True

            if key in (Qt.Key_Return, Qt.Key_Enter):
                text = obj.text().strip()
                if text:
                    self._add_new_row_and_focus()
                    return True
                else:
                    if self._should_open_list(text):
                        self._show_completer_for(obj, text)
                        return True

        return super().eventFilter(obj, event)

    # =====================================================
    # بارگذاری داده
    # =====================================================

    def load_position_data(self):
        today_shamsi = jdatetime.date.today().strftime("%Y/%m/%d")
        exec_date = self.position.execution_date or today_shamsi

        self.txt_strategy.setText(self.position.strategy_name)

        broker = self.position.broker_name or DEFAULT_BROKER
        idx = self.cmb_broker.findText(broker)
        if idx >= 0:
            self.cmb_broker.setCurrentIndex(idx)
        else:
            self.cmb_broker.setCurrentText(broker)

        self.txt_exec_date.setText(exec_date)
        self.spin_alert_roi.setValue(
            10.0 if self.is_new else self.position.alert_target_roi)

        self.table_legs.setRowCount(0)
        for leg in self.position.legs:
            self.add_leg_row(leg)

        self._update_detected_strategy_label()
        self._update_live_summary()

    # =====================================================
    # ذخیره
    # =====================================================

    def save_and_close(self):
        strategy_name = self.txt_strategy.text().strip()
        exec_date = self.txt_exec_date.text().strip()
        broker_name = self.cmb_broker.currentText().strip() or DEFAULT_BROKER

        if not strategy_name:
            QMessageBox.warning(
                self, "خطا",
                "نام استراتژی نمی‌تواند خالی باشد.\n\n"
                "لطفاً یک نام وارد کنید یا از دکمه «← استفاده» استفاده کنید.")
            self.txt_strategy.setFocus()
            return

        if not exec_date:
            QMessageBox.warning(self, "خطا", "تاریخ اجرا را وارد کنید.")
            return

        if not re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', exec_date):
            QMessageBox.warning(
                self, "خطا",
                "تاریخ اجرا نامعتبر است.\n"
                "فرمت صحیح: YYYY/MM/DD (مثلاً 1403/01/15)")
            return

        # ─── استخراج لگ‌ها ───
        legs: List[OptionLeg] = []

        for r in range(self.table_legs.rowCount()):
            line_symbol: QLineEdit = self.table_legs.cellWidget(r, COL_SYMBOL)
            cmb_kind: QComboBox = self.table_legs.cellWidget(r, COL_KIND)
            cmb_side: QComboBox = self.table_legs.cellWidget(r, COL_SIDE)
            spin_strike: QSpinBox = self.table_legs.cellWidget(r, COL_STRIKE)
            spin_qty: QSpinBox = self.table_legs.cellWidget(r, COL_QTY)
            spin_entry: QSpinBox = self.table_legs.cellWidget(r, COL_ENTRY)
            spin_current: QSpinBox = self.table_legs.cellWidget(
                r, COL_CURRENT)
            line_expiry: QLineEdit = self.table_legs.cellWidget(r, COL_EXPIRY)

            if line_symbol is None or not line_symbol.text().strip():
                continue

            raw_symbol = line_symbol.text()
            symbol = normalize_symbol(sanitize_symbol_input(raw_symbol))

            option_kind = cmb_kind.currentData() or OptionType.STOCK
            leg_type = cmb_side.currentData() or LegType.BUY
            strike = spin_strike.value()
            qty = spin_qty.value()
            entry_price = spin_entry.value()
            current_price = spin_current.value() if spin_current else 0
            expiry = line_expiry.text().strip()

            is_option = (option_kind != OptionType.STOCK)

            ins_code = line_symbol.property("ins_code") or ""

            cs_prop = line_symbol.property("contract_size")
            try:
                cs_value = int(cs_prop) if cs_prop is not None else 0
            except (TypeError, ValueError):
                cs_value = 0

            contract_size = cs_value if cs_value > 0 else (
                1000 if is_option else 1)

            # حفظ فیلدهای قبلی اگر همان لگه بود
            original = None
            for orig in self.position.legs:
                if orig.leg_id and getattr(orig, 'leg_id', '') == \
                        line_symbol.property("leg_id"):
                    original = orig
                    break
                if orig.symbol == symbol and \
                   orig.leg_type == leg_type and \
                   abs(orig.strike_price - strike) < 1:
                    original = orig
                    break

            leg = OptionLeg(
                symbol=symbol,
                is_option=is_option,
                option_kind=option_kind,
                leg_type=leg_type,
                strike_price=strike if is_option else 0.0,
                contract_size=int(contract_size),
                quantity=qty,
                entry_price=entry_price,
                current_price=current_price,
                expiry_date=expiry,
                ins_code=ins_code,
            )

            if original is not None:
                leg.leg_id = original.leg_id
                leg.close_price = original.close_price
                leg.close_fee = original.close_fee
                leg.entry_fee = original.entry_fee
                leg.is_defaulted = original.is_defaulted
                leg.default_penalty = original.default_penalty
                leg.default_payment = original.default_payment
                leg.settlement_price = original.settlement_price
                # ✅ فیلدهای جدید
                leg.source = original.source
                leg.trade_ref = original.trade_ref
                leg.close_trade_ref = original.close_trade_ref
                leg.realized_pnl = original.realized_pnl
                leg.open_date = original.open_date
                leg.open_time = original.open_time
                leg.close_date = original.close_date
                leg.close_time = original.close_time
                leg.trade_time = original.trade_time

            legs.append(leg)

        if not legs:
            QMessageBox.warning(
                self, "خطا", "حداقل یک لگ معتبر وارد کنید.")
            return

        underlying_symbol = self._extract_underlying_symbol(legs)

        position_expiry = ""
        for leg in legs:
            if leg.is_option and leg.expiry_date:
                position_expiry = leg.expiry_date
                break

        if self.is_new or not self.position.position_id:
            self.position.position_id = f"POS-{int(time.time())}"

        self.position.strategy_name = strategy_name
        self.position.broker_name = broker_name
        self.position.underlying_symbol = underlying_symbol
        self.position.execution_date = exec_date
        self.position.expiry_date = position_expiry
        self.position.alert_target_roi = self.spin_alert_roi.value()
        self.position.legs = legs

        self.accept()

    # =====================================================
    # استخراج نماد پایه
    # =====================================================

    def _extract_underlying_symbol(self, legs: List[OptionLeg]) -> str:
        for leg in legs:
            if leg.is_stock and leg.symbol:
                return leg.symbol

        if self.snapshot is not None:
            for leg in legs:
                if leg.is_option and leg.symbol:
                    contract = self.snapshot.get_options_by_symbol(leg.symbol)
                    if contract and contract.underlying_ticker:
                        return normalize_symbol(contract.underlying_ticker)

        for leg in legs:
            if leg.is_option and leg.symbol:
                s = leg.symbol
                if s.startswith(("ض", "ط")):
                    s = s[1:]
                m = re.match(r'([^\d]+)', s)
                if m:
                    return m.group(1)
                return s[:4]

        return ""


# =====================================================
# دیالوگ تسویه نقدی / نکول
# =====================================================

class CashSettlementDialog(QDialog):
    """دیالوگ ثبت تسویه نقدی یا نکول"""

    def __init__(self, parent=None, position: StrategyPosition = None,
                 default_mode: str = "cash"):
        super().__init__(parent)
        self.setWindowTitle("ثبت تسویه نقدی / نکول")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(620)

        self.position = position
        self._default_mode = default_mode
        self._result = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── اطلاعات موقعیت ───
        info_group = QGroupBox("اطلاعات موقعیت")
        info_layout = QFormLayout(info_group)

        info_layout.addRow("شناسه:", QLabel(self.position.position_id))
        info_layout.addRow(
            "استراتژی:", QLabel(self.position.strategy_name))
        info_layout.addRow(
            "کارگزاری:", QLabel(self.position.broker_name or "—"))
        info_layout.addRow(
            "نماد پایه:", QLabel(self.position.underlying_symbol))
        info_layout.addRow(
            "تاریخ سررسید:", QLabel(self.position.expiry_date))

        layout.addWidget(info_group)

        # ─── نوع انجام ───
        type_group = QGroupBox("نوع انجام")
        type_layout = QVBoxLayout(type_group)

        self.radio_cash = QRadioButton("📌 تسویه نقدی معمولی")
        self.radio_default = QRadioButton(
            "⚖️ تسویه نقدی با نکول طرف مقابل")
        self.radio_you_default = QRadioButton(
            "❌ تسویه نقدی با نکول خودم")

        has_call = any(l.is_call for l in self.position.legs)

        if not has_call:
            self.radio_default.setEnabled(False)
            self.radio_you_default.setEnabled(False)
            self.radio_default.setToolTip("نکول فقط برای CALL معنا دارد")
            self.radio_you_default.setToolTip(
                "نکول فقط برای CALL معنا دارد")

        if self._default_mode == "default" and has_call:
            self.radio_default.setChecked(True)
        elif self._default_mode == "you_default" and has_call:
            self.radio_you_default.setChecked(True)
        else:
            self.radio_cash.setChecked(True)

        type_layout.addWidget(self.radio_cash)
        type_layout.addWidget(self.radio_default)
        type_layout.addWidget(self.radio_you_default)

        self.radio_cash.toggled.connect(self._on_type_changed)
        self.radio_default.toggled.connect(self._on_type_changed)
        self.radio_you_default.toggled.connect(self._on_type_changed)

        layout.addWidget(type_group)

        # ─── تسویه نقدی معمولی ───
        self.cash_group = QGroupBox("تسویه نقدی معمولی")
        cash_layout = QFormLayout(self.cash_group)

        self.spin_amount = QDoubleSpinBox()
        self.spin_amount.setRange(-1e12, 1e12)
        self.spin_amount.setDecimals(0)
        self.spin_amount.setGroupSeparatorShown(True)
        self.spin_amount.setSuffix(f" {CURRENCY}")
        self.spin_amount.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_amount.setValue(0.0)

        cash_layout.addRow(
            "مبلغ خالص دریافتی/پرداختی:", self.spin_amount)

        hint = QLabel(
            "💡 مثبت = دریافت، منفی = پرداخت\n"
            "   (بدون کارمزد اعمال یا جریمه)")
        set_tone(hint, "muted")
        cash_layout.addRow("", hint)

        layout.addWidget(self.cash_group)

        # ─── نکول ───
        self.default_group = QGroupBox(
            "تسویه نقدی با نکول (فقط برای CALL)")
        default_layout = QFormLayout(self.default_group)

        self.spin_st = QDoubleSpinBox()
        self.spin_st.setRange(0, 1e12)
        self.spin_st.setDecimals(0)
        self.spin_st.setGroupSeparatorShown(True)
        self.spin_st.setSuffix(" ریال")
        self.spin_st.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_st.valueChanged.connect(self._update_default_calc)

        # ✅ استفاده از get_market_snapshot از main
        default_st = 0.0
        try:
            snap = get_market_snapshot(
                use_cache=True, force_refresh=False)
            default_st = _get_underlying_closing_price(
                snap, self.position.underlying_symbol)
        except Exception as e:
            logger.warning(f"S_T load failed: {e}")

        if default_st <= 0:
            default_st = self.position.underlying_price
        self.spin_st.setValue(default_st)

        default_layout.addRow(
            "قیمت پایانی سهم پایه (S_T):", self.spin_st)

        st_hint = QLabel(
            "💡 این مقدار از «قیمت پایانی» سهم پایه گرفته شده است.")
        set_tone(st_hint, "muted")
        default_layout.addRow("", st_hint)

        self.lbl_payment = QLabel("—")
        self.lbl_penalty = QLabel("—")
        self.lbl_exercise_fee = QLabel("—")
        self.lbl_net = QLabel("—")

        default_layout.addRow("💰 وجه تسویه:", self.lbl_payment)
        default_layout.addRow("💸 جریمه ۱٪:", self.lbl_penalty)
        default_layout.addRow("📋 کارمزد اعمال:", self.lbl_exercise_fee)
        default_layout.addRow("━━━━━━━━━━━", QLabel(""))
        default_layout.addRow("📈 خالص نهایی:", self.lbl_net)

        layout.addWidget(self.default_group)

        # ─── دکمه‌ها ───
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("✅ تأیید و ثبت")
        buttons.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        set_kind(buttons.button(QDialogButtonBox.Ok), "primary")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self._on_type_changed()

    def _on_type_changed(self):
        is_cash = self.radio_cash.isChecked()
        self.cash_group.setVisible(is_cash)
        self.default_group.setVisible(not is_cash)

        if not is_cash:
            self._update_default_calc()

        self.adjustSize()

    def _get_exercise_rate(self) -> float:
        """نرخ کارمزد اعمال — از main.get_setting"""
        try:
            rate = get_setting(
                "exercise_fee_rate",
                self.position.underlying_symbol,
            )
            if rate is not None:
                return float(rate)
        except Exception as e:
            logger.debug(f"exercise_fee_rate load failed: {e}")
        return 0.0005  # پیش‌فرض

    def _update_default_calc(self):
        S_T = self.spin_st.value()
        exercise_rate = self._get_exercise_rate()

        # ✅ تعیین is_self_default بر اساس radio انتخاب‌شده
        is_self_default = self.radio_you_default.isChecked()

        total_payment = 0.0
        total_penalty = 0.0
        total_exercise_fee = 0.0
        net_total = 0.0

        for leg in self.position.legs:
            if not leg.is_call:
                continue
            r = PositionPnLCalculator.calculate_call_default(
                leg, S_T,
                exercise_rate=exercise_rate,
                is_self_default=is_self_default,
            )
            if r["valid"]:
                total_payment += r["payment"]
                total_penalty += r["penalty"]
                total_exercise_fee += r["exercise_fee"]
                net_total += r["net"]

        self.lbl_payment.setText(f"{fmt_money(total_payment)} ریال")
        self.lbl_penalty.setText(f"{fmt_money(total_penalty)} ریال")

        if total_exercise_fee > 0:
            self.lbl_exercise_fee.setText(
                f"{fmt_money(total_exercise_fee)} ریال")
            set_tone(self.lbl_exercise_fee, "loss")
        else:
            self.lbl_exercise_fee.setText("—")
            set_tone(self.lbl_exercise_fee, "muted")

        tone = pnl_tone(net_total)
        self.lbl_net.setText(f"{fmt_money(net_total)} ریال")
        set_tone(self.lbl_net, tone, big=True)

    def _on_accept(self):
        if self.radio_cash.isChecked():
            amount = self.spin_amount.value()
            self._result = {
                "mode": "cash",
                "amount": amount,
            }
        else:
            mode = "default" if self.radio_default.isChecked() \
                else "you_default"
            self._result = {
                "mode": mode,
                "S_T": self.spin_st.value(),
                "exercise_rate": self._get_exercise_rate(),
            }
        self.accept()

    def get_result(self) -> dict:
        return self._result


# =====================================================
# دیالوگ آفست
# =====================================================

class OffsetDialog(QDialog):
    """دیالوگ آفست — بستن موقعیت باز با معامله معکوس"""

    def __init__(self, parent=None, position: StrategyPosition = None):
        super().__init__(parent)
        self.setWindowTitle("آفست (بستن موقعیت باز)")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(720)

        self.position = position
        self._result = None
        self._spin_outputs: List[QSpinBox] = []

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── اطلاعات موقعیت ───
        info_group = QGroupBox("اطلاعات موقعیت")
        info_layout = QFormLayout(info_group)

        info_layout.addRow("شناسه:", QLabel(self.position.position_id))
        info_layout.addRow("استراتژی:", QLabel(self.position.strategy_name))
        info_layout.addRow(
            "کارگزاری:", QLabel(self.position.broker_name or "—"))
        info_layout.addRow(
            "نماد پایه:", QLabel(self.position.underlying_symbol))
        info_layout.addRow(
            "تاریخ اجرا:", QLabel(self.position.execution_date))

        layout.addWidget(info_group)

        # ─── جدول لگ‌ها ───
        legs_group = QGroupBox("قیمت خروج هر لگ (معامله معکوس)")
        legs_layout = QVBoxLayout(legs_group)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "#", "نماد", "نوع", "قیمت ورود", "قیمت خروج",
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 170)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setAlternatingRowColors(True)

        for idx, leg in enumerate(self.position.legs, 1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            item_num = QTableWidgetItem(str(idx))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_num)

            item_sym = QTableWidgetItem(leg.symbol)
            item_sym.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, item_sym)

            direction = "خرید" if leg.leg_type == LegType.BUY else "فروش"
            if leg.is_call:
                direction += " (کال)"
            elif leg.is_put:
                direction += " (پوت)"
            elif leg.is_stock:
                direction += " (سهام)"

            item_kind = QTableWidgetItem(direction)
            item_kind.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, item_kind)

            item_entry = QTableWidgetItem(fmt_int(leg.entry_price))
            item_entry.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, item_entry)

            spin_out = QSpinBox()
            spin_out.setRange(0, 1_000_000_000)
            spin_out.setSingleStep(10)
            spin_out.setGroupSeparatorShown(True)
            spin_out.setButtonSymbols(QAbstractSpinBox.NoButtons)

            default_price = leg.current_price or leg.entry_price
            spin_out.setValue(int(default_price))
            spin_out.valueChanged.connect(self._update_calculation)

            self.table.setCellWidget(row, 4, spin_out)
            self._spin_outputs.append(spin_out)

        legs_layout.addWidget(self.table)
        layout.addWidget(legs_group)

        # ─── محاسبه خودکار ───
        result_group = QGroupBox("محاسبه خودکار")
        result_layout = QFormLayout(result_group)

        self.lbl_net_entry = QLabel("—")
        self.lbl_net_exit = QLabel("—")
        self.lbl_close_fee = QLabel("—")
        self.lbl_realized_pnl = QLabel("—")
        self.lbl_realized_roi = QLabel("—")

        result_layout.addRow("💰 هزینه ورود خالص:", self.lbl_net_entry)
        result_layout.addRow("💵 ارزش خروج خالص:", self.lbl_net_exit)
        result_layout.addRow("📋 کارمزد خروج:", self.lbl_close_fee)
        result_layout.addRow("━━━━━━━━━", QLabel(""))
        result_layout.addRow(
            "📈 سود/زیان محقق‌شده:", self.lbl_realized_pnl)
        result_layout.addRow("📊 بازدهی (ROI):", self.lbl_realized_roi)

        layout.addWidget(result_group)

        # ─── دکمه‌ها ───
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("✅ تأیید و بستن")
        buttons.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        set_kind(buttons.button(QDialogButtonBox.Ok), "primary")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self._update_calculation()

    def _update_calculation(self):
        temp_legs: List[OptionLeg] = []

        for i, leg in enumerate(self.position.legs):
            close_price = self._spin_outputs[i].value()

            temp_leg = OptionLeg(
                leg_id=leg.leg_id,
                symbol=leg.symbol,
                is_option=leg.is_option,
                option_kind=leg.option_kind,
                leg_type=leg.leg_type,
                strike_price=leg.strike_price,
                contract_size=leg.contract_size,
                quantity=leg.quantity,
                entry_price=leg.entry_price,
                entry_fee=leg.entry_fee,
                current_price=leg.current_price,
                close_price=float(close_price),
                close_fee=0.0,
                expiry_date=leg.expiry_date,
                ins_code=leg.ins_code,
            )
            temp_leg.close_fee = \
                PositionPnLCalculator.calculate_leg_close_fee(
                    temp_leg, float(close_price))
            temp_legs.append(temp_leg)

        temp_pos = StrategyPosition(
            position_id=self.position.position_id,
            strategy_name=self.position.strategy_name,
            broker_name=self.position.broker_name,
            underlying_symbol=self.position.underlying_symbol,
            underlying_price=self.position.underlying_price,
            execution_date=self.position.execution_date,
            expiry_date=self.position.expiry_date,
            status=PositionStatus.CLOSED,
            legs=temp_legs,
        )

        net_entry = PositionPnLCalculator.calculate_net_entry_cost(temp_pos)
        realized_pnl, realized_roi = \
            PositionPnLCalculator.calculate_realized_pnl(temp_pos)
        net_exit = net_entry + realized_pnl
        total_close_fee = sum(l.close_fee for l in temp_legs)

        self.lbl_net_entry.setText(fmt_money(net_entry))
        self.lbl_net_exit.setText(fmt_money(net_exit))
        self.lbl_close_fee.setText(fmt_money(total_close_fee))

        tone = pnl_tone(realized_pnl)
        self.lbl_realized_pnl.setText(fmt_money(realized_pnl))
        set_tone(self.lbl_realized_pnl, tone, big=True)

        self.lbl_realized_roi.setText(fmt_pct(realized_roi, digits=2))
        set_tone(self.lbl_realized_roi, tone)

        self._result = {
            "net_entry": net_entry,
            "net_exit": net_exit,
            "realized_pnl": realized_pnl,
            "realized_roi": realized_roi,
            "total_close_fee": total_close_fee,
            "close_prices": [s.value() for s in self._spin_outputs],
        }

    def _on_accept(self):
        if not self._result:
            QMessageBox.warning(self, "خطا", "محاسبه معتبر نیست.")
            return
        self.accept()

    def get_result(self) -> dict:
        return self._result


# =====================================================
# ✅ دیالوگ تاریخچه‌ی ایمپورت‌ها (جدید)
# =====================================================

class ImportHistoryDialog(QDialog):
    """دیالوگ تاریخچه‌ی ایمپورت‌ها + بازگردانی batch"""

    def __init__(self, parent=None, storage=None):
        super().__init__(parent)
        self.setWindowTitle("تاریخچه‌ی ایمپورت‌ها")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(800, 500)

        self.storage = storage
        self._batches: List[dict] = []

        self.init_ui()
        self._load_batches()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── هدر ───
        header = QLabel(
            "📋 فهرست ایمپورت‌های انجام‌شده از اکسل کارگزاری"
        )
        set_tone(header, "primary", big=True)
        layout.addWidget(header)

        hint = QLabel(
            "💡 با کلیک روی «بازگردانی»، همه‌ی موقعیت‌های آن batch حذف می‌شوند."
        )
        set_tone(hint, "muted")
        layout.addWidget(hint)

        # ─── جدول ───
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "شناسه batch", "کارگزاری", "تاریخ ایجاد",
            "معاملات", "باز", "بسته", "اقدام",
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 70)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table, 1)

        # ─── دکمه‌ها ───
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("بستن")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_batches(self):
        if self.storage is None:
            return

        self._batches = self.storage.load_import_batches()
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)

        if not self._batches:
            self.table.insertRow(0)
            item = QTableWidgetItem("هیچ ایمپورتی ثبت نشده است")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 7)
            return

        for batch in self._batches:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(
                batch.get("batch_id", "—")))
            self.table.setItem(row, 1, QTableWidgetItem(
                batch.get("broker", "—")))
            self.table.setItem(row, 2, QTableWidgetItem(
                batch.get("created_at", "—")))
            self.table.setItem(row, 3, QTableWidgetItem(
                str(batch.get("n_trades", 0))))
            self.table.setItem(row, 4, QTableWidgetItem(
                str(batch.get("n_positions_open", 0))))
            self.table.setItem(row, 5, QTableWidgetItem(
                str(batch.get("n_positions_closed", 0))))

            btn = QPushButton("↩️ بازگردانی")
            btn.clicked.connect(
                lambda _, b=batch: self._rollback_batch(b))
            self.table.setCellWidget(row, 6, btn)

    def _rollback_batch(self, batch: dict):
        batch_id = batch.get("batch_id", "")
        if not batch_id:
            return

        n_open = batch.get("n_positions_open", 0)
        n_closed = batch.get("n_positions_closed", 0)

        reply = QMessageBox.question(
            self, "تأیید بازگردانی",
            f"آیا از بازگردانی ایمپورت زیر مطمئن هستید؟\n\n"
            f"شناسه: {batch_id}\n"
            f"کارگزاری: {batch.get('broker', '—')}\n"
            f"موقعیت‌های باز: {n_open}\n"
            f"موقعیت‌های بسته: {n_closed}\n\n"
            f"⚠️ این عمل قابل بازگشت نیست!",
            QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # حذف موقعیت‌ها
        positions = self.storage.load_positions()
        new_positions = [
            p for p in positions
            if p.import_batch_id != batch_id
        ]

        removed_count = len(positions) - len(new_positions)

        if removed_count == 0:
            QMessageBox.information(
                self, "اطلاع",
                "هیچ موقعیتی برای این batch یافت نشد.")
            return

        if not self.storage.save_positions(new_positions):
            QMessageBox.critical(
                self, "خطا",
                "ذخیره‌سازی موقعیت‌ها ناموفق بود.")
            return

        # حذف batch از فایل batch ها
        self.storage.delete_import_batch(batch_id)

        QMessageBox.information(
            self, "موفق",
            f"✅ {removed_count} موقعیت حذف شد.")

        self._load_batches()