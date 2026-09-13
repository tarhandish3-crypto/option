# ui/table_filter_manager.py
# -*- coding: utf-8 -*-

"""
مدیریت جامع و بلادرنگ فیلترهای ستونی جدول با بهینه‌سازی رندر.
"""

from __future__ import annotations

import copy
import logging
from typing import Dict, Any, Optional, Callable, List

from PySide6.QtWidgets import QTableWidget
from PySide6.QtCore import Qt

logger = logging.getLogger("OptionScanner.UI.TableFilterManager")


# =========================================================================
# ColumnFilter
# =========================================================================

class ColumnFilter:
    """
    نمایش‌دهنده‌ی یک فیلتر فعال روی یک ستون جدول.

    Attributes:
        column_index: شماره ستون
        column_name: نام نمایشی ستون
        filter_func: تابع فیلتر (Callable) یا None
        metadata: دیکشنری اطلاعات فیلتر برای ذخیره/بازیابی
        is_active: آیا فیلتر فعال است؟
        filter_metadata: نام قدیمی metadata (برای سازگاری)
    """

    def __init__(
        self,
        column_index: int,
        column_name: str,
        filter_func: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.column_index = column_index
        self.column_name = column_name
        self.filter_func = filter_func
        self.metadata: Dict[str, Any] = metadata or {}
        self.filter_metadata: Dict[str, Any] = self.metadata  # سازگاری
        self.is_active: bool = filter_func is not None

    def __repr__(self) -> str:
        return (
            f"ColumnFilter(col={self.column_index}, "
            f"name='{self.column_name}', active={self.is_active})"
        )


# =========================================================================
# TableFilterManager
# =========================================================================

class TableFilterManager:
    """مدیریت جامع و بلادرنگ فیلترهای ستونی جدول با بهینه‌سازی رندر"""

    _FILTER_PREFIX = "🔍 "

    def __init__(self, table_widget: QTableWidget) -> None:
        self.table_widget = table_widget
        self.filters: Dict[int, ColumnFilter] = {}
        self._original_headers: Dict[int, str] = {}
        self._filtered_rows: List[int] = []
        self._saved_filters: Dict[int, ColumnFilter] = {}

    # =====================================================================
    # Filter CRUD
    # =====================================================================

    def set_filter(
        self,
        column_index: int,
        column_name: str,
        filter_func: Optional[Callable],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        تنظیم یا حذف فیلتر یک ستون.

        Args:
            column_index: شماره ستون
            column_name: نام نمایشی ستون
            filter_func: تابع فیلتر یا None (برای حذف)
            metadata: اطلاعات فیلتر برای بازیابی
        """
        if filter_func is None:
            # حذف فیلتر
            if column_index in self.filters:
                del self.filters[column_index]
        else:
            # ذخیره‌ی نام اصلی قبل از اعمال فیلتر (فقط در اولین بار)
            if column_index not in self._original_headers:
                header_item = self.table_widget.horizontalHeaderItem(
                    column_index)
                if header_item is not None:
                    raw = header_item.text()
                    if raw.startswith(self._FILTER_PREFIX):
                        raw = raw[len(self._FILTER_PREFIX):]
                    self._original_headers[column_index] = raw

            self.filters[column_index] = ColumnFilter(
                column_index, column_name, filter_func, metadata
            )

        self._update_header_appearance(
            column_index, has_filter=(column_index in self.filters)
        )
        self.apply_filters()

    def get_filter(self, column_index: int) -> Optional[ColumnFilter]:
        """دریافت فیلتر فعلی یک ستون"""
        return self.filters.get(column_index)

    def get_all_filters(self) -> Dict[int, ColumnFilter]:
        """دریافت کپی از تمام فیلترهای فعال"""
        return dict(self.filters)

    def has_active_filters(self) -> bool:
        """آیا حداقل یک فیلتر فعال وجود دارد؟"""
        return any(
            cf.is_active and cf.filter_func is not None
            for cf in self.filters.values()
        )

    def get_active_filter_count(self) -> int:
        """تعداد فیلترهای فعال"""
        return sum(
            1 for cf in self.filters.values()
            if cf.is_active and cf.filter_func is not None
        )

    def clear_all_filters(self, reset_headers: bool = False) -> None:
        """
        پاک‌سازی تمام فیلترها.

        Args:
            reset_headers: اگر True باشد، کش نام اصلی ستون‌ها هم پاک می‌شود.
        """
        for col_idx in list(self.filters.keys()):
            self._update_header_appearance(col_idx, has_filter=False)
        self.filters.clear()
        if reset_headers:
            self._original_headers.clear()
        self.apply_filters()

    # =====================================================================
    # Preserve / Restore
    # =====================================================================

    def preserve_filters(self) -> None:
        """ذخیره فیلترهای فعلی برای بازیابی پس از رفرش جدول"""
        self._saved_filters = {
            k: copy.copy(v) for k, v in self.filters.items()
        }
        logger.debug(f"Filters preserved: {len(self._saved_filters)}")

    def restore_filters(self) -> None:
        """بازیابی فیلترهای ذخیره‌شده"""
        if not self._saved_filters:
            return

        # پاک‌سازی فیلترهای فعلی بدون تغییر هدر
        for col_idx in list(self.filters.keys()):
            self._update_header_appearance(col_idx, has_filter=False)
        self.filters.clear()

        # بازگردانی فیلترهای ذخیره‌شده
        self.filters = {
            k: copy.copy(v) for k, v in self._saved_filters.items()
        }

        # بروزرسانی ظاهر هدرها
        for col_idx in self.filters.keys():
            self._update_header_appearance(col_idx, has_filter=True)

        self.apply_filters()
        logger.debug(f"Filters restored: {len(self.filters)}")

    def reset_for_new_table(self) -> None:
        """پاک‌سازی کامل برای جدول جدید (مثلاً بعد از تغییر ستون‌ها)"""
        self.filters.clear()
        self._original_headers.clear()
        self._filtered_rows.clear()
        self._saved_filters.clear()

    # =====================================================================
    # Row Visibility
    # =====================================================================

    def get_visible_row_count(self) -> int:
        """
        شمارش واقعی ردیف‌های مرئی جدول.

        نکته: برخلاف نسخه‌ی قبلی، این متد همیشه مقدار accurate برمی‌گرداند،
        حتی اگر ردیف‌ها به صورت دستی مخفی شده باشند.
        """
        count = 0
        for r in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(r):
                count += 1
        return count

    # =====================================================================
    # Internal Helpers
    # =====================================================================

    def _update_header_appearance(
        self, column_index: int, has_filter: bool
    ) -> None:
        """بروزرسانی ظاهر هدر ستون با پیشوند 🔍"""
        header_item = self.table_widget.horizontalHeaderItem(column_index)
        if header_item is None:
            return

        # ذخیره‌ی نام اصلی فقط در اولین فراخوانی
        if column_index not in self._original_headers:
            raw_text = header_item.text()
            if raw_text.startswith(self._FILTER_PREFIX):
                raw_text = raw_text[len(self._FILTER_PREFIX):]
            self._original_headers[column_index] = raw_text

        base_name = self._original_headers[column_index]
        new_text = (
            f"{self._FILTER_PREFIX}{base_name}"
            if has_filter
            else base_name
        )

        if header_item.text() != new_text:
            header_item.setText(new_text)

    def _is_empty_state(self) -> bool:
        """بررسی اینکه جدول در حالت Empty State است (ردیف راهنما)"""
        if self.table_widget.rowCount() != 1:
            return False

        for col in range(self.table_widget.columnCount()):
            item = self.table_widget.item(0, col)
            if item is not None:
                text = item.text()
                if text and "برای شروع" in text:
                    return True
        return False

    # =====================================================================
    # Apply Filters
    # =====================================================================

    def apply_filters(self) -> None:
        """
        اعمال تمام فیلترهای فعال روی ردیف‌های جدول.

        این متد همیشه از rowCount() فعلی جدول استفاده می‌کند، پس
        بعد از بازسازی جدول در Refresh/Scan نیز قابل فراخوانی است.
        """
        row_count = self.table_widget.rowCount()
        if row_count <= 0:
            self._filtered_rows = []
            return

        # حالت Empty State (ردیف راهنما)
        if self._is_empty_state():
            self._filtered_rows = [0]
            return

        # حالت بدون فیلتر
        if not self.has_active_filters():
            self.table_widget.setUpdatesEnabled(False)
            try:
                for r in range(row_count):
                    self.table_widget.setRowHidden(r, False)
            finally:
                self.table_widget.setUpdatesEnabled(True)
            self._filtered_rows = list(range(row_count))
            return

        # حالت با فیلتر: بررسی هر ردیف
        visible_rows: List[int] = []
        self.table_widget.setUpdatesEnabled(False)
        try:
            for row in range(row_count):
                passes_all = True
                for col_idx, col_filter in self.filters.items():
                    if not col_filter.is_active or col_filter.filter_func is None:
                        continue

                    if col_idx < 0 or col_idx >= self.table_widget.columnCount():
                        continue

                    item = self.table_widget.item(row, col_idx)
                    if item is None:
                        passes_all = False
                        break

                    val = item.data(Qt.ItemDataRole.UserRole)
                    if val is None:
                        val = item.text()

                    try:
                        if not col_filter.filter_func(val):
                            passes_all = False
                            break
                    except Exception as e:
                        logger.debug(
                            f"Filter error at row {row}, col {col_idx}: {e}"
                        )
                        passes_all = False
                        break

                self.table_widget.setRowHidden(row, not passes_all)
                if passes_all:
                    visible_rows.append(row)
        finally:
            self.table_widget.setUpdatesEnabled(True)

        self._filtered_rows = visible_rows
