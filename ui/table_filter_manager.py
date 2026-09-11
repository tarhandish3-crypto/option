# -*- coding: utf-8 -*-
"""
مدیریت فیلترهای جدول و اعمال آنها روی ردیف‌های جدول
"""

import logging
from typing import Dict, Optional, Callable, List, Any
from dataclasses import dataclass
from copy import deepcopy

from PySide6.QtWidgets import QTableWidget
from PySide6.QtCore import Qt

logger = logging.getLogger("OptionScanner.UI.TableFilterManager")


@dataclass
class ColumnFilter:
    """نگهداری اطلاعات فیلتر برای یک سرستون"""
    column_index: int
    column_name: str
    filter_func: Optional[Callable] = None
    is_active: bool = False
    filter_metadata: Optional[Dict[str, Any]] = None  # ذخیره تنظیمات فیلتر برای نمایش دوباره


class TableFilterManager:
    """
    مدیریت فیلترهای متقدم جدول
    
    ویژگی‌ها:
    - ذخیره فیلترهای فعال برای هر سرستون
    - اعمال فیلترها بر روی ردیف‌های جدول
    - ترکیب چندین فیلتر با منطق AND
    """
    
    def __init__(self, table_widget: QTableWidget):
        self.table_widget = table_widget
        self.filters: Dict[int, ColumnFilter] = {}
        self._original_rows: List[int] = []  # لیست ردیف‌های اصلی
        self._filtered_rows: List[int] = []  # لیست ردیف‌های فیلتر‌شده
        self._saved_filters: Dict[int, ColumnFilter] = {}  # ذخیره فیلترها برای restore
    
    def set_filter(
            self,
            column_index: int,
            column_name: str,
            filter_func: Optional[Callable],
            filter_metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        تنظیم فیلتر برای یک سرستون
        
        Arguments:
            column_index: شاخص سرستون
            column_name: نام سرستون
            filter_func: تابع فیلتر (None به معنی حذف فیلتر)
            filter_metadata: اطلاعات فیلتر برای ذخیره و بازیابی
        """
        
        logger.info(f"set_filter called: column={column_index} ({column_name}), has_func={filter_func is not None}, has_metadata={filter_metadata is not None}")
        
        if filter_func is None:
            # حذف فیلتر
            if column_index in self.filters:
                del self.filters[column_index]
                self._update_header_appearance(column_index, False)
        else:
            # اضافه کردن یا بروزرسانی فیلتر
            self.filters[column_index] = ColumnFilter(
                column_index=column_index,
                column_name=column_name,
                filter_func=filter_func,
                is_active=True,
                filter_metadata=filter_metadata)

            self._update_header_appearance(column_index, True)
        
        # اعمال فیلترها
        self.apply_filters()
    
    def apply_filters(self) -> None:
        """
        اعمال تمام فیلترهای فعال روی ردیف‌های فعلی جدول.

        نکته مهم:
        این متد همیشه rowCount() فعلی جدول را می‌خواند.
        بنابراین بعد از بازسازی جدول در Refresh/Scan نیز
        می‌تواند همان Filter State را روی داده‌های جدید اعمال کند.
        """

        row_count = self.table_widget.rowCount()

        if row_count <= 0:
            self._original_rows = []
            self._filtered_rows = []
            return

        if not self.has_active_filters():
            self._original_rows = list(range(row_count))
            self._filtered_rows = list(range(row_count))

            self._show_all_rows()
            return

        # همیشه از Rowهای فعلی جدول شروع می‌کنیم.
        filtered_rows = list(range(row_count))

        self._original_rows = list(filtered_rows)

        # تمام فیلترهای فعال با AND ترکیب می‌شوند.
        for column_index, column_filter in self.filters.items():

            if (not column_filter.is_active or column_filter.filter_func is None):

                continue

            # اگر ستون دیگر وجود نداشته باشد، آن فیلتر را
            # روی جدول فعلی اعمال نمی‌کنیم.
            if (column_index < 0 or column_index >= self.table_widget.columnCount()):

                continue

            filtered_rows = [row for row in filtered_rows
                             if self._passes_filter(row, column_index, column_filter.filter_func,)]

        self._filtered_rows = list(filtered_rows)

        # نمایش/مخفی کردن Rowها
        self._update_row_visibility(filtered_rows)

        logger.info("Final filtered rows: %s/%s",
                    len(filtered_rows), row_count,)

    
    def _passes_filter(
            self,
            row: int,
            column_index: int,
            filter_func: Callable) -> bool:
        """بررسی اینکه یک ردیف از فیلتر می‌گذرد یا نه"""
        
        try:
            item = self.table_widget.item(row, column_index)
            if item is None:
                return False
            
            # ابتدا مقدار عددی (UserRole) را امتحان کن، سپس متن را
            user_value = item.data(Qt.ItemDataRole.UserRole)
            
            # اگر UserRole یک عدد است، آن را استفاده کن
            if user_value is not None and isinstance(user_value, (int, float)):
                value = user_value
            else:
                # در غیر اینصورت، متن را استفاده کن
                value = item.text()
            
            return bool(filter_func(value))
        
        except Exception as e:
            logger.warning("Error filtering row %s, column %s: %s",
                           row, column_index, e,)
            return False
    
    def _show_all_rows(self) -> None:
        """نمایش تمام ردیف‌های جدول"""
        for row in range(self.table_widget.rowCount()):
            self.table_widget.setRowHidden(row, False)
    
    def _update_row_visibility(self, visible_rows: List[int]) -> None:
        """به‌روزرسانی نمایش/مخفی کردن ردیف‌ها"""
        
        visible_set = set(visible_rows)
        
        for row in range(self.table_widget.rowCount()):
            is_visible = row in visible_set
            self.table_widget.setRowHidden(row, not is_visible)
    
    def clear_all_filters(self) -> None:
        """حذف تمام فیلترها"""
        for column_index in list(self.filters.keys()):
            self._update_header_appearance(column_index, False)
        self.filters.clear()
        self._show_all_rows()
        logger.info("تمام فیلترها حذف شد")
    
    def _update_header_appearance(self, column_index: int, has_filter: bool) -> None:
        """بروزرسانی ظاهر هدر سرستون برای نشان‌دادن فیلتر"""
        
        header_item = self.table_widget.horizontalHeaderItem(column_index)
        if header_item is None:
            return
        
        current_text = header_item.text()
        
        # حذف نماد فیلتر قبلی اگر وجود داشت
        if "🔍" in current_text:
            current_text = current_text.replace("🔍 ", "").strip()
        
        if has_filter:
            # اضافه کردن نماد فیلتر
            new_text = f"🔍 {current_text}"
        else:
            new_text = current_text
        
        header_item.setText(new_text)
        logger.info(f"هدر سرستون {column_index} به‌روزرسانی شد: {new_text}")
    
    def preserve_filters(self) -> None:
        """ذخیره فیلترهای فعلی برای استفاده مجدد پس از رفرش"""
        self._saved_filters = deepcopy(self.filters)
        logger.info(f"فیلترها ذخیره شدند ({len(self._saved_filters)} فیلتر فعال)")
    
    def restore_filters(self) -> None:
        """بازیابی فیلترهای ذخیره‌شده"""
        if not self._saved_filters:
            return
        
        self.filters = deepcopy(self._saved_filters)
        
        # بروزرسانی ظاهر هدرها
        for column_index in self.filters.keys():
            self._update_header_appearance(column_index, True)
        
        # اعمال فیلترها
        self.apply_filters()
        logger.info(f"فیلترها بازیابی شدند ({len(self.filters)} فیلتر)")
    
    def has_active_filters(self) -> bool:
        """بررسی وجود فیلترهای فعال"""
        return any(column_filter.is_active
                   and column_filter.filter_func is not None
                   for column_filter in self.filters.values())
    
    def get_active_filter_count(self) -> int:
        """دریافت تعداد فیلترهای فعال"""
        return sum(1 for column_filter in self.filters.values()
                   if (column_filter.is_active and column_filter.filter_func is not None))
    
    def get_filter(self, column_index: int) -> Optional[ColumnFilter]:
        """دریافت فیلتر فعلی برای یک سرستون"""
        return self.filters.get(column_index)
    
    def get_visible_row_count(self) -> int:
        """دریافت تعداد ردیف‌های قابل نمایش"""
        return sum(
            1 for row in range(self.table_widget.rowCount())
            if not self.table_widget.isRowHidden(row))