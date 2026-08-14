# ui/main_window.py
# -*- coding: utf-8 -*-

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

from ui.workers import ScannerWorker, AutoScannerWorker, BrokerLoginWorker
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.settings_dialog import SettingsDialog
from ui.settings_manager import settings_manager
from alerts.bale_notifier import BaleNotifier

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
        # تنظیمات از settings_manager (پروفایل فعال) + هر override اضافی
        self.config = settings_manager.get_active_settings()
        if config_dict:
            self.config.update(config_dict)
        
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

        # ۳. راه‌اندازی notifier بله (تنظیمات از settings_manager خوانده می‌شود)
        bale_cfg = settings_manager.get_bale_config()
        self._bale_notifier = BaleNotifier(
            bot_token=bale_cfg.get("bot_token", ""),
            chat_id=bale_cfg.get("chat_id", ""),
        )
        self._bale_enabled = bale_cfg.get("enabled", False)
        self._bale_top_n   = bale_cfg.get("top_n", 2)

        # ۴. اتصال به کارگزاری (Omex Khobregan)
        self._broker = None           # نمونه OmexKhobreganBroker (lazy init)
        self._broker_connected = False
        self._login_worker: Optional[BrokerLoginWorker] = None

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
        """ساخت و تنظیم جدول اصلی با ستون checkbox و ستون‌های پویا"""
        table = QTableWidget()
        
        # ۱. ستون checkbox انتخاب سطر
        # ۲. ستون‌های ثابت
        fixed_headers = ["✓", "Rank", "Strategy", "Positions", "DTE", "Ticker", "Breakeven"]
        
        # ۳. ستون‌های درصدی پویا (از config)
        dynamic_price_headers = self._generate_price_step_columns()
        
        # ترکیب ستون‌ها
        all_headers = fixed_headers + dynamic_price_headers
        
        table.setColumnCount(len(all_headers))
        table.setHorizontalHeaderLabels(all_headers)
        
        # تنظیم اندازه ستون‌ها
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSortIndicatorShown(True)
        
        table.setColumnWidth(0, 35)   # checkbox
        table.setColumnWidth(1, 50)   # Rank
        table.setColumnWidth(2, 130)  # Strategy
        table.setColumnWidth(3, 220)  # Positions
        table.setColumnWidth(4, 50)   # DTE
        table.setColumnWidth(5, 90)   # Ticker
        table.setColumnWidth(6, 110)  # Breakeven

        # ستون‌های پویا
        for col_idx in range(len(fixed_headers), len(all_headers)):
            table.setColumnWidth(col_idx, 70)

        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # کلیک روی header checkbox برای انتخاب/لغو همه
        header.sectionClicked.connect(self._on_header_clicked)
        # تک‌انتخابی: وقتی checkbox‌ای تیک خورد، بقیه پاک شوند
        table.itemChanged.connect(self._on_checkbox_changed)
        
        return table

    def _on_header_clicked(self, col: int):
        """کلیک روی ستون ✓ → چون تک‌انتخابی است، header click کاری نمی‌کند"""
        pass

    def _on_checkbox_changed(self, item: QTableWidgetItem):
        """تک‌انتخابی: وقتی یک checkbox تیک خورد، بقیه را پاک کن"""
        if item.column() != 0:
            return
        if item.checkState() != Qt.CheckState.Checked:
            self._update_stats()
            return

        # پاک کردن همه checkboxهای دیگر
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if r == item.row():
                continue
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                chk.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_stats()

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
        self.btn_send_to_broker.setEnabled(False)   # تا زمان اتصال غیرفعال است
        self.btn_send_to_broker.clicked.connect(self.send_selected_to_broker)
        layout.addWidget(self.btn_send_to_broker)

        self.btn_broker_connect = QPushButton("🔌 اتصال به کارگزاری")
        self.btn_broker_connect.setObjectName("btn_broker_connect")
        self.btn_broker_connect.setStyleSheet(
            "QPushButton#btn_broker_connect { background-color: #5d4037; }"
            "QPushButton#btn_broker_connect:hover { background-color: #4e342e; }"
            "QPushButton#btn_broker_connect[connected='true'] { background-color: #1b5e20; }"
        )
        self.btn_broker_connect.clicked.connect(self.connect_to_broker)
        layout.addWidget(self.btn_broker_connect)

        self.btn_send_to_bale = QPushButton("📱 ارسال انتخابی به بله")
        self.btn_send_to_bale.setObjectName("btn_send_bale")
        self.btn_send_to_bale.setStyleSheet(
            "QPushButton#btn_send_bale { background-color: #7b2d8b; }"
            "QPushButton#btn_send_bale:hover { background-color: #5e2070; }"
            "QPushButton#btn_send_bale:disabled { background-color: #b8c4d0; color: #7a8a9a; }"
        )
        self.btn_send_to_bale.clicked.connect(self.send_selected_to_bale)
        layout.addWidget(self.btn_send_to_bale)

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
        """شروع اسکن دستی — جدول پاک شده و اسکن جدید شروع می‌شود"""
        # اگر worker در حال اجراست، آن را متوقف کن و worker جدید بساز
        if self.worker is not None:
            if self.worker.isRunning():
                self.worker.stop()
                self.worker.wait(2000)
            self.worker = None

        # پاک‌سازی نتایج قبلی
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.current_results = []
        self._show_empty_state()

        self._set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_update_signal.emit("🔄 در حال دریافت داده‌ها و محاسبه استراتژی‌ها...")

        self.worker = ScannerWorker(self.scanner_engine)
        self.worker.scan_finished.connect(self.on_scan_finished)
        self.worker.scan_failed.connect(self.on_scan_failed)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_changed.connect(self.status_update_signal.emit)
        # finished همیشه اجرا می‌شود — کنترل‌ها را فعال و worker را پاک می‌کند
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

        logger.info("اسکن دستی شروع شد")

    def _on_worker_finished(self):
        """همیشه بعد از پایان worker — چه موفق چه ناموفق — اجرا می‌شود"""
        self._set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        # پاک‌سازی reference برای اسکن بعدی
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def on_scan_finished(self, results):
        """پس از پایان موفقیت‌آمیز اسکن"""
        all_results = results or []

        # فیلتر نمادهای بلاک‌شده از نتایج نهایی
        excluded = set(settings_manager.get_excluded_symbols())
        if excluded:
            before = len(all_results)
            all_results = [
                opp for opp in all_results
                if getattr(opp, 'underlying_ticker', '') not in excluded
            ]
            if before - len(all_results):
                logger.info(f"🚫 {before - len(all_results)} استراتژی بلاک‌شده حذف شد")

        self.current_results = all_results
        # کنترل‌ها در _on_worker_finished فعال می‌شوند

        count = len(self.current_results)
        self.status_update_signal.emit(f"✅ اسکن با موفقیت انجام شد - {count} استراتژی یافت شد")
        self.populate_table(self.current_results)
        self._update_stats()
        logger.info(f"اسکن کامل شد - {count} نتیجه")

        # ارسال نتایج برتر به بله (async — UI بلاک نمی‌شود)
        self._send_bale_alert(self.current_results)

    def on_scan_failed(self, error_msg):
        """در صورت بروز خطا در اسکن"""
        # کنترل‌ها در _on_worker_finished فعال می‌شوند
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
        """پر کردن جدول — سطرهایی که در ستون Positions شامل نماد استثناشده هستند نمایش داده نمی‌شوند"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if not results:
            self._show_empty_state()
            return

        excluded = set(settings_manager.get_excluded_symbols())

        row_idx = 0
        for strat in results:
            if excluded:
                # ساخت متن Positions دقیقاً مثل _populate_row
                legs = getattr(strat, 'legs', [])
                positions_text = ""
                if legs:
                    parts = []
                    for leg in legs:
                        ticker = leg.contract.ticker if leg.contract else 'Stock'
                        side = leg.side.value if hasattr(leg.side, 'value') else str(leg.side)
                        parts.append(f"{ticker} ({leg.ratio}x{side})")
                    positions_text = " | ".join(parts)

                # بررسی: آیا هر یک از نمادهای استثنا در متن Positions وجود دارد؟
                blocked = any(sym in positions_text for sym in excluded)
                if blocked:
                    continue

            self.table.insertRow(row_idx)
            self._populate_row(row_idx, strat)
            row_idx += 1

        self.table.setSortingEnabled(True)
        self._update_stats()

    def _populate_row(self, row: int, strategy: Any):
        """پر کردن سطر بر اساس ساختار Opportunity: checkbox, Rank, Strategy, Positions, DTE, Ticker, Breakeven, [درصدهای P&L]"""
        
        # ۰. ستون checkbox انتخاب سطر
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Unchecked)
        check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        check_item.setData(Qt.ItemDataRole.UserRole + 1, strategy)  # ذخیره شیء کامل
        self.table.setItem(row, 0, check_item)

        # ۱. رتبه (Rank) — ستون ۱
        rank_val = getattr(strategy, 'rank', row + 1)
        rank_item = NumericTableWidgetItem(str(rank_val))
        rank_item.setData(Qt.ItemDataRole.UserRole, int(rank_val))
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, rank_item)

        # ۲. نوع استراتژی (Strategy) — ستون ۲
        strat_name = str(getattr(strategy, 'strategy_name', 'N/A'))
        item_strat = QTableWidgetItem(strat_name)
        font = item_strat.font()
        font.setBold(True)
        item_strat.setFont(font)
        self.table.setItem(row, 2, item_strat)

        # ۳. موقعیت‌ها (Positions) — ستون ۳
        legs = getattr(strategy, 'legs', [])
        if legs:
            positions_parts = []
            for leg in legs:
                ticker = leg.contract.ticker if leg.contract else 'Stock'
                side = leg.side.value if hasattr(leg.side, 'value') else str(leg.side)
                ratio = leg.ratio
                positions_parts.append(f"{ticker} ({ratio}x{side})")
            positions = " | ".join(positions_parts)
        else:
            positions = 'N/A'
        self._set_item(row, 3, positions)

        # ۴. روز تا سررسید (DTE) — ستون ۴
        dte_val = int(getattr(strategy, 'days_to_maturity', 0))
        dte_item = NumericTableWidgetItem(str(dte_val))
        dte_item.setData(Qt.ItemDataRole.UserRole, dte_val)
        dte_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, dte_item)

        # ۵. نماد پایه (Ticker) — ستون ۵
        ticker = str(getattr(strategy, 'underlying_ticker', 'N/A'))
        self._set_item(row, 5, ticker, bold=True)

        # ۶. نقطه سربه‌سر (Breakeven) — ستون ۶
        be_list = getattr(strategy, 'break_even_points', [])
        metadata = getattr(strategy, 'metadata', {})
        if not be_list and isinstance(metadata, dict):
            be_list = metadata.get('break_even_points', [])
        if be_list:
            be_str = ", ".join(f"{p:,.0f}" for p in be_list)
        else:
            be_str = '-'
        self._set_item(row, 6, be_str)

        # ۷. ستون‌های پویا P&L — از ستون ۷ به بعد
        pnl_data = metadata.get('returns_monthly_pct', [])
        if not pnl_data:
            pnl_data = metadata.get('net_returns_closed', [])

        fixed_col_offset = 7
        for i, step_pct in enumerate(self.price_steps):
            col_idx = fixed_col_offset + i
            
            val = pnl_data[i] if i < len(pnl_data) else None

            if val is not None:
                try:
                    num_val = float(val)
                    item_pnl = NumericTableWidgetItem(f"{num_val:,.0f}")
                    item_pnl.setData(Qt.ItemDataRole.UserRole, num_val)
                    item_pnl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    if num_val > 0:
                        item_pnl.setForeground(QBrush(QColor(0, 128, 0)))
                    elif num_val < 0:
                        item_pnl.setForeground(QBrush(QColor(200, 0, 0)))
                        
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
        
        for col in range(self.table.columnCount()):
            self.table.setItem(0, col, QTableWidgetItem(""))
        
        empty_item = QTableWidgetItem("🔍 برای شروع اسکن، دکمه '🔄 اسکن دستی' را بزنید")
        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_item.setForeground(QBrush(QColor(150, 150, 150)))
        font = empty_item.font()
        font.setPointSize(12)
        empty_item.setFont(font)
        
        # span از ستون ۱ (بعد از checkbox) تا آخر
        self.table.setItem(0, 1, empty_item)
        self.table.setSpan(0, 1, 1, self.table.columnCount() - 1)
        self.table.setSortingEnabled(True)

    def _update_stats(self):
        """به‌روزرسانی آمار — شامل تعداد تیک‌شده"""
        is_empty = (
            self.table.rowCount() == 1 and
            self.table.item(0, 1) and
            ("برای شروع اسکن" in self.table.item(0, 1).text() or
             "هیچ استراتژی‌ای" in self.table.item(0, 1).text())
        )
        if is_empty:
            total = 0
            checked = 0
        else:
            total = self.table.rowCount()
            checked = sum(
                1 for r in range(total)
                if self.table.item(r, 0) and
                self.table.item(r, 0).checkState() == Qt.CheckState.Checked
            )

        if checked > 0:
            self.lbl_stats.setText(f"📊 {total} استراتژی یافت شد | ✅ {checked} انتخاب شده")
        else:
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
            import config as cfg
            available = list(cfg.SYMBOL_INFO.keys()) if hasattr(cfg, 'SYMBOL_INFO') else []
            
            dialog = SymbolFilterDialog(
                available_symbols=available,
                parent=self
            )
            dialog.symbols_updated.connect(self._on_excluded_symbols_changed)
            dialog.exec()
        except Exception as e:
            logger.warning(f"عدم امکان باز کردن SymbolFilterDialog: {e}")
            QMessageBox.information(
                self, 
                "اطلاعات", 
                "ماژول فیلتر نمادها در حال توسعه است.\nبه زودی اضافه خواهد شد."
            )

    def _on_excluded_symbols_changed(self, excluded: list):
        """بعد از ذخیره فیلتر نمادها — اعلام به اسکنر"""
        self.config['excluded_symbols'] = excluded
        count = len(excluded)
        msg = f"🚫 {count} نماد بلاک شد" if count else "✅ هیچ نمادی بلاک نیست"
        self.status_update_signal.emit(msg)
        logger.info(f"نمادهای بلاک‌شده به‌روز شد: {excluded}")

    def open_settings_dialog(self):
        """باز کردن پنجره تنظیمات سیستم"""
        try:
            dialog = SettingsDialog(self)
            dialog.settings_saved.connect(self._on_settings_saved)
            dialog.exec()
        except Exception as e:
            logger.warning(f"عدم امکان باز کردن SettingsDialog: {e}")
            QMessageBox.information(
                self,
                "اطلاعات",
                "ماژول تنظیمات سیستم در حال توسعه است.\nبه زودی اضافه خواهد شد."
            )

    def _on_settings_saved(self, new_settings: dict):
        """اعمال تنظیمات جدید پس از بستن SettingsDialog"""
        self.config.update(new_settings)

        # بروزرسانی notifier بله
        self._bale_enabled = new_settings.get("bale_enabled", False)
        self._bale_top_n   = new_settings.get("bale_top_n", 2)
        self._bale_notifier.update_config(
            bot_token=new_settings.get("bale_bot_token", ""),
            chat_id=new_settings.get("bale_chat_id", ""),
        )
        logger.info("تنظیمات سیستم به‌روزرسانی شد")

    def _send_bale_alert(self, opportunities: List) -> None:
        """ارسال n سطر اول نتایج به پیام‌رسان بله (async)"""
        if not self._bale_enabled:
            return
        if not self._bale_notifier.is_configured:
            logger.debug("BaleNotifier: توکن یا chat_id تنظیم نشده")
            return
        self._bale_notifier.send_scan_results(opportunities, top_n=self._bale_top_n)
        logger.info(f"📱 ارسال {min(self._bale_top_n, len(opportunities))} نتیجه به بله آغاز شد")

    def send_selected_to_broker(self):
        """ارسال استراتژی انتخاب‌شده به کارگزاری از طریق مرورگر"""
        if not self._broker_connected or not self._broker:
            QMessageBox.warning(self, "هشدار",
                                "ابتدا با دکمه «🔌 اتصال به کارگزاری» وارد سامانه شوید.")
            return

        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and
            self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]

        if not checked_rows:
            QMessageBox.warning(self, "هشدار", "لطفاً یک سطر را با تیک انتخاب کنید.")
            return

        # خواندن متن Positions از ستون ۳ سطر انتخابی
        row = checked_rows[0]
        positions_item = self.table.item(row, 3)
        if not positions_item or not positions_item.text():
            QMessageBox.warning(self, "خطا", "متن موقعیت‌ها یافت نشد.")
            return
        positions_text = positions_item.text()

        reply = QMessageBox.question(
            self,
            "تأیید ارسال به کارگزاری",
            f"ارسال استراتژی زیر به کارگزاری:\n\n{positions_text}\n\nادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_update_signal.emit("� در حال استخراج موقعیت‌های باز...")
        try:
            existing = self._broker.extract_open_positions()
            result   = self._broker.submit_strategy(positions_text, existing)

            if result['success']:
                self.status_update_signal.emit(f"✅ {result['message']}")
                QMessageBox.information(self, "موفق", result['message'])
            else:
                self.status_update_signal.emit(f"❌ {result['message']}")
                QMessageBox.critical(self, "خطا در ارسال", result['message'])

        except Exception as e:
            self.status_update_signal.emit(f"❌ خطا: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در ارتباط با کارگزاری:\n{e}")
            logger.error(f"خطا در ارسال به کارگزاری: {e}", exc_info=True)

    def send_selected_to_bale(self):
        """ارسال سطر انتخاب‌شده به پیام‌رسان بله"""
        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and
            self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]

        if not checked_rows:
            QMessageBox.warning(self, "هشدار", "لطفاً یک سطر را با تیک انتخاب کنید.")
            return

        if not self._bale_enabled:
            QMessageBox.warning(
                self, "بله غیرفعال",
                "ارسال به بله فعال نیست.\nاز تنظیمات سیستم → تب «اعلان بله» آن را فعال کنید."
            )
            return

        if not self._bale_notifier.is_configured:
            QMessageBox.warning(
                self, "تنظیمات ناقص",
                "توکن یا Chat ID ربات بله تنظیم نشده.\nاز تنظیمات سیستم → تب «اعلان بله» آن را تکمیل کنید."
            )
            return

        # دریافت آبجکت‌های Opportunity از سطرهای تیک‌شده
        selected_opps = []
        for r in checked_rows:
            item = self.table.item(r, 0)
            if item:
                opp = item.data(Qt.ItemDataRole.UserRole + 1)
                if opp is not None:
                    selected_opps.append(opp)

        if not selected_opps:
            # اگر آبجکت ذخیره نشده، از current_results بر اساس ردیف جدول بگیر
            for r in checked_rows:
                rank_item = self.table.item(r, 1)
                if rank_item and r < len(self.current_results):
                    selected_opps.append(self.current_results[r])

        if not selected_opps:
            QMessageBox.warning(self, "خطا", "داده استراتژی انتخابی یافت نشد.")
            return

        # ارسال با همان فرمت استاندارد (top_n=len تا فقط انتخابی‌ها ارسال شوند)
        self._bale_notifier.send_scan_results(selected_opps, top_n=len(selected_opps))
        self.status_update_signal.emit(f"📱 ارسال {len(selected_opps)} استراتژی به بله آغاز شد...")
        logger.info(f"ارسال دستی {len(selected_opps)} استراتژی به بله")

    def clear_results(self):
        """پاک کردن نتایج جدول"""
        if self.table.rowCount() > 0:
            reply = QMessageBox.question(
                self,
                "تأیید پاک کردن",
                "آیا از پاک کردن تمام نتایج اطمینان دارید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.table.setSortingEnabled(False)
                self.table.setRowCount(0)
                self.current_results = []
                self._show_empty_state()
                self._update_stats()
                self.status_update_signal.emit("🗑️ نتایج پاک شد")
                logger.info("نتایج جدول پاک شد")

    def connect_to_broker(self):
        """باز کردن مرورگر و انتظار برای ورود کاربر به سامانه کارگزاری"""
        # اگر قبلاً متصل است، قطع اتصال
        if self._broker_connected:
            reply = QMessageBox.question(
                self, "قطع اتصال",
                "آیا می‌خواهید اتصال به کارگزاری را قطع کنید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._disconnect_broker()
            return

        # اگر login worker در حال اجراست، کاری نکن
        if self._login_worker and self._login_worker.isRunning():
            self.status_update_signal.emit("⌨️ در انتظار ورود کاربر به سامانه...")
            return

        # ساخت broker با تنظیمات فعلی
        try:
            from automation.brokers.Omex_khobregan import OmexKhobreganBroker
            broker_cfg = self.config.get('broker', {})
            self._broker = OmexKhobreganBroker(
                username=broker_cfg.get('username', ''),
                password=broker_cfg.get('password', ''),
            )
        except ImportError as e:
            QMessageBox.critical(
                self, "خطای ماژول",
                f"ماژول کارگزاری بارگذاری نشد:\n{e}\n\n"
                "مطمئن شوید selenium نصب است:\n  pip install selenium"
            )
            return

        # تغییر ظاهر دکمه به حالت «در حال اتصال»
        self.btn_broker_connect.setText("⏳ در حال اتصال...")
        self.btn_broker_connect.setEnabled(False)
        self.status_update_signal.emit("🌐 در حال باز کردن مرورگر کارگزاری...")

        # شروع worker
        self._login_worker = BrokerLoginWorker(self._broker)
        self._login_worker.login_success.connect(self._on_broker_login_success)
        self._login_worker.login_failed.connect(self._on_broker_login_failed)
        self._login_worker.status_changed.connect(self.status_update_signal.emit)
        self._login_worker.finished.connect(self._login_worker.deleteLater)
        self._login_worker.start()

    def _on_broker_login_success(self):
        """پس از ورود موفق کاربر به سامانه کارگزاری"""
        self._broker_connected = True

        # تغییر ظاهر دکمه به «✅ به مرورگر وصل است»
        self.btn_broker_connect.setText("✅ به مرورگر وصل است")
        self.btn_broker_connect.setEnabled(True)
        self.btn_broker_connect.setStyleSheet(
            "QPushButton { background-color: #1b5e20; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #145214; }"
        )

        # فعال کردن دکمه ارسال به کارگزاری
        self.btn_send_to_broker.setEnabled(True)

        self.status_update_signal.emit("✅ اتصال به کارگزاری برقرار شد — آماده ارسال")
        logger.info("اتصال به کارگزاری برقرار شد")

    def _on_broker_login_failed(self, error_msg: str):
        """پس از شکست اتصال"""
        self._broker_connected = False
        self._broker = None

        # بازگشت دکمه به حالت اولیه
        self.btn_broker_connect.setText("🔌 اتصال به کارگزاری")
        self.btn_broker_connect.setEnabled(True)
        self.btn_broker_connect.setStyleSheet(
            "QPushButton { background-color: #5d4037; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e342e; }"
        )

        # غیرفعال نگه داشتن دکمه ارسال
        self.btn_send_to_broker.setEnabled(False)

        self.status_update_signal.emit(f"❌ اتصال ناموفق: {error_msg}")
        QMessageBox.warning(self, "اتصال به کارگزاری", f"اتصال ناموفق:\n{error_msg}")
        logger.warning(f"اتصال به کارگزاری ناموفق: {error_msg}")

    def _disconnect_broker(self):
        """قطع اتصال از کارگزاری"""
        if self._broker:
            try:
                self._broker.close_browser()
            except Exception:
                pass
            self._broker = None

        self._broker_connected = False
        self.btn_broker_connect.setText("🔌 اتصال به کارگزاری")
        self.btn_broker_connect.setEnabled(True)
        self.btn_broker_connect.setStyleSheet(
            "QPushButton { background-color: #5d4037; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e342e; }"
        )
        self.btn_send_to_broker.setEnabled(False)
        self.status_update_signal.emit("🔌 اتصال به کارگزاری قطع شد")
        logger.info("اتصال به کارگزاری قطع شد")

    def closeEvent(self, event):
        """هنگام بستن برنامه"""
        if self.auto_scan_timer.isActive():
            self.auto_scan_timer.stop()

        # توقف login worker در صورت اجرا
        if self._login_worker and self._login_worker.isRunning():
            self._login_worker.stop()
            self._login_worker.wait(2000)

        # بستن مرورگر کارگزاری
        if self._broker_connected:
            try:
                self._broker.close_browser()
            except Exception:
                pass

        for w in (self.worker, self.auto_worker):
            if w and w.isRunning():
                if hasattr(w, 'stop'):
                    w.stop()
                else:
                    w.quit()
                w.wait(3000)

        event.accept()
        logger.info("برنامه بسته شد")