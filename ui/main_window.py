# ui/main_window.py
# -*- coding: utf-8 -*-

import sys
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, 
    QSpinBox, QLabel, QHeaderView, QMessageBox, QStatusBar,
    QProgressBar, QFrame, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from ui.workers import ScannerWorker, AutoScannerWorker
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class NumericTableWidgetItem(QTableWidgetItem):
    """آیتم اختصاصی جدول جهت مرتب‌سازی صحیح عددی"""
    def __lt__(self, other):
        try:
            val_self = self.data(Qt.UserRole)
            val_other = other.data(Qt.UserRole)
            if val_self is not None and val_other is not None:
                return float(val_self) < float(val_other)
            return super().__lt__(other)
        except (ValueError, TypeError):
            return super().__lt__(other)


class MainWindow(QMainWindow):
    """
    پنجره اصلی برنامه Option Strategy Scanner
    """
    
    status_update_signal = Signal(str)
    
    def __init__(self, scanner_engine: Any, config: Optional[Dict] = None):
        super().__init__()
        
        self.scanner_engine = scanner_engine
        self.config = config or {}
        
        # متغیرهای مدیریتی
        self.worker: Optional[ScannerWorker] = None
        self.auto_worker: Optional[AutoScannerWorker] = None
        self.current_results: List = []
        
        # ۱. راه‌اندازی UI و StatusBar
        self.init_ui()
        
        # ۲. اتصال سیگنال وضعیت
        self.status_update_signal.connect(self.status_bar.showMessage)
        
        # تنظیم تایمر برای اسکن دوره‌ای
        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.timeout.connect(self.start_scan)
        
        self.load_settings()
        
        # اسکن اولیه
        QTimer.singleShot(500, self.start_scan)
        
        logger.info("پنجره اصلی راه‌اندازی شد")

    def init_ui(self):
        """راه‌اندازی رابط کاربری"""
        self.setWindowTitle("Option Strategy Scanner - دستیار هوشمند اختیار معامله")
        self.resize(1200, 700)
        
        self.setStyleSheet(self._get_global_style())
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ۱. نوار ابزار بالا
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # ۲. نوار پیشرفت
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(20)
        main_layout.addWidget(self.progress_bar)

        # ۳. جدول اصلی نمایش استراتژی‌ها
        self.table = self._create_table()
        main_layout.addWidget(self.table, stretch=1)

        # ۴. نوار ابزار پایین
        bottom_toolbar = self._create_bottom_toolbar()
        main_layout.addWidget(bottom_toolbar)

        # ۵. نوار وضعیت
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("✅ آماده به کار - برای شروع اسکن، دکمه 'اسکن دستی' را بزنید")

    def _get_global_style(self) -> str:
        """استایل کلی برنامه"""
        return """
        QMainWindow {
            background-color: #f5f7fa;
        }
        QTableWidget {
            background-color: white;
            alternate-background-color: #f8f9fc;
            gridline-color: #e1e4e8;
            selection-background-color: #cfe2ff;
        }
        QTableWidget::item {
            padding: 5px;
        }
        QHeaderView::section {
            background-color: #4a6fa5;
            color: white;
            padding: 8px;
            border: 1px solid #3d5f8a;
            font-weight: bold;
        }
        QPushButton {
            background-color: #4a6fa5;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #3d5f8a;
        }
        QPushButton:pressed {
            background-color: #2e4a6b;
        }
        QPushButton:disabled {
            background-color: #b8c4d0;
            color: #7a8a9a;
        }
        QPushButton#btn_send_broker {
            background-color: #2e7d32;
        }
        QPushButton#btn_send_broker:hover {
            background-color: #1b5e20;
        }
        QCheckBox {
            font-weight: bold;
        }
        QSpinBox {
            padding: 4px;
            border: 1px solid #d0d7de;
            border-radius: 4px;
            min-width: 80px;
        }
        QLabel {
            color: #24292e;
        }
        QProgressBar {
            border: 1px solid #d0d7de;
            border-radius: 4px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #4a6fa5;
            border-radius: 4px;
        }
        """

    def _create_toolbar(self) -> QFrame:
        """ساخت نوار ابزار بالایی"""
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        self.btn_refresh = QPushButton("🔄 اسکن دستی")
        self.btn_refresh.clicked.connect(self.start_scan)
        layout.addWidget(self.btn_refresh)

        layout.addWidget(self._create_separator())

        self.chk_auto_scan = QCheckBox("تکرار خودکار هر:")
        self.chk_auto_scan.stateChanged.connect(self.toggle_auto_scan)
        layout.addWidget(self.chk_auto_scan)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(self.config.get('auto_scan_interval', 2))
        self.spin_interval.setSuffix(" دقیقه")
        self.spin_interval.setEnabled(False)
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        layout.addWidget(self.spin_interval)

        layout.addStretch()

        self.btn_symbol_filter = QPushButton("🔍 فیلتر نمادها")
        self.btn_symbol_filter.clicked.connect(self.open_symbol_filter_dialog)
        layout.addWidget(self.btn_symbol_filter)

        self.btn_settings = QPushButton("⚙️ تنظیمات سیستم")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        layout.addWidget(self.btn_settings)

        return toolbar

    def _create_separator(self) -> QFrame:
        """ساخت جداکننده عمودی"""
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setMaximumWidth(2)
        separator.setStyleSheet("background-color: #d0d7de;")
        return separator

    def _create_table(self) -> QTableWidget:
        """ساخت و تنظیم جدول اصلی"""
        table = QTableWidget()
        
        headers = [
            "انتخاب", 
            "نوع استراتژی", 
            "نماد پایه", 
            "بازدهی (%)", 
            "حد ریسک", 
            "وجه تضمین", 
            "امتیاز", 
            "جزئیات Legها",
            "وضعیت"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        
        table.setColumnWidth(0, 60)
        
        return table

    def _create_bottom_toolbar(self) -> QFrame:
        """ساخت نوار ابزار پایینی"""
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_stats = QLabel("📊 ۰ استراتژی | ۰ انتخاب‌شده")
        layout.addWidget(self.lbl_stats)

        layout.addStretch()

        self.btn_send_to_broker = QPushButton("🚀 ارسال موقعیت‌های انتخابی به کارگزاری")
        self.btn_send_to_broker.setObjectName("btn_send_broker")
        self.btn_send_to_broker.clicked.connect(self.send_selected_to_broker)
        layout.addWidget(self.btn_send_to_broker)

        self.btn_clear = QPushButton("🗑️ پاک کردن نتایج")
        self.btn_clear.clicked.connect(self.clear_results)
        layout.addWidget(self.btn_clear)

        return toolbar

    def load_settings(self):
        """بارگذاری تنظیمات ذخیره‌شده"""
        auto_scan_enabled = self.config.get('auto_scan_enabled', False)
        if auto_scan_enabled:
            self.chk_auto_scan.setChecked(True)
            self.spin_interval.setEnabled(True)
            self.toggle_auto_scan(Qt.CheckState.Checked.value)

    # ==================== متدهای اجرایی ====================

    def start_scan(self):
        """شروع اسکن در ورکر پس‌زمینه"""
        if self.worker and self.worker.isRunning():
            logger.warning("اسکن در حال اجراست، درخواست جدید رد شد")
            self.status_update_signal.emit("⏳ اسکن در حال انجام است...")
            return

        self._set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_update_signal.emit("🔄 در حال دریافت داده‌ها و محاسبه استراتژی‌ها...")

        self.worker = ScannerWorker(self.scanner_engine)
        self.worker.scan_finished.connect(self.on_scan_finished)
        self.worker.scan_failed.connect(self.on_scan_failed)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_changed.connect(self.status_update_signal.emit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

        logger.info("اسکن شروع شد")

    def on_scan_finished(self, results):
        """پس از پایان موفقیت‌آمیز اسکن"""
        self.current_results = results or []
        self._set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        
        count = len(self.current_results)
        self.status_update_signal.emit(f"✅ اسکن با موفقیت انجام شد - {count} استراتژی یافت شد")
        self.populate_table(self.current_results)
        self._update_stats()
        
        logger.info(f"اسکن کامل شد - {count} نتیجه")

    def on_scan_failed(self, error_msg):
        """در صورت بروز خطا در اسکن"""
        self._set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_update_signal.emit(f"❌ خطا در اسکن: {error_msg}")
        
        QMessageBox.critical(
            self, 
            "خطا در اسکن", 
            f"خطایی در حین اسکن رخ داد:\n\n{error_msg}\n\nلطفاً تنظیمات را بررسی کرده و دوباره تلاش کنید."
        )
        
        logger.error(f"خطا در اسکن: {error_msg}")

    def on_progress_updated(self, percent: int, status: str):
        """به‌روزرسانی پیشرفت اسکن"""
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}% - {status}")

    def populate_table(self, results: List):
        """پر کردن جدول با داده‌های دریافتی"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if not results:
            self._show_empty_state()
            return

        for row_idx, strat in enumerate(results):
            self.table.insertRow(row_idx)
            self._add_checkbox(row_idx)
            self._populate_row(row_idx, strat)

        self.table.setSortingEnabled(True)
        self._update_stats()

    def _add_checkbox(self, row: int):
        """افزودن چک‌باکس به سطر"""
        chk_box = QCheckBox()
        chk_box.checkStateChanged.connect(lambda: self._on_selection_changed())
        
        chk_widget = QWidget()
        layout = QHBoxLayout(chk_widget)
        layout.addWidget(chk_box)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.table.setCellWidget(row, 0, chk_widget)

    def _populate_row(self, row: int, strategy: Any):
        """پر کردن یک سطر از جدول و ذخیره شیء استراتژی"""
        data = {
            'name': getattr(strategy, 'name', 'N/A'),
            'symbol': getattr(strategy, 'ua_symbol', getattr(strategy, 'symbol', 'N/A')),
            'return_pct': float(getattr(strategy, 'return_pct', 0)),
            'risk': getattr(strategy, 'risk', 'N/A'),
            'margin': float(getattr(strategy, 'margin', 0)),
            'score': float(getattr(strategy, 'score', 0)),
            'legs': getattr(strategy, 'legs_summary', 'N/A'),
            'status': getattr(strategy, 'status', 'جدید')
        }
        
        # ستون ۱: نوع استراتژی (ذخیره کامل شیء strategy جهت استخراج امن هنگام سورت)
        item_name = QTableWidgetItem(str(data['name']))
        font = item_name.font()
        font.setBold(True)
        item_name.setFont(font)
        item_name.setData(Qt.UserRole, strategy)
        self.table.setItem(row, 1, item_name)
        
        # ستون ۲: نماد پایه
        self._set_item(row, 2, data['symbol'])
        
        # ستون ۳: بازدهی (عددی)
        item_ret = NumericTableWidgetItem(f"{data['return_pct']:.2f}%")
        item_ret.setData(Qt.UserRole, data['return_pct'])
        if data['return_pct'] > 0:
            item_ret.setForeground(QBrush(QColor(0, 128, 0)))
        elif data['return_pct'] < 0:
            item_ret.setForeground(QBrush(QColor(200, 0, 0)))
        self.table.setItem(row, 3, item_ret)
        
        # ستون ۴: حد ریسک
        self._set_item(row, 4, str(data['risk']))
        
        # ستون ۵: وجه تضمین (عددی)
        item_margin = NumericTableWidgetItem(f"{int(data['margin']):,}")
        item_margin.setData(Qt.UserRole, data['margin'])
        self.table.setItem(row, 5, item_margin)
        
        # ستون ۶: امتیاز (عددی)
        score_item = NumericTableWidgetItem(f"{data['score']:.2f}")
        score_item.setData(Qt.UserRole, data['score'])
        if data['score'] > 0.7:
            score_item.setBackground(QBrush(QColor(144, 238, 144)))
        elif data['score'] > 0.4:
            score_item.setBackground(QBrush(QColor(255, 255, 150)))
        else:
            score_item.setBackground(QBrush(QColor(255, 200, 200)))
        self.table.setItem(row, 6, score_item)
        
        # ستون ۷: جزئیات Legها
        self._set_item(row, 7, data['legs'])
        
        # ستون ۸: وضعیت
        status_item = QTableWidgetItem(data['status'])
        if str(data['status']).lower() == 'جدید':
            status_item.setForeground(QBrush(QColor(0, 100, 200)))
        elif str(data['status']).lower() == 'اجرا شده':
            status_item.setForeground(QBrush(QColor(0, 128, 0)))
        self.table.setItem(row, 8, status_item)

    def _set_item(self, row: int, col: int, text: str, bold: bool = False):
        """تنظیم یک آیتم متنی ساده در جدول"""
        item = QTableWidgetItem(str(text))
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.table.setItem(row, col, item)

    def _show_empty_state(self):
        """نمایش حالت بدون داده"""
        self.table.setRowCount(1)
        empty_item = QTableWidgetItem("هیچ استراتژی‌ای یافت نشد")
        empty_item.setTextAlignment(Qt.AlignCenter)
        self.table.setSpan(0, 0, 1, self.table.columnCount())
        self.table.setItem(0, 0, empty_item)

    def _on_selection_changed(self):
        """تغییر در انتخاب سطرها"""
        self._update_stats()

    def _update_stats(self):
        """به‌روزرسانی آمار"""
        if self.table.rowCount() == 1 and self.table.item(0, 0) and self.table.item(0, 0).text() == "هیچ استراتژی‌ای یافت نشد":
            total = 0
        else:
            total = self.table.rowCount()
            
        selected = self._get_selected_rows()
        self.lbl_stats.setText(f"📊 {total} استراتژی | {len(selected)} انتخاب‌شده")

    def _get_selected_rows(self) -> List[int]:
        """دریافت ایندکس سطرهای انتخاب‌شده"""
        selected = []
        for row in range(self.table.rowCount()):
            cell_widget = self.table.cellWidget(row, 0)
            if cell_widget:
                chk_box = cell_widget.findChild(QCheckBox)
                if chk_box and chk_box.isChecked():
                    selected.append(row)
        return selected

    def _set_controls_enabled(self, enabled: bool):
        """فعال/غیرفعال کردن کنترل‌ها"""
        self.btn_refresh.setEnabled(enabled)
        self.chk_auto_scan.setEnabled(enabled)
        self.spin_interval.setEnabled(enabled and self.chk_auto_scan.isChecked())
        self.btn_symbol_filter.setEnabled(enabled)
        self.btn_settings.setEnabled(enabled)

    # ==================== متدهای عملیاتی ====================

    def toggle_auto_scan(self, state: int):
        """فعال/غیرفعال‌سازی اسکن دوره‌ای"""
        is_checked = (state == Qt.CheckState.Checked.value or state == True)
        if is_checked:
            interval = self.spin_interval.value()
            interval_ms = interval * 60 * 1000
            self.auto_scan_timer.start(interval_ms)
            self.spin_interval.setEnabled(True)
            self.status_update_signal.emit(f"⏱️ اسکن خودکار هر {interval} دقیقه فعال شد")
            logger.info(f"اسکن خودکار فعال شد - هر {interval} دقیقه")
        else:
            self.auto_scan_timer.stop()
            self.spin_interval.setEnabled(False)
            self.status_update_signal.emit("⏹️ اسکن خودکار غیرفعال شد")
            logger.info("اسکن خودکار غیرفعال شد")

    def _on_interval_changed(self, value: int):
        """در صورت تغییر بازه زمانی اسکن خودکار"""
        if self.chk_auto_scan.isChecked():
            interval_ms = value * 60 * 1000
            self.auto_scan_timer.start(interval_ms)
            self.status_update_signal.emit(f"⏱️ زمان‌بندی اسکن به {value} دقیقه تغییر یافت")

    def open_symbol_filter_dialog(self):
        """باز کردن پنجره فیلتر نمادها"""
        try:
            dialog = SymbolFilterDialog(self.config.get('symbol_filters', {}), self)
            if dialog.exec():
                filters = dialog.get_filters()
                self.config['symbol_filters'] = filters
                logger.info("فیلتر نمادها به‌روزرسانی شد")
        except (ImportError, NameError, AttributeError):
            QMessageBox.information(
                self, 
                "اطلاعات", 
                "ماژول فیلتر نمادها در حال توسعه است.\nبه زودی اضافه خواهد شد."
            )

    def open_settings_dialog(self):
        """باز کردن پنجره تنظیمات سیستم"""
        try:
            dialog = SettingsDialog(self.config, self)
            if dialog.exec():
                new_config = dialog.get_settings()
                self.config.update(new_config)
                logger.info("تنظیمات سیستم به‌روزرسانی شد")
        except (ImportError, NameError, AttributeError):
            QMessageBox.information(
                self, 
                "اطلاعات", 
                "ماژول تنظیمات سیستم در حال توسعه است.\nبه زودی اضافه خواهد شد."
            )

    def send_selected_to_broker(self):
        """ارسال استراتژی‌های انتخاب‌شده به کارگزاری"""
        selected_rows = self._get_selected_rows()
        
        if not selected_rows:
            QMessageBox.warning(
                self, 
                "هشدار", 
                "لطفاً حداقل یک استراتژی را از جدول انتخاب (تیک) کنید."
            )
            return

        selected_strategies = []
        for row in selected_rows:
            item_name = self.table.item(row, 1)
            strategy_obj = item_name.data(Qt.UserRole) if item_name else None
            
            strategy_summary = {
                'row': row,
                'obj': strategy_obj,
                'name': item_name.text() if item_name else '',
                'symbol': self.table.item(row, 2).text() if self.table.item(row, 2) else '',
                'return': self.table.item(row, 3).text() if self.table.item(row, 3) else '',
                'risk': self.table.item(row, 4).text() if self.table.item(row, 4) else '',
                'margin': self.table.item(row, 5).text() if self.table.item(row, 5) else '',
            }
            selected_strategies.append(strategy_summary)

        reply = QMessageBox.question(
            self,
            "تأیید ارسال به کارگزاری",
            f"آیا از ارسال {len(selected_strategies)} استراتژی به کارگزاری اطمینان دارید؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.status_update_signal.emit(f"🚀 در حال ارسال {len(selected_strategies)} استراتژی به کارگزاری...")
            logger.info(f"ارسال {len(selected_strategies)} استراتژی به کارگزاری")

    def clear_results(self):
        """پاک کردن نتایج جدول"""
        if self.table.rowCount() > 0:
            reply = QMessageBox.question(
                self,
                "تأیید پاک کردن",
                "آیا از پاک کردن تمام نتایج اطمینان دارید؟",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.table.setRowCount(0)
                self.current_results = []
                self._update_stats()
                self.status_update_signal.emit("🗑️ نتایج پاک شد")
                logger.info("نتایج جدول پاک شد")

    def closeEvent(self, event):
        """هنگام بستن برنامه"""
        if self.auto_scan_timer.isActive():
            self.auto_scan_timer.stop()
        
        for w in (self.worker, self.auto_worker):
            if w and w.isRunning():
                if hasattr(w, 'stop'):
                    w.stop()
                else:
                    w.quit()
                w.wait(3000)
        
        event.accept()
        logger.info("برنامه بسته شد")