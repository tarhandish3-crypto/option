# -*- coding: utf-8 -*-
"""
دیالوگ فیلتر متقدم برای سرستون‌های جدول (مثل Excel)
"""

import logging
import math
from typing import Optional, Any, Callable, List, Dict
from enum import Enum

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QDoubleSpinBox, QCheckBox,
    QGroupBox, QRadioButton, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt

logger = logging.getLogger("OptionScanner.UI.ColumnFilterDialog")


def _safe_float(value: Any) -> float:
    """تبدیل ایمن مقدار به float - تابع خارج از کلاس برای استفاده در lambda"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # حذف پیش‌فرض‌ها مثل درصد
            clean_str = str(value).strip().replace('%', '').replace(',', '').strip()
            if not clean_str:
                return float('nan')
            return float(clean_str)
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return float('nan')


class FilterType(Enum):
    """انواع فیلترها"""
    NUMERIC = "numeric"      # عددی
    TEXT = "text"            # متنی
    CHECKBOX = "checkbox"    # چک‌باکس
    COMBO = "combo"          # کمبو‌باکس


class ColumnFilterDialog(QDialog):
    """
    دیالوگ فیلتر متقدم برای سرستون‌های جدول
    
    ویژگی‌ها:
    - فیلترهای عددی: بزرگتر از، کوچکتر از، برابر با، بین
    - فیلترهای متنی: شامل، شروع با، پایان با، برابر با
    - فیلترهای خاص: خالی از محتوا، تهی نیست
    - قابل ترکیب با AND/OR
    """
    
    def __init__(
        self,
        column_name: str,
        filter_type: FilterType = FilterType.TEXT,
        parent=None,
        table_filter_manager=None,
        column_index: int = -1
    ):
        super().__init__(parent)
        self.setWindowTitle(f"فیلتر: {column_name}")
        self.setMinimumWidth(400)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.column_name = column_name
        self.column_index = column_index
        self.filter_type = filter_type
        self.filter_result = None
        self.filter_metadata = None  # ذخیره metadata برای restore
        self.table_filter_manager = table_filter_manager
        
        self._init_ui()
        self._restore_previous_filter()
    
    def _init_ui(self):
        """ایجاد رابط کاربری"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # ۱. انتخاب نوع فیلتر
        filter_group = QGroupBox("نوع فیلتر")
        filter_layout = QVBoxLayout(filter_group)
        
        self.filter_options = {}
        
        if self.filter_type == FilterType.NUMERIC:
            self._create_numeric_filters(filter_layout)
        elif self.filter_type == FilterType.TEXT:
            self._create_text_filters(filter_layout)
        
        layout.addWidget(filter_group)
        
        # ۲. دکمه‌های پایین
        button_layout = QHBoxLayout()
        
        btn_apply = QPushButton("✅ اعمال فیلتر")
        btn_apply.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 15px;")
        btn_apply.clicked.connect(self._apply_filter)
        button_layout.addWidget(btn_apply)
        
        btn_clear = QPushButton("🧹 حذف فیلتر")
        btn_clear.setStyleSheet("padding: 6px 15px;")
        btn_clear.clicked.connect(self._clear_filter)
        button_layout.addWidget(btn_clear)
        
        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.setStyleSheet("padding: 6px 15px;")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def _restore_previous_filter(self) -> None:
        """بازیابی فیلتر قبلی برای نشان‌دادن تنظیمات قبل"""
        if not self.table_filter_manager or self.column_index < 0:
            return
        
        previous_filter = self.table_filter_manager.get_filter(self.column_index)
        if not previous_filter or not previous_filter.filter_metadata:
            return
        
        metadata = previous_filter.filter_metadata
        logger.info(f"بازیابی فیلتر قبلی برای سرستون {self.column_index}")
        
        try:
            if self.filter_type == FilterType.NUMERIC and metadata.get("filter_type") == "numeric":
                if metadata.get("greater_checked"):
                    self.filter_options['greater'][0].setChecked(True)
                    self.filter_options['greater'][1].setValue(metadata.get("greater_value", 0))
                elif metadata.get("less_checked"):
                    self.filter_options['less'][0].setChecked(True)
                    self.filter_options['less'][1].setValue(metadata.get("less_value", 0))
                elif metadata.get("equal_checked"):
                    self.filter_options['equal'][0].setChecked(True)
                    self.filter_options['equal'][1].setValue(metadata.get("equal_value", 0))
                elif metadata.get("between_checked"):
                    self.filter_options['between'][0].setChecked(True)
                    self.filter_options['between'][1].setValue(metadata.get("between_from", 0))
                    self.filter_options['between'][2].setValue(metadata.get("between_to", 100))
                elif metadata.get("empty_checked"):
                    self.filter_options['empty'].setChecked(True)
            
            elif self.filter_type == FilterType.TEXT and metadata.get("filter_type") == "text":
                if metadata.get("contains_checked"):
                    self.filter_options['contains'][0].setChecked(True)
                    self.filter_options['contains'][1].setText(metadata.get("contains_text", ""))
                elif metadata.get("exact_checked"):
                    self.filter_options['exact'][0].setChecked(True)
                    self.filter_options['exact'][1].setText(metadata.get("exact_text", ""))
                elif metadata.get("starts_checked"):
                    self.filter_options['starts'][0].setChecked(True)
                    self.filter_options['starts'][1].setText(metadata.get("starts_text", ""))
                elif metadata.get("ends_checked"):
                    self.filter_options['ends'][0].setChecked(True)
                    self.filter_options['ends'][1].setText(metadata.get("ends_text", ""))
                elif metadata.get("empty_checked"):
                    self.filter_options['empty'].setChecked(True)
        
        except Exception as e:
            logger.warning(f"خطا در بازیابی فیلتر قبلی: {e}")
    
    def _create_numeric_filters(self, layout: QVBoxLayout):
        """ایجاد فیلترهای عددی"""
        
        # فیلتر بزرگتر از
        greater_layout = QHBoxLayout()
        rb_greater = QRadioButton("بزرگتر از")
        rb_greater.setChecked(True)
        self.spin_greater = QDoubleSpinBox()
        self.spin_greater.setRange(-999999, 999999)
        self.spin_greater.setSingleStep(0.1)
        self.spin_greater.setDecimals(2)
        rb_greater.toggled.connect(lambda checked: self.spin_greater.setEnabled(checked))
        greater_layout.addWidget(rb_greater)
        greater_layout.addWidget(self.spin_greater, stretch=1)
        self.filter_options['greater'] = (rb_greater, self.spin_greater)
        layout.addLayout(greater_layout)
        
        # فیلتر کوچکتر از
        less_layout = QHBoxLayout()
        rb_less = QRadioButton("کوچکتر از")
        self.spin_less = QDoubleSpinBox()
        self.spin_less.setRange(-999999, 999999)
        self.spin_less.setSingleStep(0.1)
        self.spin_less.setDecimals(2)
        self.spin_less.setEnabled(False)
        rb_less.toggled.connect(lambda checked: self.spin_less.setEnabled(checked))
        less_layout.addWidget(rb_less)
        less_layout.addWidget(self.spin_less, stretch=1)
        self.filter_options['less'] = (rb_less, self.spin_less)
        layout.addLayout(less_layout)
        
        # فیلتر برابر با
        equal_layout = QHBoxLayout()
        rb_equal = QRadioButton("برابر با")
        self.spin_equal = QDoubleSpinBox()
        self.spin_equal.setRange(-999999, 999999)
        self.spin_equal.setSingleStep(0.1)
        self.spin_equal.setDecimals(2)
        self.spin_equal.setEnabled(False)
        rb_equal.toggled.connect(lambda checked: self.spin_equal.setEnabled(checked))
        equal_layout.addWidget(rb_equal)
        equal_layout.addWidget(self.spin_equal, stretch=1)
        self.filter_options['equal'] = (rb_equal, self.spin_equal)
        layout.addLayout(equal_layout)
        
        # فیلتر بین
        between_layout = QHBoxLayout()
        rb_between = QRadioButton("بین")
        self.spin_from = QDoubleSpinBox()
        self.spin_from.setRange(-999999, 999999)
        self.spin_from.setSingleStep(0.1)
        self.spin_from.setDecimals(2)
        self.spin_from.setEnabled(False)
        lbl_and = QLabel("و")
        self.spin_to = QDoubleSpinBox()
        self.spin_to.setRange(-999999, 999999)
        self.spin_to.setSingleStep(0.1)
        self.spin_to.setDecimals(2)
        self.spin_to.setEnabled(False)
        rb_between.toggled.connect(lambda checked: (self.spin_from.setEnabled(checked), self.spin_to.setEnabled(checked)))
        between_layout.addWidget(rb_between)
        between_layout.addWidget(self.spin_from)
        between_layout.addWidget(lbl_and)
        between_layout.addWidget(self.spin_to)
        self.filter_options['between'] = (rb_between, self.spin_from, self.spin_to)
        layout.addLayout(between_layout)
        
        # فیلتر خالی از محتوا
        empty_layout = QHBoxLayout()
        rb_empty = QRadioButton("خالی از محتوا")
        rb_empty.toggled.connect(lambda checked: None)
        empty_layout.addWidget(rb_empty)
        empty_layout.addStretch()
        self.filter_options['empty'] = rb_empty
        layout.addLayout(empty_layout)
    
    def _create_text_filters(self, layout: QVBoxLayout):
        """ایجاد فیلترهای متنی"""
        
        # فیلتر شامل
        contains_layout = QHBoxLayout()
        rb_contains = QRadioButton("شامل")
        rb_contains.setChecked(True)
        self.input_contains = QLineEdit()
        self.input_contains.setPlaceholderText("متن را وارد کنید...")
        rb_contains.toggled.connect(lambda checked: self.input_contains.setEnabled(checked))
        contains_layout.addWidget(rb_contains)
        contains_layout.addWidget(self.input_contains, stretch=1)
        self.filter_options['contains'] = (rb_contains, self.input_contains)
        layout.addLayout(contains_layout)
        
        # فیلتر برابر با
        exact_layout = QHBoxLayout()
        rb_exact = QRadioButton("برابر با")
        self.input_exact = QLineEdit()
        self.input_exact.setPlaceholderText("متن دقیق را وارد کنید...")
        self.input_exact.setEnabled(False)
        rb_exact.toggled.connect(lambda checked: self.input_exact.setEnabled(checked))
        exact_layout.addWidget(rb_exact)
        exact_layout.addWidget(self.input_exact, stretch=1)
        self.filter_options['exact'] = (rb_exact, self.input_exact)
        layout.addLayout(exact_layout)
        
        # فیلتر شروع با
        starts_layout = QHBoxLayout()
        rb_starts = QRadioButton("شروع با")
        self.input_starts = QLineEdit()
        self.input_starts.setPlaceholderText("شروع متن...")
        self.input_starts.setEnabled(False)
        rb_starts.toggled.connect(lambda checked: self.input_starts.setEnabled(checked))
        starts_layout.addWidget(rb_starts)
        starts_layout.addWidget(self.input_starts, stretch=1)
        self.filter_options['starts'] = (rb_starts, self.input_starts)
        layout.addLayout(starts_layout)
        
        # فیلتر پایان با
        ends_layout = QHBoxLayout()
        rb_ends = QRadioButton("پایان با")
        self.input_ends = QLineEdit()
        self.input_ends.setPlaceholderText("پایان متن...")
        self.input_ends.setEnabled(False)
        rb_ends.toggled.connect(lambda checked: self.input_ends.setEnabled(checked))
        ends_layout.addWidget(rb_ends)
        ends_layout.addWidget(self.input_ends, stretch=1)
        self.filter_options['ends'] = (rb_ends, self.input_ends)
        layout.addLayout(ends_layout)
        
        # فیلتر خالی از محتوا
        empty_layout = QHBoxLayout()
        rb_empty = QRadioButton("خالی از محتوا")
        rb_empty.toggled.connect(lambda checked: None)
        empty_layout.addWidget(rb_empty)
        empty_layout.addStretch()
        self.filter_options['empty'] = rb_empty
        layout.addLayout(empty_layout)
    
    def _apply_filter(self):
        """اعمال فیلتر"""
        try:
            if self.filter_type == FilterType.NUMERIC:
                self.filter_result = self._get_numeric_filter()
            elif self.filter_type == FilterType.TEXT:
                self.filter_result = self._get_text_filter()
            
            # اگر فیلتر None باشد (مثلاً متن خالی)، صرفاً قبول نکن
            if self.filter_result is None:
                if self.filter_type == FilterType.TEXT:
                    return  # پیام warning قبلاً نمایش داده شد
                # برای numeric، اگر هیچ چیز انتخاب نشده، فیلتر نیست
                return
            
            # ذخیره metadata برای restore
            self.filter_metadata = self._get_filter_metadata()
            logger.info(f"فیلتر اعمال شد برای {self.column_name}: {self.filter_metadata}")
            
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطای فیلتر: {str(e)}")
            logger.error(f"Filter error: {e}")
    
    def _get_filter_metadata(self) -> Dict[str, Any]:
        """دریافت metadata فیلتر برای ذخیره و بازیابی"""
        metadata = {"filter_type": self.filter_type.value}
        
        if self.filter_type == FilterType.NUMERIC:
            metadata["greater_checked"] = self.filter_options['greater'][0].isChecked()
            metadata["greater_value"] = self.filter_options['greater'][1].value()
            metadata["less_checked"] = self.filter_options['less'][0].isChecked()
            metadata["less_value"] = self.filter_options['less'][1].value()
            metadata["equal_checked"] = self.filter_options['equal'][0].isChecked()
            metadata["equal_value"] = self.filter_options['equal'][1].value()
            metadata["between_checked"] = self.filter_options['between'][0].isChecked()
            metadata["between_from"] = self.filter_options['between'][1].value()
            metadata["between_to"] = self.filter_options['between'][2].value()
            metadata["empty_checked"] = self.filter_options['empty'].isChecked()
        
        elif self.filter_type == FilterType.TEXT:
            metadata["contains_checked"] = self.filter_options['contains'][0].isChecked()
            metadata["contains_text"] = self.filter_options['contains'][1].text()
            metadata["exact_checked"] = self.filter_options['exact'][0].isChecked()
            metadata["exact_text"] = self.filter_options['exact'][1].text()
            metadata["starts_checked"] = self.filter_options['starts'][0].isChecked()
            metadata["starts_text"] = self.filter_options['starts'][1].text()
            metadata["ends_checked"] = self.filter_options['ends'][0].isChecked()
            metadata["ends_text"] = self.filter_options['ends'][1].text()
            metadata["empty_checked"] = self.filter_options['empty'].isChecked()
        
        return metadata
    
    def _clear_filter(self):
        """حذف فیلتر"""
        self.filter_result = None
        self.accept()
    
    def _get_numeric_filter(self) -> Optional[Callable]:
        """دریافت تابع فیلتر عددی"""
        
        if self.filter_options['greater'][0].isChecked():
            value = self.filter_options['greater'][1].value()
            return lambda x, v=value: not math.isnan(_safe_float(x)) and _safe_float(x) > v
        
        elif self.filter_options['less'][0].isChecked():
            value = self.filter_options['less'][1].value()
            return lambda x, v=value: not math.isnan(_safe_float(x)) and _safe_float(x) < v
        
        elif self.filter_options['equal'][0].isChecked():
            value = self.filter_options['equal'][1].value()
            return lambda x, v=value: not math.isnan(_safe_float(x)) and _safe_float(x) == v
        
        elif self.filter_options['between'][0].isChecked():
            from_val = self.filter_options['between'][1].value()
            to_val = self.filter_options['between'][2].value()
            return lambda x, f=from_val, t=to_val: not math.isnan(_safe_float(x)) and f <= _safe_float(x) <= t
        
        elif self.filter_options['empty'].isChecked():
            return lambda x: not str(x).strip()
        
        return None
    
    def _get_text_filter(self) -> Optional[Callable]:
        """دریافت تابع فیلتر متنی"""
        
        if self.filter_options['contains'][0].isChecked():
            text = self.filter_options['contains'][1].text().strip()
            if not text:
                QMessageBox.warning(self, "هشدار", "لطفاً متن را وارد کنید")
                return None
            search_text = text  # ذخیره برای جلوگیری از closure issues
            return lambda x, t=search_text: t.lower() in str(x).lower()
        
        elif self.filter_options['exact'][0].isChecked():
            text = self.filter_options['exact'][1].text().strip()
            if not text:
                QMessageBox.warning(self, "هشدار", "لطفاً متن را وارد کنید")
                return None
            search_text = text
            return lambda x, t=search_text: t.lower() == str(x).lower()
        
        elif self.filter_options['starts'][0].isChecked():
            text = self.filter_options['starts'][1].text().strip()
            if not text:
                QMessageBox.warning(self, "هشدار", "لطفاً متن را وارد کنید")
                return None
            search_text = text
            return lambda x, t=search_text: str(x).lower().startswith(t.lower())
        
        elif self.filter_options['ends'][0].isChecked():
            text = self.filter_options['ends'][1].text().strip()
            if not text:
                QMessageBox.warning(self, "هشدار", "لطفاً متن را وارد کنید")
                return None
            search_text = text
            return lambda x, t=search_text: str(x).lower().endswith(t.lower())
        
        elif self.filter_options['empty'].isChecked():
            return lambda x: not str(x).strip()
        
        return None
