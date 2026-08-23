# ui/symbol_filter_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ مدیریت فیلتر نمادها (Symbol Filter Dialog) با پشتیبانی کامل از پوسته تاریک و روشن
"""

import logging
import json
import re
from typing import List, Set, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QGroupBox,
    QMessageBox, QDialogButtonBox, QFileDialog,
    QComboBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QBrush, QColor

from ui.settings_manager import settings_manager
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.SymbolFilter")


class SymbolFilterDialog(QDialog):
    symbols_updated = Signal(list)
    categories_updated = Signal(dict)

    def __init__(
        self, 
        available_symbols: Optional[List[str]] = None, 
        currently_excluded: Optional[List[str]] = None,
        symbol_categories: Optional[Dict[str, List[str]]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("مدیریت و فیلتر نمادها")
        self.resize(620, 720)
        self.setMinimumSize(520, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.available_symbols: List[str] = available_symbols or []
        
        persisted = settings_manager.get_excluded_symbols()
        initial = persisted if persisted else (currently_excluded or [])
        
        self.excluded_symbols: Set[str] = set(initial)
        self._initial_excluded: Set[str] = set(initial)
        self.symbol_categories: Dict[str, List[str]] = symbol_categories or {}
        self._current_search_text = ""
        self._theme_mode = ui_theme.current_mode()

        self._init_ui()
        self._apply_dialog_theme()
        self._populate_list()
        self._update_stats()

    def _apply_dialog_theme(self) -> None:
        mode = ui_theme.current_mode()
        self._theme_mode = mode
        if hasattr(self, "info_label"):
            self.info_label.setStyleSheet(ui_theme.get_symbol_filter_info_style(mode))
        if hasattr(self, "stats_label"):
            self.stats_label.setStyleSheet(ui_theme.get_symbol_filter_stats_style(mode))

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        header_group = QGroupBox("جستجو و فیلتر")
        header_layout = QVBoxLayout(header_group)

        info_label = QLabel(
            "نمادهایی که چک‌باکس آن‌ها فعال است، از محاسبات اسکنر حذف (Block) خواهند شد:"
        )
        self.info_label = info_label
        info_label.setWordWrap(True)
        header_layout.addWidget(info_label)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("جستجو:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("نام نماد (مثلا: خودرو، ضخود، اهرم...)...")
        self.search_input.textChanged.connect(self._filter_list_items)
        filter_layout.addWidget(self.search_input)

        if self.symbol_categories:
            filter_layout.addWidget(QLabel("دسته‌بندی:"))
            self.category_combo = QComboBox()
            self.category_combo.addItem("همه دسته‌بندی‌ها")
            self.category_combo.addItems(sorted(self.symbol_categories.keys()))
            self.category_combo.currentTextChanged.connect(self._filter_by_category)
            filter_layout.addWidget(self.category_combo)
        else:
            self.category_combo = None

        header_layout.addLayout(filter_layout)
        main_layout.addWidget(header_group)

        list_group = QGroupBox("لیست نمادهای بازار")
        list_layout = QVBoxLayout(list_group)

        self.stats_label = QLabel("📊 آماده‌سازی...")
        list_layout.addWidget(self.stats_label)

        self.symbol_list_widget = QListWidget()
        self.symbol_list_widget.setAlternatingRowColors(True)
        self.symbol_list_widget.setFont(QFont("Vazirmatn", 10))
        self.symbol_list_widget.itemChanged.connect(self._on_item_checked)
        list_layout.addWidget(self.symbol_list_widget)

        operation_group = QGroupBox("عملیات گروهی و فایل")
        operation_layout = QGridLayout(operation_group)

        self.btn_select_all = QPushButton("✅ بلاک کردن همه (نمایشی)")
        self.btn_select_all.clicked.connect(lambda: self._set_all_checks(True))
        operation_layout.addWidget(self.btn_select_all, 0, 0)

        self.btn_deselect_all = QPushButton("❌ آن‌بلاک همه (نمایشی)")
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_checks(False))
        operation_layout.addWidget(self.btn_deselect_all, 0, 1)

        self.btn_remove_selected = QPushButton("🗑️ حذف از لیست")
        self.btn_remove_selected.clicked.connect(self._remove_selected_symbol)
        self.btn_remove_selected.setStyleSheet("background-color: #e74c3c; color: white;")
        operation_layout.addWidget(self.btn_remove_selected, 0, 2)

        self.btn_import = QPushButton("📥 بارگذاری از فایل")
        self.btn_import.clicked.connect(self._import_list)
        operation_layout.addWidget(self.btn_import, 1, 0)

        self.btn_export = QPushButton("📤 خروجی به فایل")
        self.btn_export.clicked.connect(self._export_list)
        operation_layout.addWidget(self.btn_export, 1, 1)

        self.btn_clear_all = QPushButton("🧹 پاک کردن همه استثناها")
        self.btn_clear_all.clicked.connect(self._clear_all_exclusions)
        self.btn_clear_all.setStyleSheet("background-color: #d35400; color: white;")
        operation_layout.addWidget(self.btn_clear_all, 1, 2)

        list_layout.addWidget(operation_group)
        main_layout.addWidget(list_group)

        custom_group = QGroupBox("افزودن نماد دستی")
        custom_layout = QHBoxLayout(custom_group)

        self.custom_symbol_input = QLineEdit()
        self.custom_symbol_input.setPlaceholderText("نام نماد (حروف فارسی، انگلیسی، اعداد)...")
        self.custom_symbol_input.returnPressed.connect(self._add_custom_symbol)
        
        self.btn_add_custom = QPushButton("➕ افزودن به استثناها")
        self.btn_add_custom.clicked.connect(self._add_custom_symbol)
        self.btn_add_custom.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")

        custom_layout.addWidget(self.custom_symbol_input)
        custom_layout.addWidget(self.btn_add_custom)
        main_layout.addWidget(custom_group)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Reset,
            Qt.Orientation.Horizontal, self
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("✅ تایید و ذخیره")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).setText("↩️ بازنشانی اولیه")
        
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset_to_initial)

        main_layout.addWidget(self.button_box)

    def _get_item_colors(self, is_excluded: bool):
        is_dark = (self._theme_mode == "dark")
        if is_excluded:
            bg = QColor("#442c2d") if is_dark else QColor("#ffebee")
            fg = QColor("#f85149") if is_dark else QColor("#c62828")
        else:
            bg = QColor("#22272e") if is_dark else QColor("#ffffff")
            fg = QColor("#cdd9e5") if is_dark else QColor("#24292e")
        return bg, fg

    def _populate_list(self) -> None:
        self.symbol_list_widget.blockSignals(True)
        self.symbol_list_widget.clear()

        all_unique = sorted(list(set(self.available_symbols) | self.excluded_symbols))

        for symbol in all_unique:
            item = QListWidgetItem(symbol)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            
            is_excluded = symbol in self.excluded_symbols
            bg, fg = self._get_item_colors(is_excluded)
            
            item.setCheckState(Qt.CheckState.Checked if is_excluded else Qt.CheckState.Unchecked)
            item.setBackground(QBrush(bg))
            item.setForeground(QBrush(fg))

            self.symbol_list_widget.addItem(item)

        self.symbol_list_widget.blockSignals(False)
        self._update_stats()

    def _update_stats(self) -> None:
        total = self.symbol_list_widget.count()
        excluded = len(self.excluded_symbols)
        visible = sum(1 for i in range(self.symbol_list_widget.count()) 
                     if not self.symbol_list_widget.item(i).isHidden())
        
        percent = (excluded / total * 100) if total > 0 else 0
        self.stats_label.setText(
            f"📊 کل نمادها: {total} | 🚫 بلاک‌شده: {excluded} ({percent:.1f}%) | 👁️ در حال نمایش: {visible}"
        )

    def _filter_list_items(self, text: str) -> None:
        self._current_search_text = text.strip().lower()
        
        for i in range(self.symbol_list_widget.count()):
            item = self.symbol_list_widget.item(i)
            search_match = self._current_search_text in item.text().lower()
            
            category_match = True
            if self.category_combo and self.category_combo.currentIndex() > 0:
                selected_cat = self.category_combo.currentText()
                cat_symbols = self.symbol_categories.get(selected_cat, [])
                category_match = item.text() in cat_symbols

            item.setHidden(not (search_match and category_match))
        
        self._update_stats()

    def _filter_by_category(self, category: str) -> None:
        self._filter_list_items(self._current_search_text)

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        symbol = item.text()
        is_checked = (item.checkState() == Qt.CheckState.Checked)
        
        if is_checked:
            self.excluded_symbols.add(symbol)
        else:
            self.excluded_symbols.discard(symbol)
        
        bg, fg = self._get_item_colors(is_checked)
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(fg))
        
        self._update_stats()

    def _set_all_checks(self, checked: bool) -> None:
        self.symbol_list_widget.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        bg, fg = self._get_item_colors(checked)
        
        for i in range(self.symbol_list_widget.count()):
            item = self.symbol_list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(state)
                symbol = item.text()
                if checked:
                    self.excluded_symbols.add(symbol)
                else:
                    self.excluded_symbols.discard(symbol)
                item.setBackground(QBrush(bg))
                item.setForeground(QBrush(fg))
                    
        self.symbol_list_widget.blockSignals(False)
        self._update_stats()

    def _remove_selected_symbol(self) -> None:
        current_item = self.symbol_list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "اطلاع", "لطفاً یک نماد را از لیست انتخاب کنید.")
            return
        
        symbol = current_item.text()
        reply = QMessageBox.question(
            self,
            "تأیید حذف",
            f"آیا از حذف نماد '{symbol}' مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.excluded_symbols.discard(symbol)
            if symbol in self.available_symbols:
                self.available_symbols.remove(symbol)
            self._populate_list()

    def _add_custom_symbol(self) -> None:
        symbol = self.custom_symbol_input.text().strip()
        if not symbol or len(symbol) < 2:
            QMessageBox.warning(self, "هشدار", "نام نماد باید حداقل ۲ کاراکتر باشد.")
            self.custom_symbol_input.setFocus()
            return

        pattern = r'^[a-zA-Z0-9_\-\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+$'
        if not re.match(pattern, symbol):
            QMessageBox.warning(self, "هشدار", "نام نماد نامعتبر است.")
            self.custom_symbol_input.setFocus()
            return

        if symbol in self.excluded_symbols:
            QMessageBox.information(self, "اطلاع", f"نماد '{symbol}' از قبل در لیست استثناها وجود دارد.")
            self.custom_symbol_input.clear()
            return

        self.excluded_symbols.add(symbol)
        if symbol not in self.available_symbols:
            self.available_symbols.append(symbol)
        
        self.custom_symbol_input.clear()
        self._populate_list()
        
        items = self.symbol_list_widget.findItems(symbol, Qt.MatchFlag.MatchExactly)
        if items:
            self.symbol_list_widget.scrollToItem(items[0])
            self.symbol_list_widget.setCurrentItem(items[0])

    def _import_list(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "بارگذاری لیست نمادها", "", "Text Files (*.txt);;JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not file_path:
            return
        
        try:
            symbols = []
            path = Path(file_path)
            if path.suffix.lower() == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    symbols = data if isinstance(data, list) else data.get('symbols', [])
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    symbols = [line.strip().split(',')[0] for line in f if line.strip() and not line.startswith('#')]
            
            valid = [s for s in symbols if s and len(s) >= 2]
            if not valid:
                QMessageBox.warning(self, "هشدار", "هیچ نماد معتبری یافت نشد.")
                return
            
            self.excluded_symbols.update(valid)
            for s in valid:
                if s not in self.available_symbols:
                    self.available_symbols.append(s)
            
            self._populate_list()
            QMessageBox.information(self, "موفق", f"✅ {len(valid)} نماد با موفقیت اضافه شد.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در بارگذاری فایل:\n{e}")

    def _export_list(self) -> None:
        if not self.excluded_symbols:
            QMessageBox.information(self, "اطلاع", "لیست استثناها خالی است.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره لیست نمادها", "excluded_symbols.json", "JSON Files (*.json);;Text Files (*.txt)"
        )
        if not file_path:
            return
        
        try:
            symbols = sorted(list(self.excluded_symbols))
            path = Path(file_path)
            if path.suffix.lower() == '.json':
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump({'symbols': symbols, 'total': len(symbols)}, f, indent=4, ensure_ascii=False)
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(symbols))
            QMessageBox.information(self, "موفق", f"✅ {len(symbols)} نماد ذخیره شد.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره فایل:\n{e}")

    def _clear_all_exclusions(self) -> None:
        if not self.excluded_symbols:
            return
        reply = QMessageBox.question(
            self, "تأیید", f"آیا از پاک کردن تمام {len(self.excluded_symbols)} استثنا اطمینان دارید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.excluded_symbols.clear()
            self._populate_list()

    def _reset_to_initial(self) -> None:
        self.excluded_symbols = set(self._initial_excluded)
        self._populate_list()

    def _save_and_accept(self) -> None:
        final_list = sorted(list(self.excluded_symbols))
        settings_manager.set_excluded_symbols(final_list)
        self.symbols_updated.emit(final_list)
        if self.symbol_categories:
            self.categories_updated.emit(self.symbol_categories)
        self.accept()

    def get_excluded_symbols(self) -> List[str]:
        return sorted(list(self.excluded_symbols))