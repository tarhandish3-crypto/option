# -*- coding: utf-8 -*-
"""
مدیریت فیلترهای جدول و اعمال آنها روی ردیف‌های جدول
"""

import logging
from typing import Dict, Optional, Callable, List, Any
from dataclasses import dataclass, field
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
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        تنظیم فیلتر برای یک سرستون
        
        Arguments:
            column_index: شاخص سرستون
            column_name: نام سرستون
            filter_func: تابع فیلتر (None به معنی حذف فیلتر)
            filter_metadata: اطلاعات فیلتر برای ذخیره و بازیابی
        """
        
        if filter_func is None:
            # حذف فیلتر
            if column_index in self.filters:
                del self.filters[column_index]
                logger.info(f"فیلتر سرستون {column_name} حذف شد")
                self._update_header_appearance(column_index, False)
        else:
            # اضافه کردن یا بروزرسانی فیلتر
            self.filters[column_index] = ColumnFilter(
                column_index=column_index,
                column_name=column_name,
                filter_func=filter_func,
                is_active=True,
                filter_metadata=filter_metadata
            )
            logger.info(f"فیلتر سرستون {column_name} تنظیم شد")
            self._update_header_appearance(column_index, True)
        
        # اعمال فیلترها
        self.apply_filters()
    
    def apply_filters(self) -> None:
        """اعمال تمام فیلترهای فعال بر روی جدول"""
        
        if not self.filters:
            # نمایش تمام ردیف‌ها
            logger.info("No active filters, showing all rows")
            self._show_all_rows()
            return
        
        # کپی لیست ردیف‌های اصلی
        filtered_rows = list(range(self.table_widget.rowCount()))
        logger.info(f"Starting with {len(filtered_rows)} rows")
        
        # اعمال هر فیلتر
        for column_index, column_filter in self.filters.items():
            if not column_filter.is_active or column_filter.filter_func is None:
                logger.warning(f"Filter for column {column_index} is not active or has no function")
                continue
            
            before_count = len(filtered_rows)
            filtered_rows = [
                row for row in filtered_rows
                if self._passes_filter(row, column_index, column_filter.filter_func)
            ]
            after_count = len(filtered_rows)
            logger.info(f"Applied filter to column {column_index}: {before_count} -> {after_count} rows")
        
        # نمایش/مخفی کردن ردیف‌ها
        self._update_row_visibility(filtered_rows)
        logger.info(f"Final filtered rows: {len(filtered_rows)}/{self.table_widget.rowCount()}")
    
    def _passes_filter(
        self,
        row: int,
        column_index: int,
        filter_func: Callable
    ) -> bool:
        """بررسی اینکه یک ردیف از فیلتر می‌گذرد یا نه"""
        
        try:
            item = self.table_widget.item(row, column_index)
            if item is None:
                return False
            
            # ابتدا مقدار عددی (UserRole) را امتحان کن، سپس متن را
            from PySide6.QtCore import Qt
            user_value = item.data(Qt.ItemDataRole.UserRole)
            
            # اگر UserRole یک عدد است، آن را استفاده کن
            if user_value is not None and isinstance(user_value, (int, float)):
                value = user_value
            else:
                # در غیر اینصورت، متن را استفاده کن
                value = item.text()
            
            result = filter_func(value)
            return result
        
        except Exception as e:
            logger.warning(f"خطا در فیلتر کردن ردیف {row}: {e}")
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
        return len(self._saved_filters) > 0
    
    def get_active_filter_count(self) -> int:
        """دریافت تعداد فیلترهای فعال"""
        return len(self.filters)
    
    def get_filter(self, column_index: int) -> Optional[ColumnFilter]:
        """دریافت فیلتر فعلی برای یک سرستون"""
        return self.filters.get(column_index)
    
    def get_visible_row_count(self) -> int:
        """دریافت تعداد ردیف‌های قابل نمایش"""
        return sum(
            1 for row in range(self.table_widget.rowCount())
            if not self.table_widget.isRowHidden(row)
        )
