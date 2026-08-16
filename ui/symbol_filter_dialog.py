# ui/symbol_filter_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ مدیریت فیلتر نمادها (Symbol Filter Dialog) - نسخه اصلاح‌شده V2.1
امکان انتخاب، جستجو، استثنا کردن، Import/Export و مدیریت دستی نمادهای بازار اختیار معامله.
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
from PySide6.QtGui import QFont

from ui.settings_manager import settings_manager
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.SymbolFilter")


class SymbolFilterDialog(QDialog):
    """
    دیالوگ مدیریت نمادهای استثنا شده (Excluded Symbols)
    
    Signals:
        symbols_updated: ارسال لیست جدید نمادهای فیلترشده
        categories_updated: ارسال دسته‌بندی‌های به‌روزرسانی‌شده
    """

    symbols_updated = Signal(list)      # لیست نمادهای استثنا شده
    categories_updated = Signal(dict)   # دسته‌بندی‌های به‌روزرسانی‌شده

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
        self.setLayoutDirection(Qt.RightToLeft)

        # نمادهای موجود
        self.available_symbols: List[str] = available_symbols or []
        
        # نمادهای بلاک‌شده: اول از settings_manager، اگر خالی بود از پارامتر
        persisted = settings_manager.get_excluded_symbols()
        initial = persisted if persisted else (currently_excluded or [])
        
        self.excluded_symbols: Set[str] = set(initial)
        self._initial_excluded: Set[str] = set(initial)
        self.symbol_categories: Dict[str, List[str]] = symbol_categories or {}
        self._current_search_text = ""

        self._init_ui()
        self._apply_dialog_theme()
        self._populate_list()
        self._update_stats()
        
        logger.info(
            f"SymbolFilterDialog opened: {len(self.available_symbols)} available symbol(s), "
            f"{len(self.excluded_symbols)} blocked symbol(s)"
        )

    def _apply_dialog_theme(self) -> None:
        mode = ui_theme.current_mode()
        if hasattr(self, "info_label"):
            self.info_label.setStyleSheet(ui_theme.get_symbol_filter_info_style(mode))
        if hasattr(self, "stats_label"):
            self.stats_label.setStyleSheet(ui_theme.get_symbol_filter_stats_style(mode))

    def _init_ui(self) -> None:
        """راه‌اندازی رابط کاربری"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # =============================================
        # ۱. بخش جستجو و فیلتر
        # =============================================
        header_group = QGroupBox("جستجو و فیلتر")
        header_layout = QVBoxLayout(header_group)

        info_label = QLabel(
            "نمادهایی که چک‌باکس آن‌ها فعال (تیک‌خورده) است، از محاسبات اسکنر حذف (Block) خواهند شد:"
        )
        self.info_label = info_label
        info_label.setWordWrap(True)
        info_label.setStyleSheet(ui_theme.get_symbol_filter_info_style(ui_theme.current_mode()))
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

        # =============================================
        # ۲. لیست نمادها با آمار
        # =============================================
        list_group = QGroupBox("لیست نمادهای بازار")
        list_layout = QVBoxLayout(list_group)

        self.stats_label = QLabel("📊 آماده‌سازی...")
        self.stats_label.setStyleSheet(ui_theme.get_symbol_filter_stats_style(ui_theme.current_mode()))
        list_layout.addWidget(self.stats_label)

        self.symbol_list_widget = QListWidget()
        self.symbol_list_widget.setAlternatingRowColors(True)
        self.symbol_list_widget.setFont(QFont("Vazir", 10))
        self.symbol_list_widget.itemChanged.connect(self._on_item_checked)
        list_layout.addWidget(self.symbol_list_widget)

        # =============================================
        # ۳. نوار ابزار عملیات گروهی و Import/Export
        # =============================================
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

        # =============================================
        # ۴. افزودن نماد دستی با اعتبارسنجی
        # =============================================
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

        # =============================================
        # ۵. دکمه‌های تایید / انصراف
        # =============================================
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

    def _populate_list(self) -> None:
        """پر کردن لیست نمادها"""
        self.symbol_list_widget.blockSignals(True)
        self.symbol_list_widget.clear()

        all_unique = sorted(list(set(self.available_symbols) | self.excluded_symbols))

        for symbol in all_unique:
            item = QListWidgetItem(symbol)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            
            if symbol in self.excluded_symbols:
                item.setCheckState(Qt.Checked)
                item.setBackground(Qt.lightGray)
            else:
                item.setCheckState(Qt.Unchecked)
                item.setBackground(Qt.white)

            self.symbol_list_widget.addItem(item)

        self.symbol_list_widget.blockSignals(False)
        self._update_stats()

    def _update_stats(self) -> None:
        """به‌روزرسانی آمار نمایشی"""
        total = self.symbol_list_widget.count()
        excluded = len(self.excluded_symbols)
        visible = sum(1 for i in range(self.symbol_list_widget.count()) 
                     if not self.symbol_list_widget.item(i).isHidden())
        
        percent = (excluded / total * 100) if total > 0 else 0
        
        self.stats_label.setText(
            f"📊 کل نمادها: {total} | 🚫 بلاک‌شده: {excluded} ({percent:.1f}%) | 👁️ در حال نمایش: {visible}"
        )

    def _filter_list_items(self, text: str) -> None:
        """فیلتر کردن آیتم‌های لیست بر اساس متن جستجو"""
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
        """فیلتر بر اساس دسته‌بندی"""
        self._filter_list_items(self._current_search_text)

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        """بروزرسانی مجموعه نمادهای بلاک‌شده"""
        symbol = item.text()
        if item.checkState() == Qt.Checked:
            self.excluded_symbols.add(symbol)
            item.setBackground(Qt.lightGray)
        else:
            self.excluded_symbols.discard(symbol)
            item.setBackground(Qt.white)
        
        self._update_stats()

    def _set_all_checks(self, checked: bool) -> None:
        """تغییر وضعیت همزمان تمام آیتم‌های مرئی"""
        self.symbol_list_widget.blockSignals(True)
        state = Qt.Checked if checked else Qt.Unchecked
        
        for i in range(self.symbol_list_widget.count()):
            item = self.symbol_list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(state)
                symbol = item.text()
                if checked:
                    self.excluded_symbols.add(symbol)
                    item.setBackground(Qt.lightGray)
                else:
                    self.excluded_symbols.discard(symbol)
                    item.setBackground(Qt.white)
                    
        self.symbol_list_widget.blockSignals(False)
        self._update_stats()

    def _remove_selected_symbol(self) -> None:
        """حذف نماد انتخاب‌شده از لیست دیالوگ"""
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
            logger.info(f"Removed symbol: {symbol}")

    def _add_custom_symbol(self) -> None:
        """افزودن نماد دستی به لیست بلاک‌شده‌ها با پشتیبانی کامل از زبان فارسی"""
        symbol = self.custom_symbol_input.text().strip()
        
        if not symbol:
            QMessageBox.warning(self, "هشدار", "لطفاً نام نماد را وارد کنید.")
            self.custom_symbol_input.setFocus()
            return
        
        if len(symbol) < 2:
            QMessageBox.warning(self, "هشدار", "نام نماد باید حداقل ۲ کاراکتر باشد.")
            self.custom_symbol_input.setFocus()
            return

        # اعتبارسنجی الگوی نمادهای بورس ایران (حروف فارسی، انگلیسی، اعداد، خط تیره و زیرخط)
        pattern = r'^[a-zA-Z0-9_\-\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+$'
        if not re.match(pattern, symbol):
            QMessageBox.warning(
                self, 
                "هشدار", 
                "نام نماد مجاز نیست. لطفاً فقط از حروف، اعداد و خط تیره استفاده کنید."
            )
            self.custom_symbol_input.setFocus()
            return

        if symbol in self.excluded_symbols:
            QMessageBox.information(self, "اطلاع", f"نماد '{symbol}' قبلاً در لیست استثناها وجود دارد.")
            self.custom_symbol_input.clear()
            return

        self.excluded_symbols.add(symbol)
        if symbol not in self.available_symbols:
            self.available_symbols.append(symbol)
        
        self.custom_symbol_input.clear()
        self._populate_list()
        
        # اسکرول روی نماد جدید
        items = self.symbol_list_widget.findItems(symbol, Qt.MatchExactly)
        if items:
            self.symbol_list_widget.scrollToItem(items[0])
            self.symbol_list_widget.setCurrentItem(items[0])

        logger.info(f"Added custom symbol: {symbol}")

    def _import_list(self) -> None:
        """بارگذاری لیست نمادها از فایل"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "بارگذاری لیست نمادها", 
            "", 
            "Text Files (*.txt);;JSON Files (*.json);;CSV Files (*.csv);;All Files (*.*)"
        )
        if not file_path:
            return
        
        try:
            symbols = []
            path = Path(file_path)
            
            if path.suffix.lower() == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        symbols = data
                    elif isinstance(data, dict):
                        symbols = data.get('symbols', data.get('excluded', []))
            elif path.suffix.lower() == '.csv':
                import csv
                with open(path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row:
                            symbols.append(row[0].strip())
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    symbols = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            valid_symbols = [s for s in symbols if s and len(s) >= 2]
            
            if not valid_symbols:
                QMessageBox.warning(self, "هشدار", "هیچ نماد معتبری در فایل یافت نشد.")
                return
            
            self.excluded_symbols.update(valid_symbols)
            for s in valid_symbols:
                if s not in self.available_symbols:
                    self.available_symbols.append(s)
            
            self._populate_list()
            QMessageBox.information(self, "موفق", f"✅ {len(valid_symbols)} نماد با موفقیت بارگذاری شد.")
            
        except Exception as e:
            logger.error(f"Failed to import symbols: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در بارگذاری فایل:\n{str(e)}")

    def _export_list(self) -> None:
        """ذخیره لیست نمادهای استثنا شده در فایل"""
        if not self.excluded_symbols:
            QMessageBox.information(self, "اطلاع", "لیست استثناها خالی است.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "ذخیره لیست نمادها", 
            "excluded_symbols.json", 
            "JSON Files (*.json);;Text Files (*.txt);;CSV Files (*.csv)"
        )
        if not file_path:
            return
        
        try:
            symbols = sorted(list(self.excluded_symbols))
            path = Path(file_path)
            
            if path.suffix.lower() == '.json':
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'symbols': symbols,
                        'total': len(symbols),
                        'export_date': datetime.now().isoformat()
                    }, f, indent=4, ensure_ascii=False)
            elif path.suffix.lower() == '.csv':
                import csv
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Symbol', 'Status'])
                    for symbol in symbols:
                        writer.writerow([symbol, 'excluded'])
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(f'# Excluded Symbols - {datetime.now()}\n')
                    f.write('\n'.join(symbols))
            
            QMessageBox.information(self, "موفق", f"✅ {len(symbols)} نماد در فایل با موفقیت ذخیره شد.")
            
        except Exception as e:
            logger.error(f"Failed to export symbols: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره فایل:\n{str(e)}")

    def _clear_all_exclusions(self) -> None:
        """پاک کردن همه استثناها"""
        if not self.excluded_symbols:
            return
        
        reply = QMessageBox.question(
            self,
            "تأیید پاک کردن",
            f"آیا از پاک کردن تمام {len(self.excluded_symbols)} استثنا اطمینان دارید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.excluded_symbols.clear()
            self._populate_list()

    def _reset_to_initial(self) -> None:
        """بازنشانی به حالت اولیه هنگام باز شدن دیالوگ"""
        self.excluded_symbols = set(self._initial_excluded)
        self._populate_list()
        if self.search_input:
            self.search_input.clear()
        if self.category_combo:
            self.category_combo.setCurrentIndex(0)
        logger.info("Reset to initial state")

    def _save_and_accept(self) -> None:
        """ذخیره در settings_manager و ارسال سیگنال"""
        final_list = sorted(list(self.excluded_symbols))
        
        # ذخیره دائمی در user_settings.json
        settings_manager.set_excluded_symbols(final_list)
        
        logger.info(f"Blocked symbols saved: {len(final_list)} symbol(s)")
        
        self.symbols_updated.emit(final_list)
        if self.symbol_categories:
            self.categories_updated.emit(self.symbol_categories)
        
        self.accept()

    def get_excluded_symbols(self) -> List[str]:
        """متد کمکی برای دریافت خروجی مستقیم"""
        return sorted(list(self.excluded_symbols))

    def set_initial_state(self, excluded_symbols: List[str]) -> None:
        """تنظیم صریح حالت اولیه"""
        self._initial_excluded = set(excluded_symbols)
        self.excluded_symbols = set(excluded_symbols)
        self._populate_list()

    def keyPressEvent(self, event) -> None:
        """مدیریت میانبرهای کیبورد"""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._save_and_accept()
        else:
            super().keyPressEvent(event)