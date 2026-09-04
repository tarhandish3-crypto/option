# -*- coding: utf-8 -*-
"""
دیالوگ تنظیم قیمت دستی برای نمادهای پایه
"""

import logging
from typing import Dict, Optional, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QGroupBox,
    QMessageBox, QDialogButtonBox, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QBrush, QColor, QDoubleValidator

from ui.settings_manager import settings_manager
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.CustomPriceDialog")


class CustomPriceDialog(QDialog):
    """دیالوگ تنظیم قیمت دستی برای نمادهای پایه"""
    
    prices_updated = Signal(dict)  # سیگنال برای اطلاع از تغییرات
    
    def __init__(
        self,
        option_symbols: List[str],
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("⚙️ تنظیم قیمت دستی نمادهای پایه")
        self.resize(600, 500)
        self.setMinimumSize(500, 400)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.option_symbols = option_symbols
        self.custom_prices: Dict[str, float] = settings_manager.get_custom_prices()
        self._theme_mode = ui_theme.current_mode()
        
        self._init_ui()
        self._apply_dialog_theme()
        self._populate_table()
    
    def _apply_dialog_theme(self) -> None:
        mode = ui_theme.current_mode()
        self._theme_mode = mode
    
    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # توضیحات
        info_group = QGroupBox("راهنما")
        info_layout = QVBoxLayout(info_group)
        
        info_label = QLabel(
            "💡 در این پنجره می‌توانید قیمت دستی برای نمادهای پایه تنظیم کنید.\n"
            "این قیمت‌ها جایگزین قیمت فعلی بازار در محاسبات اسکنر خواهند شد.\n"
            "این قابلیت برای ارزیابی استراتژی‌ها با قیمت سهم موجود در پرتفوی شما کاربرد دارد."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #58a6ff; padding: 5px;")
        info_layout.addWidget(info_label)
        
        main_layout.addWidget(info_group)
        
        # جدول قیمت‌ها
        table_group = QGroupBox("لیست نمادهای دارای قرارداد اختیار")
        table_layout = QVBoxLayout(table_group)
        
        self.price_table = QTableWidget()
        self.price_table.setColumnCount(3)
        self.price_table.setHorizontalHeaderLabels(["نماد", "قیمت دستی", "عملیات"])
        self.price_table.setAlternatingRowColors(True)
        self.price_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.price_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = self.price_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.price_table.setColumnWidth(2, 100)
        
        table_layout.addWidget(self.price_table)
        
        # دکمه‌های جدول
        table_buttons = QHBoxLayout()
        
        self.btn_add = QPushButton("➕ افزودن قیمت جدید")
        self.btn_add.clicked.connect(self._add_new_price)
        self.btn_add.setStyleSheet("background-color: #238636; color: white; font-weight: bold;")
        table_buttons.addWidget(self.btn_add)
        
        self.btn_clear_all = QPushButton("🧹 پاک کردن همه")
        self.btn_clear_all.clicked.connect(self._clear_all_prices)
        self.btn_clear_all.setStyleSheet("background-color: #d73a49; color: white;")
        table_buttons.addWidget(self.btn_clear_all)
        
        table_layout.addLayout(table_buttons)
        main_layout.addWidget(table_group)
        
        # دکمه‌های پایین
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal, self
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("✅ ذخیره و خروج")
        button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold;"
        )
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)
    
    def _populate_table(self) -> None:
        """پر کردن جدول با نمادها و قیمت‌های موجود"""
        self.price_table.setRowCount(0)
        
        # ترکیب نمادهای دارای قرارداد با قیمت‌های دستی موجود
        all_symbols = sorted(set(self.option_symbols) | set(self.custom_prices.keys()))
        
        for row_idx, symbol in enumerate(all_symbols):
            self.price_table.insertRow(row_idx)
            
            # ستون نماد
            symbol_item = QTableWidgetItem(symbol)
            symbol_item.setFlags(symbol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            # اگر قیمت دستی دارد، با رنگ خاص نشان بده
            has_custom = symbol in self.custom_prices
            if has_custom:
                symbol_item.setForeground(QBrush(QColor("#f0883e")))
                symbol_item.setFont(QFont("Vazirmatn", 10, QFont.Weight.Bold))
            
            self.price_table.setItem(row_idx, 0, symbol_item)
            
            # ستون قیمت
            price_value = self.custom_prices.get(symbol, "")
            price_item = QTableWidgetItem(str(price_value) if price_value else "")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.price_table.setItem(row_idx, 1, price_item)
            
            # ستون عملیات
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(5, 2, 5, 2)
            
            btn_edit = QPushButton("✏️")
            btn_edit.setToolTip("ویرایش قیمت")
            btn_edit.setMaximumWidth(40)
            btn_edit.clicked.connect(lambda checked, s=symbol: self._edit_price(s))
            btn_layout.addWidget(btn_edit)
            
            btn_delete = QPushButton("🗑️")
            btn_delete.setToolTip("حذف قیمت")
            btn_delete.setMaximumWidth(40)
            btn_delete.clicked.connect(lambda checked, s=symbol: self._delete_price(s))
            btn_delete.setStyleSheet("background-color: #d73a49; color: white;")
            btn_layout.addWidget(btn_delete)
            
            self.price_table.setCellWidget(row_idx, 2, btn_widget)
        
        # به‌روزرسانی تعداد
        logger.info(f"Loaded {len(all_symbols)} symbols, {len(self.custom_prices)} with custom prices")
    
    def _add_new_price(self) -> None:
        """افزودن قیمت جدید"""
        # دریافت نماد از کاربر
        from PySide6.QtWidgets import QInputDialog, QComboBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("افزودن قیمت دستی")
        dialog.setMinimumWidth(350)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        layout = QVBoxLayout(dialog)
        
        # انتخاب نماد
        layout.addWidget(QLabel("نماد:"))
        symbol_combo = QComboBox()
        symbol_combo.addItems(self.option_symbols)
        symbol_combo.setEditable(True)
        layout.addWidget(symbol_combo)
        
        # وارد کردن قیمت
        layout.addWidget(QLabel("قیمت (ریال):"))
        price_input = QLineEdit()
        price_input.setPlaceholderText("مثال: 12500")
        price_input.setValidator(QDoubleValidator(0, 999999999, 0))
        layout.addWidget(price_input)
        
        # دکمه‌ها
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("✅ ذخیره")
        btn_save.setStyleSheet("background-color: #238636; color: white;")
        btn_save.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            symbol = symbol_combo.currentText().strip().upper()
            price_text = price_input.text().strip()
            
            if not symbol:
                QMessageBox.warning(self, "خطا", "لطفاً نماد را انتخاب کنید.")
                return
            
            if not price_text:
                QMessageBox.warning(self, "خطا", "لطفاً قیمت را وارد کنید.")
                return
            
            try:
                price = float(price_text)
                if price <= 0:
                    raise ValueError("Price must be positive")
                
                self.custom_prices[symbol] = price
                self._populate_table()
                
            except ValueError as e:
                QMessageBox.warning(self, "خطا", f"قیمت نامعتبر است: {e}")
    
    def _edit_price(self, symbol: str) -> None:
        """ویرایش قیمت یک نماد"""
        current_price = self.custom_prices.get(symbol, 0)
        
        from PySide6.QtWidgets import QInputDialog
        
        price, ok = QInputDialog.getDouble(
            self,
            f"ویرایش قیمت {symbol}",
            "قیمت جدید (ریال):",
            value=current_price,
            min=0,
            max=999999999,
            decimals=0
        )
        
        if ok and price > 0:
            self.custom_prices[symbol] = price
            self._populate_table()
    
    def _delete_price(self, symbol: str) -> None:
        """حذف قیمت یک نماد"""
        if symbol in self.custom_prices:
            reply = QMessageBox.question(
                self,
                "تأیید حذف",
                f"آیا از حذف قیمت دستی برای نماد '{symbol}' مطمئن هستید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                del self.custom_prices[symbol]
                self._populate_table()
    
    def _clear_all_prices(self) -> None:
        """پاک کردن همه قیمت‌ها"""
        if not self.custom_prices:
            return
        
        reply = QMessageBox.question(
            self,
            "تأیید",
            f"آیا از پاک کردن تمام {len(self.custom_prices)} قیمت دستی مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.custom_prices.clear()
            self._populate_table()
    
    def _save_and_accept(self) -> None:
        """ذخیره و خروج"""
        settings_manager.set_custom_prices(self.custom_prices)
        self.prices_updated.emit(self.custom_prices)
        
        QMessageBox.information(
            self,
            "موفق",
            f"✅ {len(self.custom_prices)} قیمت دستی ذخیره شد."
        )
        
        self.accept()
    
    def get_custom_prices(self) -> Dict[str, float]:
        """دریافت قیمت‌های دستی"""
        return self.custom_prices.copy()
