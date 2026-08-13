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

# دریافت تنظیمات از config
import config

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
    
    def __init__(self, scanner_engine: Any, config_dict: Optional[Dict] = None):
        super().__init__()
        
        self.scanner_engine = scanner_engine
        self.config = config_dict or {}
        
        # دریافت تنظیمات بازه درصدی قیمت از config.py
        self.price_range_config = self.config.get(
            'price_range', 
            config.PRICE_RANGE_CONFIG  # استفاده از تنظیمات config.py
        )
        
        # متغیرهای مدیریتی
        self.worker: Optional[ScannerWorker] = None
        self.auto_worker: Optional[AutoScannerWorker] = None
        self.current_results: List = []
        self.price_steps: List[float] = []
        
        # ۱. راه‌اندازی UI و StatusBar
        self.init_ui()
        
        # ۲. اتصال سیگنال وضعیت
        self.status_update_signal.connect(self.status_bar.showMessage)
        
        # تنظیم تایمر برای اسکن دوره‌ای
        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.timeout.connect(self.start_scan)
        
        self.load_settings()
        
        # نمایش پیام خوش‌آمدگویی
        self.status_bar.showMessage("✅ آماده به کار - برای شروع اسکن، دکمه '🔄 اسکن دستی' را بزنید")
        
        # نمایش حالت خالی در جدول
        self._show_empty_state()
        
        logger.info("پنجره اصلی با ساختار ستون‌های جدید راه‌اندازی شد (بدون اسکن خودکار)")

    def _generate_price_step_columns(self) -> List[str]:
        """
        تولید پویا لیست عناوین ستون‌های درصدی تغییر قیمت
        با استفاده از تنظیمات config.PRICE_RANGE_CONFIG
        """
        cfg = self.price_range_config
        min_p = cfg.get("min_percent", -45.0)
        max_p = cfg.get("max_percent", 45.0)
        num_pts = cfg.get("num_points", 21)
        step_sz = cfg.get("step_size", None)
        fmt = cfg.get("labels_format", "{:.1f}%")

        if step_sz is not None and step_sz > 0:
            steps = []
            curr = min_p
            while curr <= max_p + 1e-9:
                steps.append(curr)
                curr += step_sz
            self.price_steps = steps
        else:
            if num_pts <= 1:
                self.price_steps = [min_p]
            else:
                step = (max_p - min_p) / (num_pts - 1)
                self.price_steps = [min_p + i * step for i in range(num_pts)]

        headers = []
        for val in self.price_steps:
            headers.append(fmt.format(val))
            
        return headers

    def init_ui(self):
        """راه‌اندازی رابط کاربری"""
        self.setWindowTitle("Option Strategy Scanner - دستیار هوشمند اختیار معامله")
        self.resize(1350, 750)
        
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
        self.status_bar.showMessage("✅ آماده به کار - برای شروع اسکن، دکمه '🔄 اسکن دستی' را بزنید")

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
            padding: 4px;
        }
        QHeaderView::section {
            background-color: #3b5998;
            color: white;
            padding: 6px;
            border: 1px solid #2d4373;
            font-weight: bold;
            font-size: 11px;
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
        """ساخت و تنظیم جدول اصلی با ستون‌های جدید و پویا"""
        table = QTableWidget()
        
        # ۱. ستون‌های ثابت
        fixed_headers = ["Rank", "Strategy", "Positions", "DTE", "Ticker", "Breakeven"]
        
        # ۲. ستون‌های درصدی پویا (از config)
        dynamic_price_headers = self._generate_price_step_columns()
        
        # ترکیب ستون‌ها
        all_headers = fixed_headers + dynamic_price_headers
        
        table.setColumnCount(len(all_headers))
        table.setHorizontalHeaderLabels(all_headers)
        
        # تنظیم اندازه ستون‌ها
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # ستون‌های ثابت اندازه مشخص‌تری می‌گیرند
        table.setColumnWidth(0, 50)   # Rank
        table.setColumnWidth(1, 130)  # Strategy
        table.setColumnWidth(2, 220)  # Positions
        table.setColumnWidth(3, 50)   # DTE
        table.setColumnWidth(4, 90)   # Ticker
        table.setColumnWidth(5, 90)   # Breakeven

        # ستون‌های پویا
        for col_idx in range(len(fixed_headers), len(all_headers)):
            table.setColumnWidth(col_idx, 70)

        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        
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

        self.lbl_stats = QLabel("📊 ۰ استراتژی یافت شد")
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
        """پر کردن جدول بر اساس ساختار ستون‌های جدید"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if not results:
            self._show_empty_state()
            return

        for row_idx, strat in enumerate(results):
            self.table.insertRow(row_idx)
            self._populate_row(row_idx, strat)

        self.table.setSortingEnabled(True)
        self._update_stats()

    def _populate_row(self, row: int, strategy: Any):
        """پر کردن سطر بر اساس ساختار جدید: Rank, Strategy, Positions, DTE, Ticker, Breakeven, [درصدهای تغییر قیمت]"""
        
        # ۱. رتبه (Rank)
        rank_val = getattr(strategy, 'rank', row + 1)
        rank_item = NumericTableWidgetItem(str(rank_val))
        rank_item.setData(Qt.UserRole, int(rank_val))
        rank_item.setTextAlignment(Qt.AlignCenter)
        rank_item.setData(Qt.UserRole + 1, strategy)  # ذخیره کامپوننت استراتژی
        self.table.setItem(row, 0, rank_item)

        # ۲. نوع استراتژی (Strategy)
        strat_name = str(getattr(strategy, 'name', getattr(strategy, 'strategy_type', 'N/A')))
        item_strat = QTableWidgetItem(strat_name)
        font = item_strat.font()
        font.setBold(True)
        item_strat.setFont(font)
        self.table.setItem(row, 1, item_strat)

        # ۳. موقعیت‌ها (Positions)
        positions = str(getattr(strategy, 'positions', getattr(strategy, 'legs_summary', 'N/A')))
        self._set_item(row, 2, positions)

        # ۴. روز تا سررسید (DTE)
        try:
            dte_val = int(getattr(strategy, 'dte', 0))
        except (ValueError, TypeError):
            dte_val = 0
        dte_item = NumericTableWidgetItem(str(dte_val))
        dte_item.setData(Qt.UserRole, dte_val)
        dte_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, dte_item)

        # ۵. نماد پایه (Ticker)
        ticker = str(getattr(strategy, 'ticker', getattr(strategy, 'ua_symbol', 'N/A')))
        self._set_item(row, 4, ticker, bold=True)

        # ۶. نقطه بزنگاه (Breakeven)
        be_val = getattr(strategy, 'breakeven', 'N/A')
        self._set_item(row, 5, str(be_val))

        # ۷. پر کردن ستون‌های پویا درصدی (Payoff Matrix)
        payoff_data = getattr(strategy, 'payoff_matrix', getattr(strategy, 'matrix', {}))
        
        fixed_col_offset = 6
        for i, step_pct in enumerate(self.price_steps):
            col_idx = fixed_col_offset + i
            
            val = None
            if isinstance(payoff_data, dict):
                val = payoff_data.get(step_pct, payoff_data.get(f"{step_pct:.1f}%", None))
            elif isinstance(payoff_data, (list, tuple)) and i < len(payoff_data):
                val = payoff_data[i]

            if val is not None:
                try:
                    num_val = float(val)
                    item_pnl = NumericTableWidgetItem(f"{num_val:,.0f}")
                    item_pnl.setData(Qt.UserRole, num_val)
                    item_pnl.setTextAlignment(Qt.AlignCenter)
                    
                    if num_val > 0:
                        item_pnl.setForeground(QBrush(QColor(0, 128, 0)))  # سبز
                    elif num_val < 0:
                        item_pnl.setForeground(QBrush(QColor(200, 0, 0)))  # قرمز
                        
                    self.table.setItem(row, col_idx, item_pnl)
                except (ValueError, TypeError):
                    self._set_item(row, col_idx, str(val))
            else:
                self._set_item(row, col_idx, "-")

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
        self.table.setSortingEnabled(False)
        self.table.setRowCount(1)
        
        # پاک کردن تمام سلول‌ها و تنظیم یک سلول یکپارچه
        for col in range(self.table.columnCount()):
            item = QTableWidgetItem("")
            self.table.setItem(0, col, item)
        
        # تنظیم پیام در ستون اول با Span
        empty_item = QTableWidgetItem("🔍 برای شروع اسکن، دکمه '🔄 اسکن دستی' را بزنید")
        empty_item.setTextAlignment(Qt.AlignCenter)
        empty_item.setForeground(QBrush(QColor(150, 150, 150)))
        font = empty_item.font()
        font.setPointSize(12)
        empty_item.setFont(font)
        
        self.table.setItem(0, 0, empty_item)
        self.table.setSpan(0, 0, 1, self.table.columnCount())
        self.table.setSortingEnabled(True)

    def _update_stats(self):
        """به‌روزرسانی آمار"""
        if self.table.rowCount() == 1 and self.table.item(0, 0):
            text = self.table.item(0, 0).text()
            if "برای شروع اسکن" in text or "هیچ استراتژی‌ای یافت نشد" in text:
                total = 0
            else:
                total = self.table.rowCount()
        else:
            total = self.table.rowCount()
            
        self.lbl_stats.setText(f"📊 {total} استراتژی یافت شد")

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
        is_checked = (state == Qt.CheckState.Checked.value or state is True)
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
        except Exception as e:
            logger.warning(f"عدم امکان باز کردن SymbolFilterDialog: {e}")
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
                # در صورت تغییر تنظیمات بازه درصدی، جدول مجدداً تنظیم می‌شود
                if 'price_range' in new_config:
                    self.price_range_config = new_config['price_range']
                    self.table = self._create_table()
                    self._show_empty_state()
                logger.info("تنظیمات سیستم به‌روزرسانی شد")
        except Exception as e:
            logger.warning(f"عدم امکان باز کردن SettingsDialog: {e}")
            QMessageBox.information(
                self, 
                "اطلاعات", 
                "ماژول تنظیمات سیستم در حال توسعه است.\nبه زودی اضافه خواهد شد."
            )

    def send_selected_to_broker(self):
        """ارسال استراتژی‌های انتخاب‌شده به کارگزاری"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, 
                "هشدار", 
                "لطفاً حداقل یک سطر از جدول را برای ارسال انتخاب کنید."
            )
            return

        selected_rows = list(set([item.row() for item in selected_items]))

        reply = QMessageBox.question(
            self,
            "تأیید ارسال به کارگزاری",
            f"آیا از ارسال {len(selected_rows)} استراتژی انتخابی به کارگزاری اطمینان دارید؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.status_update_signal.emit(f"🚀 در حال ارسال {len(selected_rows)} استراتژی به کارگزاری...")
            logger.info(f"ارسال {len(selected_rows)} استراتژی به کارگزاری")
            QMessageBox.information(self, "موفقیت", "استراتژی‌های انتخابی با موفقیت ارسال شدند.")

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
                self.table.setSortingEnabled(False)
                self.table.setRowCount(0)
                self.current_results = []
                self._show_empty_state()
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