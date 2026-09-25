# position_saver/ui/dialogs.py
# -*- coding: utf-8 -*-

import re
import sys
import time
import jdatetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QMessageBox, QHeaderView,
    QGroupBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtGui import QColor, QFont

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,
)
from position_saver.pnl_calculator import PositionPnLCalculator
from core.enums import OptionType


# =====================================================
# کارگزاری‌های پیش‌فرض
# =====================================================

BROKER_NAMES = ["مفید", "خبرگان سهام", "پیشرو", "سایر"]
DEFAULT_BROKER = "مفید"


# =====================================================
# تغییر زبان کیبورد (ویندوز)
# =====================================================

def switch_to_persian_keyboard():
    if sys.platform == "win32":
        try:
            import win32api
            import win32con
            PERSIAN_LAYOUT_ID = 0x0429
            win32api.LoadKeyboardLayout(
                f"{PERSIAN_LAYOUT_ID:08x}", win32con.KLF_ACTIVATE)
        except Exception as e:
            print(f"[Keyboard] Failed to switch: {e}")


# =====================================================
# نرمال‌سازی نام نماد
# =====================================================

def normalize_symbol(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    s = s.replace('ي', 'ی').replace('ك', 'ک')
    s = s.replace("\u200c", " ")
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# =====================================================
# پاکسازی ورودی نماد
# =====================================================

_SYMBOL_INVALID_CHARS = re.compile(r'[^\u0600-\u06FF\u200cA-Za-z0-9 ]')


def sanitize_symbol_input(text: str) -> str:
    if not text:
        return text
    return _SYMBOL_INVALID_CHARS.sub('', text)


# =====================================================
# تابع کمکی: قیمت پایانی سهم پایه از snapshot
# =====================================================

def _get_underlying_closing_price(snapshot, underlying_ticker: str) -> float:
    """
    گرفتن قیمت پایانی سهم پایه از snapshot.
    اول close_price (پایانی)، بعد last_price.
    """
    if snapshot is None or not underlying_ticker:
        return 0.0
    try:
        ua = snapshot.get_underlying_assets(underlying_ticker)
        if ua is not None:
            # ✅ اول close_price (پایانی)
            if hasattr(ua, 'close_price') and ua.close_price > 0:
                return float(ua.close_price)
            # فال‌بک: last_price
            if hasattr(ua, 'last_price') and ua.last_price > 0:
                return float(ua.last_price)
    except Exception as e:
        print(f"[DefaultDialog] Failed to get closing price: {e}")
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
COL_EXPIRY = 6
N_LEG_COLS = 7


# =====================================================
# تشخیص خودکار نام استراتژی
# =====================================================

def detect_strategy_name(legs: List[OptionLeg]) -> str:
    """تشخیص خودکار نام استراتژی از ترکیب لگ‌ها (مستقل از ترتیب)"""
    if not legs:
        return ""

    stock_buys = [l for l in legs if l.is_stock and l.leg_type == LegType.BUY]
    stock_sells = [
        l for l in legs if l.is_stock and l.leg_type == LegType.SELL]
    call_buys = [l for l in legs if l.is_call and l.leg_type == LegType.BUY]
    call_sells = [l for l in legs if l.is_call and l.leg_type == LegType.SELL]
    put_buys = [l for l in legs if l.is_put and l.leg_type == LegType.BUY]
    put_sells = [l for l in legs if l.is_put and l.leg_type == LegType.SELL]

    n_total = len(legs)
    n_stock = len(stock_buys) + len(stock_sells)
    n_call = len(call_buys) + len(call_sells)
    n_put = len(put_buys) + len(put_sells)

    # ═══════ تک‌لگ ═══════
    if n_total == 1:
        leg = legs[0]
        if leg.is_stock:
            return "Long Stock" if leg.leg_type == LegType.BUY else "Short Stock"
        if leg.is_call:
            return "Long Call" if leg.leg_type == LegType.BUY else "Short Call"
        if leg.is_put:
            return "Long Put" if leg.leg_type == LegType.BUY else "Short Put"

    # ═══════ دولگ ═══════
    if n_total == 2:
        if n_stock == 1 and n_call == 1:
            if stock_buys and call_sells:
                return "Covered Call"
            if stock_sells and call_buys:
                return "Covered Call"
            if stock_buys and call_buys:
                return "Long Stock + Long Call"
            if stock_sells and call_sells:
                return "Short Stock + Short Call"

        if n_stock == 1 and n_put == 1:
            if stock_buys and put_buys:
                return "Married Put"
            if stock_buys and put_sells:
                return "Covered Put"
            if stock_sells and put_buys:
                return "Protective Put (Short)"
            if stock_sells and put_sells:
                return "Covered Put (Short)"

        if n_call == 2 and len(call_buys) == 1 and len(call_sells) == 1:
            if call_buys[0].strike_price < call_sells[0].strike_price:
                return "Bull Call Spread"
            elif call_buys[0].strike_price > call_sells[0].strike_price:
                return "Bear Call Spread"
            else:
                return "Call Spread"

        if n_put == 2 and len(put_buys) == 1 and len(put_sells) == 1:
            if put_buys[0].strike_price > put_sells[0].strike_price:
                return "Bear Put Spread"
            elif put_buys[0].strike_price < put_sells[0].strike_price:
                return "Bull Put Spread"
            else:
                return "Put Spread"

        if n_call == 1 and n_put == 1:
            if call_buys and put_buys:
                if call_buys[0].strike_price == put_buys[0].strike_price:
                    return "Long Straddle"
                elif call_buys[0].strike_price > put_buys[0].strike_price:
                    return "Long Strangle"
                else:
                    return "Long Guts"
            if call_sells and put_sells:
                if call_sells[0].strike_price == put_sells[0].strike_price:
                    return "Short Straddle"
                elif call_sells[0].strike_price < put_sells[0].strike_price:
                    return "Short Strangle"
                else:
                    return "Short Guts"
            if call_buys and put_sells:
                return "Synthetic Long Stock"
            if call_sells and put_buys:
                return "Synthetic Short Stock"

    # ═══════ سه‌لگ ═══════
    if n_total == 3:
        if n_stock == 1 and n_call == 1 and n_put == 1:
            if stock_buys and call_sells and put_buys:
                return "Collar"
            if stock_buys and call_sells and put_sells:
                return "Covered Call + Covered Put"
            if stock_sells and call_buys and put_buys:
                return "Reverse Collar"

        if n_call == 3:
            if len(call_buys) == 2 and len(call_sells) == 1:
                buys_sorted = sorted([l.strike_price for l in call_buys])
                sell_strike = call_sells[0].strike_price
                if buys_sorted[0] < sell_strike < buys_sorted[1]:
                    return "Long Call Butterfly"
            if len(call_buys) == 1 and len(call_sells) == 2:
                sells_sorted = sorted([l.strike_price for l in call_sells])
                buy_strike = call_buys[0].strike_price
                if sells_sorted[0] < buy_strike < sells_sorted[1]:
                    return "Short Call Butterfly"

        if n_put == 3:
            if len(put_buys) == 2 and len(put_sells) == 1:
                buys_sorted = sorted([l.strike_price for l in put_buys])
                sell_strike = put_sells[0].strike_price
                if buys_sorted[0] < sell_strike < buys_sorted[1]:
                    return "Long Put Butterfly"
            if len(put_buys) == 1 and len(put_sells) == 2:
                sells_sorted = sorted([l.strike_price for l in put_sells])
                buy_strike = put_buys[0].strike_price
                if sells_sorted[0] < buy_strike < sells_sorted[1]:
                    return "Short Put Butterfly"

        if n_call == 2 and n_put == 1:
            return "Call Ratio + Put"
        if n_call == 1 and n_put == 2:
            return "Put Ratio + Call"

    # ═══════ چهارلگ ═══════
    if n_total == 4:
        if n_call == 2 and n_put == 2:
            return "Iron Condor"
        if n_call == 4 and len(call_buys) == 2 and len(call_sells) == 2:
            return "Condor (Call)"
        if n_put == 4 and len(put_buys) == 2 and len(put_sells) == 2:
            return "Condor (Put)"

    return "Strategy"


# =====================================================
# لیست Autocomplete
# =====================================================

class SymbolCompleter(QListWidget):
    """
    لیست شناور برای autocomplete نمادها.
    - هرگز فوکوس کیبورد را از line_edit نمی‌گیرد.
    - فقط نام نماد نمایش داده می‌شود.
    - فیلتر با startswith.
    - هنگام بسته شدن دیالوگ، به‌صورت کامل پنهان می‌شود.
    """

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
        self.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF;
                border: 1px solid #BDBDBD;
                border-radius: 4px;
                padding: 2px;
                font-family: Tahoma, Arial;
                font-size: 11px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                color: #212121;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #E3F2FD;
            }
        """)

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
        self.resize(1100, 680)
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
                    "ins_code": "",
                    "underlying_ticker": underlying,
                },
            })

        return items

    def _lookup_underlying_price(self, normalized_ticker: str) -> float:
        """جستجوی قیمت سهم پایه (قیمت پایانی، فال‌بک به last_price)"""
        if self.snapshot is None:
            return 0.0
        for ua_key, ua in self.snapshot.underlying_assets.items():
            if normalize_symbol(ua_key) == normalized_ticker:
                # ✅ اول close_price
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

        # ─── اطلاعات کلی ───
        info_group = QGroupBox("اطلاعات کلی")
        form_layout = QFormLayout(info_group)

        self.txt_strategy = QLineEdit()
        self.txt_strategy.setPlaceholderText(
            "مثلاً: Covered Call / Bull Call Spread / Long Call")

        # ✅ ردیف تشخیص خودکار
        detected_row = QHBoxLayout()

        self.lbl_detected_strategy = QLabel("(تشخیص خودکار: —)")
        self.lbl_detected_strategy.setStyleSheet(
            "color: #9E9E9E; font-size: 10px; "
            "font-weight: bold; padding-right: 4px;")

        self.btn_use_suggestion = QPushButton("← استفاده")
        self.btn_use_suggestion.setFixedWidth(90)
        self.btn_use_suggestion.setStyleSheet(
            "background-color: #E3F2FD; color: #1976D2; "
            "font-size: 10px; padding: 3px 6px; border-radius: 3px;")
        self.btn_use_suggestion.setToolTip(
            "کپی کردن پیشنهاد تشخیص خودکار در فیلد نام استراتژی")
        self.btn_use_suggestion.setEnabled(False)
        self.btn_use_suggestion.clicked.connect(self._apply_suggested_strategy)

        detected_row.addWidget(self.lbl_detected_strategy)
        detected_row.addWidget(self.btn_use_suggestion)
        detected_row.addStretch()

        # ✅ کارگزاری
        self.cmb_broker = QComboBox()
        self.cmb_broker.setEditable(True)
        self.cmb_broker.addItems(BROKER_NAMES)
        self.cmb_broker.setCurrentText(DEFAULT_BROKER)
        self.cmb_broker.setMinimumWidth(180)
        self.cmb_broker.setInsertPolicy(QComboBox.NoInsert)

        self.txt_exec_date = QLineEdit()
        self.txt_exec_date.setPlaceholderText("1403/01/15")

        self.spin_alert_roi = QDoubleSpinBox()
        self.spin_alert_roi.setRange(0.0, 1000.0)
        self.spin_alert_roi.setSuffix(" ٪")
        self.spin_alert_roi.setValue(10.0)

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
            "تعداد", "قیمت ورود", "تاریخ سررسید",
        ])
        self.table_legs.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_legs.horizontalHeader().setStretchLastSection(True)
        self.table_legs.setColumnWidth(COL_SYMBOL, 280)
        self.table_legs.setColumnWidth(COL_KIND, 90)
        self.table_legs.setColumnWidth(COL_SIDE, 90)
        self.table_legs.setColumnWidth(COL_STRIKE, 120)
        self.table_legs.setColumnWidth(COL_QTY, 90)
        self.table_legs.setColumnWidth(COL_ENTRY, 120)
        self.table_legs.setSelectionBehavior(QTableWidget.SelectRows)
        legs_layout.addWidget(self.table_legs)

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

        # ─── دکمه‌های پایین ───
        bottom_layout = QHBoxLayout()
        btn_save = QPushButton("💾 ذخیره موقعیت")
        btn_save.setStyleSheet(
            "background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 6px 20px;")
        btn_save.clicked.connect(self.save_and_close)

        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)
        main_layout.addLayout(bottom_layout)

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
            lambda _: self._update_detected_strategy_label())
        self.table_legs.setCellWidget(row, COL_SIDE, cmb_side)

        # ─── ستون ۳: قیمت اعمال ───
        spin_strike = QSpinBox()
        spin_strike.setRange(0, 1_000_000_000)
        spin_strike.setSingleStep(50)
        spin_strike.setGroupSeparatorShown(True)
        spin_strike.setValue(int(leg.strike_price) if leg else 0)
        spin_strike.valueChanged.connect(
            lambda _: self._update_detected_strategy_label())
        self.table_legs.setCellWidget(row, COL_STRIKE, spin_strike)

        # ─── ستون ۴: تعداد ───
        spin_qty = QSpinBox()
        spin_qty.setRange(1, 100_000_000)
        spin_qty.setGroupSeparatorShown(True)
        spin_qty.setValue(int(leg.quantity) if leg else 1)
        self.table_legs.setCellWidget(row, COL_QTY, spin_qty)

        # ─── ستون ۵: قیمت ورود ───
        spin_entry = QSpinBox()
        spin_entry.setRange(0, 1_000_000_000)
        spin_entry.setSingleStep(10)
        spin_entry.setGroupSeparatorShown(True)
        spin_entry.setValue(int(leg.entry_price) if leg else 0)
        self.table_legs.setCellWidget(row, COL_ENTRY, spin_entry)

        # ─── ستون ۶: تاریخ سررسید ───
        line_expiry = QLineEdit(leg.expiry_date if leg else "")
        line_expiry.setPlaceholderText("1403/06/20")
        self.table_legs.setCellWidget(row, COL_EXPIRY, line_expiry)

        self._apply_leg_row_state(row)
        self._refresh_row_indices()
        self._update_detected_strategy_label()

    def remove_leg_row(self):
        row = self.table_legs.currentRow()
        if row >= 0:
            self._hide_completer()
            self.table_legs.removeRow(row)
            self._refresh_row_indices()
            self._update_detected_strategy_label()

    # =====================================================
    # افزودن سطر جدید و فوکوس
    # =====================================================

    def _add_new_row_and_focus(self):
        last_row = self.table_legs.rowCount() - 1

        if last_row >= 0:
            last_symbol = self.table_legs.cellWidget(last_row, COL_SYMBOL)
            if isinstance(last_symbol, QLineEdit):
                if not last_symbol.text().strip():
                    self.table_legs.setCurrentCell(last_row, COL_SYMBOL)
                    last_symbol.setFocus()
                    last_symbol.selectAll()
                    return

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
    # استخراج لگ‌ها از جدول
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

    # =====================================================
    # به‌روزرسانی لیبل تشخیص خودکار
    # =====================================================

    def _update_detected_strategy_label(self):
        legs = self._collect_legs_from_table()
        if not legs:
            self.lbl_detected_strategy.setText("(تشخیص خودکار: —)")
            self.lbl_detected_strategy.setStyleSheet(
                "color: #9E9E9E; font-size: 10px; "
                "font-weight: bold; padding-right: 4px;")
            self.btn_use_suggestion.setEnabled(False)
            return

        suggested = detect_strategy_name(legs)
        if suggested and suggested != "Strategy":
            self.lbl_detected_strategy.setText(
                f"(تشخیص خودکار: {suggested})")
            self.lbl_detected_strategy.setStyleSheet(
                "color: #1976D2; font-size: 10px; "
                "font-weight: bold; padding-right: 4px;")
            self.btn_use_suggestion.setEnabled(True)
        else:
            self.lbl_detected_strategy.setText("(تشخیص خودکار: —)")
            self.lbl_detected_strategy.setStyleSheet(
                "color: #9E9E9E; font-size: 10px; "
                "font-weight: bold; padding-right: 4px;")
            self.btn_use_suggestion.setEnabled(False)

    def _apply_suggested_strategy(self):
        legs = self._collect_legs_from_table()
        if not legs:
            return
        suggested = detect_strategy_name(legs)
        if suggested and suggested != "Strategy":
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
            spin_strike.setStyleSheet(
                "background-color: #EEEEEE; color: #9E9E9E;")
            line_expiry.setEnabled(False)
            line_expiry.setText("")
            line_expiry.setStyleSheet(
                "background-color: #EEEEEE; color: #9E9E9E;")
        else:
            spin_strike.setEnabled(True)
            spin_strike.setStyleSheet("")
            line_expiry.setEnabled(True)
            line_expiry.setStyleSheet("")

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

        self._hide_completer()
        self._update_detected_strategy_label()

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

        self.add_leg_row()
        self._update_detected_strategy_label()

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
                "لطفاً یک نام برای استراتژی وارد کنید یا از "
                "دکمه «← استفاده» کنار پیشنهاد «تشخیص خودکار» استفاده کنید.")
            self.txt_strategy.setFocus()
            return

        if not exec_date:
            QMessageBox.warning(self, "خطا", "تاریخ اجرا را وارد کنید.")
            return

        legs: List[OptionLeg] = []
        for r in range(self.table_legs.rowCount()):
            line_symbol: QLineEdit = self.table_legs.cellWidget(r, COL_SYMBOL)
            cmb_kind: QComboBox = self.table_legs.cellWidget(r, COL_KIND)
            cmb_side: QComboBox = self.table_legs.cellWidget(r, COL_SIDE)
            spin_strike: QSpinBox = self.table_legs.cellWidget(r, COL_STRIKE)
            spin_qty: QSpinBox = self.table_legs.cellWidget(r, COL_QTY)
            spin_entry: QSpinBox = self.table_legs.cellWidget(r, COL_ENTRY)
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

            leg = OptionLeg(
                symbol=symbol,
                is_option=is_option,
                option_kind=option_kind,
                leg_type=leg_type,
                strike_price=strike if is_option else 0.0,
                contract_size=int(contract_size),
                quantity=qty,
                entry_price=entry_price,
                current_price=entry_price,
                expiry_date=expiry,
                ins_code=ins_code,
            )
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
# ✅ دیالوگ ثبت نکول CALL (جدید)
# =====================================================

class DefaultSettlementDialog(QDialog):
    """
    دیالوگ ثبت نکول CALL در روز سررسید.
    - کاربر قیمت پایانی سهم پایه را وارد/تأیید می‌کند
    - محاسبه خودکار: payment + penalty + exercise_fee
    - net نهایی (مثبت = ذی‌نفع، منفی = متضرر)
    """

    def __init__(self, parent=None, position: StrategyPosition = None):
        super().__init__(parent)
        self.setWindowTitle("ثبت نکول CALL")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(580)

        self.position = position
        self._result = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

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
            "تاریخ سررسید:", QLabel(self.position.expiry_date))

        call_legs = [l for l in self.position.legs if l.is_call]
        if call_legs:
            leg = call_legs[0]
            role = "خریدار (ذی‌نفع)" if leg.leg_type == LegType.BUY \
                else "فروشنده (متضرر)"
            role_lbl = QLabel(role)
            if leg.leg_type == LegType.BUY:
                role_lbl.setStyleSheet(
                    "color: #2E7D32; font-weight: bold;")
            else:
                role_lbl.setStyleSheet(
                    "color: #C62828; font-weight: bold;")
            info_layout.addRow("نقش شما:", role_lbl)

        layout.addWidget(info_group)

        # ─── لگ‌های CALL ───
        call_group = QGroupBox("لگ‌های CALL در این موقعیت")
        call_layout = QVBoxLayout(call_group)

        for i, leg in enumerate(call_legs, 1):
            direction = "خرید" if leg.leg_type == LegType.BUY else "فروش"
            text = (
                f"{i}. {leg.symbol} | {direction} | "
                f"اعمال: {int(leg.strike_price):,} | "
                f"تعداد: {leg.quantity} × {leg.effective_contract_size}"
            )
            call_layout.addWidget(QLabel(text))

        layout.addWidget(call_group)

        # ─── ورودی S_T ───
        input_group = QGroupBox(
            "قیمت پایانی سهم پایه در روز سررسید")
        input_layout = QFormLayout(input_group)

        self.spin_st = QDoubleSpinBox()
        self.spin_st.setRange(0, 1e12)
        self.spin_st.setDecimals(0)
        self.spin_st.setGroupSeparatorShown(True)
        self.spin_st.setSuffix(" ریال")
        self.spin_st.valueChanged.connect(self._update_calculation)

        # مقدار پیش‌فرض: از snapshot.underlying_assets[ticker].close_price
        default_st = 0.0
        try:
            from data.manager import get_market_snapshot
            snap = get_market_snapshot(
                use_cache=True, force_refresh=False)
            default_st = _get_underlying_closing_price(
                snap, self.position.underlying_symbol)
        except Exception as e:
            print(f"[DefaultDialog] S_T load failed: {e}")

        if default_st <= 0:
            default_st = self.position.underlying_price

        self.spin_st.setValue(default_st)

        input_layout.addRow("S_T (پایانی):", self.spin_st)

        st_hint = QLabel(
            "💡 این مقدار از «قیمت پایانی» سهم پایه گرفته شده است.\n"
            "   در صورت نیاز می‌توانید تغییر دهید.")
        st_hint.setStyleSheet("color: #666; font-size: 10px;")
        input_layout.addRow("", st_hint)

        layout.addWidget(input_group)

        # ─── محاسبه خودکار ───
        result_group = QGroupBox("محاسبه خودکار")
        result_layout = QFormLayout(result_group)

        self.lbl_payment = QLabel("—")
        self.lbl_penalty = QLabel("—")
        self.lbl_exercise_fee = QLabel("—")
        self.lbl_total = QLabel("—")
        self.lbl_total.setStyleSheet(
            "font-weight: bold; color: #1976D2; font-size: 13px;")

        result_layout.addRow("💰 وجه تسویه:", self.lbl_payment)
        result_layout.addRow("💸 جریمه ۱٪ نکول:", self.lbl_penalty)
        result_layout.addRow("📋 کارمزد اعمال:", self.lbl_exercise_fee)
        result_layout.addRow("━━━━━━━━━━━", QLabel(""))
        result_layout.addRow("📈 خالص نهایی:", self.lbl_total)

        layout.addWidget(result_group)

        # ─── دکمه‌ها ───
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("✅ تأیید و ثبت نکول")
        buttons.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        # محاسبه اولیه
        self._update_calculation()

    def _get_exercise_rate(self) -> float:
        """گرفتن نرخ کارمزد اعمال از config"""
        try:
            from config import (
                get_exercise_fee_rate,
                get_symbol_market,
                get_symbol_kind,
            )
            market = get_symbol_market(self.position.underlying_symbol)
            kind = get_symbol_kind(self.position.underlying_symbol)
            rate = get_exercise_fee_rate(market, kind)
            return float(rate) if rate else 0.0005
        except Exception:
            return 0.0005

    def _update_calculation(self):
        """محاسبه و نمایش خودکار"""
        S_T = self.spin_st.value()
        exercise_rate = self._get_exercise_rate()

        total_payment = 0.0
        total_penalty = 0.0
        total_exercise_fee = 0.0
        net_total = 0.0

        for leg in self.position.legs:
            if not leg.is_call:
                continue
            r = PositionPnLCalculator.calculate_call_default(
                leg, S_T, exercise_rate=exercise_rate)
            if r["valid"]:
                total_payment += r["payment"]
                total_penalty += r["penalty"]
                total_exercise_fee += r["exercise_fee"]
                net_total += r["net"]

        self.lbl_payment.setText(f"{int(total_payment):,} ریال")
        self.lbl_penalty.setText(f"{int(total_penalty):,} ریال")

        if total_exercise_fee > 0:
            self.lbl_exercise_fee.setText(
                f"{int(total_exercise_fee):,} ریال")
            self.lbl_exercise_fee.setStyleSheet(
                "color: #C62828; font-weight: bold;")
        else:
            self.lbl_exercise_fee.setText("—")
            self.lbl_exercise_fee.setStyleSheet("")

        # رنگ برای خالص
        if net_total >= 0:
            self.lbl_total.setStyleSheet(
                "font-weight: bold; color: #2E7D32; font-size: 13px;")
        else:
            self.lbl_total.setStyleSheet(
                "font-weight: bold; color: #C62828; font-size: 13px;")

        self.lbl_total.setText(f"{int(net_total):,} ریال")

        self._result = {
            "S_T": S_T,
            "payment": total_payment,
            "penalty": total_penalty,
            "exercise_fee": total_exercise_fee,
            "net": net_total,
            "exercise_rate": exercise_rate,
        }

    def _on_accept(self):
        if not self._result or self._result["S_T"] <= 0:
            QMessageBox.warning(
                self, "خطا",
                "قیمت پایانی سهم پایه (S_T) باید بزرگ‌تر از صفر باشد.")
            return
        self.accept()

    def get_result(self) -> dict:
        return self._result