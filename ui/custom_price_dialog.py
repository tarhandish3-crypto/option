# -*- coding: utf-8 -*-
"""
دیالوگ تنظیم قیمت دستی برای نمادهای پایه
"""

import logging
from typing import Dict, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QGroupBox,
    QMessageBox, QDialogButtonBox, QHeaderView, QAbstractItemView,
    QWidget, QListWidget, QListWidgetItem, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QBrush, QColor, QDoubleValidator, QPalette

from ui.settings_manager import settings_manager
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.CustomPriceDialog")


# ─────────────────────────────────────────────────────────────────────────────
# ۱. دیالوگ انتخاب نماد با چک‌باکس تک‌انتخابی
# ─────────────────────────────────────────────────────────────────────────────

class SymbolSelectionDialog(QDialog):
    """دیالوگ انتخاب نماد پایه با چک‌باکس"""

    def __init__(self, option_symbols: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("انتخاب نماد پایه")
        self.setMinimumSize(380, 400)
        self.resize(380, 420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.selected_symbol: str | None = None
        self._option_symbols = sorted(option_symbols)
        self._current_checked: QListWidgetItem | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        lbl = QLabel("یک نماد پایه را انتخاب کنید:")
        lbl.setStyleSheet("font-weight: bold; color: #58a6ff;")
        layout.addWidget(lbl)

        # جستجو
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 جستجو...")
        self.search_input.textChanged.connect(self._filter)
        layout.addWidget(self.search_input)

        # لیست
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        for sym in self._option_symbols:
            item = QListWidgetItem(sym)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        # دکمه‌ها
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("✅ تأیید")
        btn_ok.setStyleSheet("background-color:#238636; color:white; font-weight:bold; padding:6px 18px;")
        btn_ok.clicked.connect(self._accept_selection)
        btn_row.addWidget(btn_ok)

        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _filter(self, text: str) -> None:
        t = text.strip().upper()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(bool(t) and t not in item.text().upper())

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.CheckState.Checked:
            self.list_widget.blockSignals(True)
            for i in range(self.list_widget.count()):
                other = self.list_widget.item(i)
                if other is not item:
                    other.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.blockSignals(False)
            self._current_checked = item
        else:
            if self._current_checked is item:
                self._current_checked = None

    def _accept_selection(self) -> None:
        if self._current_checked is None:
            QMessageBox.warning(self, "خطا", "لطفاً یک نماد را انتخاب کنید.")
            return
        self.selected_symbol = self._current_checked.text()
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# ۲. دیالوگ ورود قیمت
# ─────────────────────────────────────────────────────────────────────────────

class PriceInputDialog(QDialog):
    """دیالوگ وارد کردن قیمت دستی برای یک نماد"""

    def __init__(self, symbol: str, current_price: float = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"تنظیم قیمت — {symbol}")
        self.setMinimumWidth(350)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.symbol = symbol
        self.price: float = current_price

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        sym_lbl = QLabel(f"نماد پایه: {self.symbol}")
        sym_lbl.setStyleSheet("font-size:16px; font-weight:bold; color:#f0883e; padding:4px;")
        layout.addWidget(sym_lbl)

        price_lbl = QLabel("قیمت دستی (ریال):")
        price_lbl.setStyleSheet("font-weight:bold;")
        layout.addWidget(price_lbl)

        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("مثال: 12500")
        if self.price > 0:
            self.price_input.setText(str(int(self.price)))
        self.price_input.setValidator(QDoubleValidator(0, 999_999_999, 0))
        self.price_input.setStyleSheet("font-size:14px; padding:8px;")
        self.price_input.returnPressed.connect(self._accept_price)
        layout.addWidget(self.price_input)

        hint = QLabel("💡 این قیمت جایگزین قیمت فعلی بازار در تمام محاسبات اسکنر می‌شود.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("✅ تأیید")
        btn_ok.setStyleSheet("background-color:#238636; color:white; font-weight:bold; padding:8px 24px;")
        btn_ok.clicked.connect(self._accept_price)
        btn_row.addWidget(btn_ok)

        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.price_input.setFocus()

    def _accept_price(self) -> None:
        text = self.price_input.text().strip().replace(",", "")
        if not text:
            QMessageBox.warning(self, "خطا", "لطفاً قیمت را وارد کنید.")
            return
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
            self.price = val
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "خطا", "قیمت باید یک عدد مثبت باشد.")


# ─────────────────────────────────────────────────────────────────────────────
# ۳. دیالوگ اصلی مدیریت قیمت‌های دستی
# ─────────────────────────────────────────────────────────────────────────────

class CustomPriceDialog(QDialog):
    """دیالوگ تنظیم قیمت دستی برای نمادهای پایه"""

    prices_updated = Signal(dict)

    def __init__(self, option_symbols: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ تنظیم قیمت دستی نمادهای پایه")
        self.resize(620, 580)
        self.setMinimumSize(500, 480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.option_symbols = option_symbols
        self.custom_prices: Dict[str, float] = settings_manager.get_custom_prices()
        self._custom_prices_enabled: bool = settings_manager.get_custom_prices_enabled()

        self._init_ui()
        self._populate_table()
        self._update_table_state()

    def _init_ui(self) -> None:
        main = QVBoxLayout(self)
        main.setSpacing(8)
        main.setContentsMargins(12, 12, 12, 12)

        # ---- چک‌باکس فعال/غیرفعال ----
        self.enable_checkbox = QCheckBox("✅ فعال‌سازی قیمت‌های دستی")
        self.enable_checkbox.setChecked(self._custom_prices_enabled)
        self.enable_checkbox.setStyleSheet("font-weight: bold; font-size: 13px; color: #2ecc71;")
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        main.addWidget(self.enable_checkbox)

        # ---- دکمه انتخاب نماد (کوچکتر) ----
        add_layout = QHBoxLayout()
        add_layout.addStretch()
        
        self.btn_select = QPushButton("📋 انتخاب نماد")
        self.btn_select.setStyleSheet(
            "background-color:#1f6feb; color:white; font-weight:bold;"
            " padding:6px 20px; font-size:12px; border-radius:4px;"
        )
        self.btn_select.clicked.connect(self._open_symbol_selection)
        add_layout.addWidget(self.btn_select)
        add_layout.addStretch()
        
        main.addLayout(add_layout)

        # ---- جدول ----
        table_box = QGroupBox("لیست قیمت‌های دستی تنظیم‌شده")
        table_layout = QVBoxLayout(table_box)
        table_layout.setSpacing(4)

        # جستجو
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("🔍 جستجو:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو در جدول...")
        self.search_input.textChanged.connect(self._filter_table)
        search_row.addWidget(self.search_input)
        table_layout.addLayout(search_row)

        self.price_table = QTableWidget()
        self.price_table.setColumnCount(3)
        self.price_table.setHorizontalHeaderLabels(["نماد", "قیمت دستی", "عملیات"])
        self.price_table.setAlternatingRowColors(True)
        self.price_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.price_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.price_table.itemDoubleClicked.connect(self._on_double_click)

        hdr = self.price_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.price_table.setColumnWidth(0, 100)
        self.price_table.setColumnWidth(2, 180)

        table_layout.addWidget(self.price_table)

        # دکمه پاک کردن
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        btn_clear = QPushButton("🧹 پاک کردن همه")
        btn_clear.setStyleSheet("background-color:#d73a49; color:white;")
        btn_clear.clicked.connect(self._clear_all)
        clear_row.addWidget(btn_clear)
        table_layout.addLayout(clear_row)

        main.addWidget(table_box)
        
        # دکمه تست ذخیره (برای دیباگ)
        test_save_row = QHBoxLayout()
        test_save_row.addStretch()
        btn_test = QPushButton("⚡ تست ذخیره")
        btn_test.setStyleSheet("background-color:#f39c12; color:white;")
        btn_test.clicked.connect(self._test_save)
        test_save_row.addWidget(btn_test)
        test_save_row.addStretch()
        main.addLayout(test_save_row)

        # ---- دکمه‌های پایین ----
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal, self
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("✅ ذخیره و خروج")
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background-color:#2ecc71; color:white; font-weight:bold;"
        )
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        main.addWidget(btn_box)

    # ──────────────────────────────────────────────────────────────────
    # عملیات
    # ──────────────────────────────────────────────────────────────────

    def _on_enable_changed(self, state: int) -> None:
        self._custom_prices_enabled = state == Qt.CheckState.Checked.value
        self._update_table_state()
        settings_manager.set_custom_prices_enabled(self._custom_prices_enabled)

    def _update_table_state(self) -> None:
        """فعال/غیرفعال کردن جدول"""
        enabled = self._custom_prices_enabled
        
        # رنگ جدول
        if enabled:
            self.price_table.setStyleSheet("")
            self.price_table.setDisabled(False)
            self.enable_checkbox.setStyleSheet("font-weight: bold; font-size: 13px; color: #2ecc71;")
            self.enable_checkbox.setText("✅ فعال‌سازی قیمت‌های دستی")
        else:
            self.price_table.setStyleSheet("QTableWidget { background-color: #3a3a3a; color: #666; }")
            self.price_table.setDisabled(True)
            self.enable_checkbox.setStyleSheet("font-weight: bold; font-size: 13px; color: #888;")
            self.enable_checkbox.setText("❌ غیرفعال - قیمت‌های دستی استفاده نمی‌شوند")

    def _open_symbol_selection(self) -> None:
        dlg = SymbolSelectionDialog(self.option_symbols, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_symbol:
            self._open_price_input(dlg.selected_symbol)

    def _open_price_input(self, symbol: str) -> None:
        current = self.custom_prices.get(symbol, 0.0)
        dlg = PriceInputDialog(symbol, current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.custom_prices[symbol] = dlg.price
            self._populate_table()

    def _populate_table(self) -> None:
        self.price_table.setRowCount(0)
        symbols = sorted(self.custom_prices.keys())

        for row, sym in enumerate(symbols):
            self.price_table.insertRow(row)

            # نماد
            sym_item = QTableWidgetItem(sym)
            sym_item.setFlags(sym_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            sym_item.setForeground(QBrush(QColor("#f0883e")))
            sym_item.setFont(QFont("Vazirmatn", 10, QFont.Weight.Bold))
            self.price_table.setItem(row, 0, sym_item)

            # قیمت
            price_val = self.custom_prices[sym]
            price_item = QTableWidgetItem(f"{price_val:,.0f} ریال")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.price_table.setItem(row, 1, price_item)

            # عملیات
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setSpacing(4)

            btn_edit = QPushButton("✏️ تغییر")
            btn_edit.setStyleSheet(
                "background-color:#1f6feb; color:white; border-radius:4px; font-weight:bold;"
            )
            btn_edit.setFixedHeight(26)
            btn_edit.clicked.connect(lambda _, s=sym: self._open_price_input(s))
            cell_layout.addWidget(btn_edit)

            btn_del = QPushButton("🗑️ حذف")
            btn_del.setStyleSheet(
                "background-color:#d73a49; color:white; border-radius:4px; font-weight:bold;"
            )
            btn_del.setFixedHeight(26)
            btn_del.clicked.connect(lambda _, s=sym: self._delete_price(s))
            cell_layout.addWidget(btn_del)

            self.price_table.setCellWidget(row, 2, cell)
            self.price_table.setRowHeight(row, 34)

        logger.info(f"Table updated: {len(symbols)} custom prices")

    def _filter_table(self, text: str) -> None:
        t = text.strip().upper()
        for row in range(self.price_table.rowCount()):
            item = self.price_table.item(row, 0)
            if item:
                self.price_table.setRowHidden(row, bool(t) and t not in item.text().upper())

    def _on_double_click(self, item) -> None:
        if item.column() == 1:
            sym_item = self.price_table.item(item.row(), 0)
            if sym_item:
                self._open_price_input(sym_item.text())

    def _delete_price(self, symbol: str) -> None:
        reply = QMessageBox.question(
            self, "تأیید حذف",
            f"آیا از حذف قیمت دستی نماد «{symbol}» مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.custom_prices.pop(symbol, None)
            self._populate_table()

    def _clear_all(self) -> None:
        if not self.custom_prices:
            return
        reply = QMessageBox.question(
            self, "تأیید",
            f"پاک کردن تمام {len(self.custom_prices)} قیمت دستی؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.custom_prices.clear()
            self._populate_table()

    def _save_and_accept(self) -> None:
        """ذخیره و خروج"""
        try:
            settings_manager.set_custom_prices(self.custom_prices)
            settings_manager.set_custom_prices_enabled(self._custom_prices_enabled)
            self.prices_updated.emit(self.custom_prices)
            
            # لاگ برای دیباگ
            logger.info(f"Custom prices saved: {len(self.custom_prices)} symbols, enabled: {self._custom_prices_enabled}")
            
            self.accept()
        except Exception as e:
            logger.error(f"Error saving custom prices: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره‌سازی:\n{str(e)}")
    
    def _test_save(self) -> None:
        """تست دستی ذخیره‌سازی"""
        try:
            settings_manager.set_custom_prices(self.custom_prices)
            settings_manager.set_custom_prices_enabled(self._custom_prices_enabled)
            
            QMessageBox.information(
                self,
                "تست موفق",
                f"✅ {len(self.custom_prices)} قیمت دستی ذخیره شد.\n"
                f"وضعیت فعال‌سازی: {self._custom_prices_enabled}"
            )
        except Exception as e:
            QMessageBox.critical(self, "خطای تست", f"خطا در ذخیره‌سازی:\n{str(e)}")

    def get_custom_prices(self) -> Dict[str, float]:
        return self.custom_prices.copy()
