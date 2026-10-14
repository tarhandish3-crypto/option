# position_saver/ui/symbol_fill_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ پر کردن گروهی اطلاعات یک نماد.

کاربرد:
    کاربر نماد را انتخاب می‌کند، strike و expiry را وارد می‌کند
    و روی «⚡ اعمال به همه» می‌زند → همه‌ی ردیف‌های همان نماد پر می‌شوند.

این دیالوگ برای مواردی است که کاربر نمی‌خواهد از Live Sync استفاده کند
یا می‌خواهد اطلاعات کامل‌تری وارد کند.
"""

import logging
import re
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QLabel, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QAbstractSpinBox,
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator

from position_saver.theme import (
    Theme, fmt_money, fmt_int, set_kind, set_tone,
)
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.UI.SymbolFill")


class SymbolFillDialog(QDialog):
    """
    دیالوگ پر کردن گروهی اطلاعات یک نماد.

    استفاده:
        dlg = SymbolFillDialog(parent, symbol="ضفزر614", trades=[...])
        if dlg.exec():
            result = dlg.get_result()
            # result = {
            #     "symbol": "ضفزر614",
            #     "strike_price": 140000.0,
            #     "expiry_date": "1405/05/25",
            #     "underlying_symbol": "فزر",
            #     "contract_size": 1000,
            # }
    """

    def __init__(self, parent=None,
                 symbol: str = "",
                 trades: Optional[List] = None,
                 initial_info: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(f"⚡ پر کردن گروهی — {symbol}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(620)

        self.symbol = symbol
        self.trades = trades or []
        self.initial_info = initial_info or {}
        self._result: Optional[dict] = None

        self._build_ui()
        self._load_initial()

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── اطلاعات نماد ───
        info_group = QGroupBox("اطلاعات نماد")
        info_form = QFormLayout(info_group)

        info_form.addRow("نماد:", QLabel(self.symbol))

        kind_text = "—"
        if self.symbol.startswith("ض"):
            kind_text = "CALL (اختیار خرید)"
        elif self.symbol.startswith("ط"):
            kind_text = "PUT (اختیار فروش)"
        info_form.addRow("نوع:", QLabel(kind_text))

        info_form.addRow(
            "تعداد ردیف‌های ناقص:",
            QLabel(f"{len(self.trades)} ردیف"))

        # نمایش وضعیت حافظه
        if self.initial_info:
            from position_saver.importer.symbol_memory import get_symbol_info
            cached = get_symbol_info(self.symbol)
            if cached:
                last = cached.get("last_updated", "—")
                lbl_cached = QLabel(f"✅ قبلاً ذخیره شده (آخرین: {last})")
                set_tone(lbl_cached, "profit")
                info_form.addRow("", lbl_cached)

        layout.addWidget(info_group)

        # ─── اطلاعات ورودی ───
        form_group = QGroupBox("اطلاعات تکمیلی")
        form = QFormLayout(form_group)

        # قیمت اعمال
        self.spin_strike = QSpinBox()
        self.spin_strike.setRange(0, 1_000_000_000)
        self.spin_strike.setSingleStep(50)
        self.spin_strike.setGroupSeparatorShown(True)
        self.spin_strike.setButtonSymbols(QAbstractSpinBox.NoButtons)
        form.addRow("قیمت اعمال:", self.spin_strike)

        # سررسید
        self.txt_expiry = QLineEdit()
        self.txt_expiry.setPlaceholderText("1405/05/25")
        validator = QRegularExpressionValidator(
            QRegularExpression(r'^\d{0,4}(/\d{0,2}(/\d{0,2})?)?$'))
        self.txt_expiry.setValidator(validator)
        form.addRow("تاریخ سررسید:", self.txt_expiry)

        # نماد پایه
        self.txt_underlying = QLineEdit()
        self.txt_underlying.setPlaceholderText("مثلاً فزر")
        form.addRow("نماد پایه (اختیاری):", self.txt_underlying)

        # Contract size
        self.spin_contract_size = QSpinBox()
        self.spin_contract_size.setRange(1, 1_000_000)
        self.spin_contract_size.setValue(1000)
        self.spin_contract_size.setGroupSeparatorShown(True)
        self.spin_contract_size.setButtonSymbols(QAbstractSpinBox.NoButtons)
        form.addRow("اندازه قرارداد:", self.spin_contract_size)

        layout.addWidget(form_group)

        # ─── پیش‌نمایش ردیف‌ها ───
        if self.trades:
            preview_group = QGroupBox(
                f"ردیف‌هایی که پر خواهند شد ({len(self.trades)} مورد)")
            preview_layout = QVBoxLayout(preview_group)

            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(
                ["تاریخ", "ساعت", "سمت", "قیمت"])
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.Interactive)
            table.horizontalHeader().setStretchLastSection(True)
            table.setColumnWidth(0, 110)
            table.setColumnWidth(1, 90)
            table.setColumnWidth(2, 70)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setAlternatingRowColors(True)

            for t in self.trades[:10]:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(
                    getattr(t, "raw_date", "—")))
                table.setItem(row, 1, QTableWidgetItem(
                    getattr(t, "raw_time", "—")))
                side_label = "—"
                if hasattr(t, "side"):
                    side_label = t.side.label_fa
                table.setItem(row, 2, QTableWidgetItem(side_label))
                price = getattr(t, "price", 0)
                table.setItem(row, 3, QTableWidgetItem(
                    fmt_money(price)))

            preview_layout.addWidget(table)

            if len(self.trades) > 10:
                lbl_more = QLabel(
                    f"... و {len(self.trades) - 10} ردیف دیگر")
                set_tone(lbl_more, "muted")
                preview_layout.addWidget(lbl_more)

            # ارتفاع بر اساس تعداد ردیف
            h = min(200, 30 * min(len(self.trades), 10) + 40)
            table.setFixedHeight(h)

            layout.addWidget(preview_group)

        # ─── دکمه‌ها ───
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(
            f"⚡ اعمال به {len(self.trades)} ردیف")
        btns.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        set_kind(btns.button(QDialogButtonBox.Ok), "primary")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ═══════════════════════════════════════════════
    # بارگذاری اولیه
    # ═══════════════════════════════════════════════

    def _load_initial(self):
        """بارگذاری اطلاعات اولیه از حافظه یا ورودی"""
        info = self.initial_info

        if info.get("strike_price"):
            self.spin_strike.setValue(int(info["strike_price"]))

        if info.get("expiry_date"):
            self.txt_expiry.setText(str(info["expiry_date"]))

        if info.get("underlying_symbol"):
            self.txt_underlying.setText(
                str(info["underlying_symbol"]))
        else:
            # حدس از پیشوند نماد
            if self.symbol.startswith(("ض", "ط")):
                s = self.symbol[1:]
                m = re.match(r'([^\d]+)', s)
                if m:
                    self.txt_underlying.setText(m.group(1).strip())

        if info.get("contract_size"):
            self.spin_contract_size.setValue(
                int(info["contract_size"]))

    # ═══════════════════════════════════════════════
    # تأیید
    # ═══════════════════════════════════════════════

    def _on_accept(self):
        strike = self.spin_strike.value()
        expiry = self.txt_expiry.text().strip()
        underlying = self.txt_underlying.text().strip()
        contract_size = self.spin_contract_size.value()

        if strike <= 0:
            QMessageBox.warning(
                self, "خطا",
                "لطفاً قیمت اعمال را وارد کنید.")
            self.spin_strike.setFocus()
            return

        if not expiry:
            QMessageBox.warning(
                self, "خطا",
                "لطفاً تاریخ سررسید را وارد کنید.")
            self.txt_expiry.setFocus()
            return

        if not re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', expiry):
            QMessageBox.warning(
                self, "خطا",
                "تاریخ سررسید نامعتبر است.\n"
                "فرمت صحیح: YYYY/MM/DD")
            self.txt_expiry.setFocus()
            return

        self._result = {
            "symbol": self.symbol,
            "strike_price": float(strike),
            "expiry_date": expiry,
            "underlying_symbol": underlying,
            "contract_size": int(contract_size),
        }

        self.accept()

    def get_result(self) -> Optional[dict]:
        return self._result


__all__ = ["SymbolFillDialog"]