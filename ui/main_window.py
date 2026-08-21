# ui/main_window.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, 
    QSpinBox, QSlider, QLabel, QHeaderView, QMessageBox, QStatusBar,
    QProgressBar, QFrame, QApplication, QToolButton, QMenu,
    QSplitter, QGroupBox, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont

from ui.workers import (
    ScannerWorker, 
    AutoScannerWorker, 
    BrokerLoginWorker, 
    TelemetryWorker, 
    BatchUpdateManager
)
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.settings_dialog import SettingsDialog
from ui.settings_manager import settings_manager
from ui.payoff_chart_dialog import PayoffChartDialog
from ui import theme as ui_theme
from alerts.bale_notifier import BaleNotifier

import config

logger = logging.getLogger("OptionScanner.UI.MainWindow")


class NumericTableWidgetItem(QTableWidgetItem):
    """آیتم اختصاصی جدول جهت مرتب‌سازی صحیح عددی و مقایسه داده‌ها"""
    def __lt__(self, other):
        try:
            val_self = self.data(Qt.ItemDataRole.UserRole)
            val_other = other.data(Qt.ItemDataRole.UserRole)
            if val_self is not None and val_other is not None:
                return float(val_self) < float(val_other)
            return super().__lt__(other)
        except (ValueError, TypeError):
            return super().__lt__(other)


class StrategyInspectorWidget(QGroupBox):
    """
    پنل اختصاصی تحلیل عمیق استراتژی، شبیه‌ساز What-If، تفکیک پایه‌ها و اجرای سریع سفارش
    """
    execute_requested = Signal(object)
    send_bale_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("🔍 تحلیل عمیق و شبیه‌ساز استراتژی", parent)
        self.current_strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 15, 10, 10)

        # ۱. خلاصه مالی (مارجین، بازده و ریسک)
        summary_frame = QFrame()
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)

        self.lbl_strategy_title = QLabel("عنوان: -")
        self.lbl_strategy_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #58a6ff;")
        summary_layout.addWidget(self.lbl_strategy_title)

        row1 = QHBoxLayout()
        self.lbl_margin = QLabel("وجه تضمین: -")
        self.lbl_roi = QLabel("بازده روی مارجین: -")
        row1.addWidget(self.lbl_margin)
        row1.addWidget(self.lbl_roi)
        summary_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_max_profit = QLabel("حداکثر سود: -")
        self.lbl_max_risk = QLabel("حداکثر ریسک: -")
        row2.addWidget(self.lbl_max_profit)
        row2.addWidget(self.lbl_max_risk)
        summary_layout.addLayout(row2)

        layout.addWidget(summary_frame)

        # ۲. جدول تفکیک پایه‌ها (Legs Breakdown)
        lbl_legs = QLabel("📌 پایه‌های معاملاتی استراتژی:")
        lbl_legs.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_legs)

        self.legs_table = QTableWidget(0, 5)
        self.legs_table.setHorizontalHeaderLabels(["نوع", "قرارداد / سررسید", "قیمت", "تعداد", "سمت"])
        self.legs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.legs_table.setFixedHeight(120)
        self.legs_table.setAlternatingRowColors(True)
        layout.addWidget(self.legs_table)

        # ۳. شبیه‌ساز What-If
        sim_group = QGroupBox("شبیه‌ساز تغییر قیمت دارایی پایه (What-If)")
        sim_layout = QVBoxLayout(sim_group)
        sim_layout.setSpacing(6)

        slider_box = QHBoxLayout()
        self.lbl_slider_min = QLabel("-۲۰%")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-20, 20)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.lbl_slider_val = QLabel(" ۰% ")
        self.lbl_slider_val.setStyleSheet("font-weight: bold; min-width: 40px;")
        self.lbl_slider_max = QLabel("+۲۰%")

        slider_box.addWidget(self.lbl_slider_min)
        slider_box.addWidget(self.slider)
        slider_box.addWidget(self.lbl_slider_max)
        slider_box.addWidget(self.lbl_slider_val)
        sim_layout.addLayout(slider_box)

        self.lbl_sim_pnl = QLabel("سود/زیان برآورد در سررسید: ۰ ریال")
        self.lbl_sim_pnl.setStyleSheet("font-weight: bold; font-size: 12px;")
        sim_layout.addWidget(self.lbl_sim_pnl)
        layout.addWidget(sim_group)

        # ۴. دکمه‌های عملیات سریع
        action_layout = QHBoxLayout()
        
        self.btn_execute = QPushButton("⚡ ارسال به کارگزاری")
        self.btn_execute.setStyleSheet("QPushButton { background-color: #238636; font-weight: bold; }")
        self.btn_execute.clicked.connect(self._on_execute_clicked)
        action_layout.addWidget(self.btn_execute)

        self.btn_bale = QPushButton("📱 ارسال به بله")
        self.btn_bale.setStyleSheet("QPushButton { background-color: #7b2d8b; font-weight: bold; }")
        self.btn_bale.clicked.connect(self._on_bale_clicked)
        action_layout.addWidget(self.btn_bale)

        layout.addLayout(action_layout)
        layout.addStretch()

    def set_theme_mode(self, mode: ui_theme.ThemeMode):
        self._theme_mode = mode
        self.setStyleSheet(ui_theme.get_inspector_frame_style(mode))

    def load_strategy(self, strategy: Any):
        """بارگذاری و نمایش دقیق اطلاعات استراتژی انتخاب‌شده"""
        self.current_strategy = strategy
        if not strategy:
            self.clear_inspector()
            return

        strat_name = str(getattr(strategy, 'strategy_name', 'استراتژی'))
        ticker = str(getattr(strategy, 'underlying_ticker', '-'))
        self.lbl_strategy_title.setText(f"{strat_name} روی {ticker}")

        margin_req = getattr(strategy, 'margin_required', 0)
        roi_val = getattr(strategy, 'return_on_margin', 0.0)
        max_p = getattr(strategy, 'max_profit', 0)
        max_l = getattr(strategy, 'max_loss', 0)

        metadata = getattr(strategy, 'metadata', {})
        if isinstance(metadata, dict):
            margin_req = margin_req or metadata.get('margin_required', 0)
            roi_val = roi_val or metadata.get('return_on_margin', 0.0)
            max_p = max_p or metadata.get('max_profit', 0)
            max_l = max_l or metadata.get('max_loss', 0)

        self.lbl_margin.setText(f"وجه تضمین: {ui_theme.format_rial(margin_req, unit='ریال')}")
        self.lbl_roi.setText(f"بازده نسبت به مارجین: {ui_theme.format_percent(roi_val)}")
        self.lbl_max_profit.setText(f"حداکثر سود: {ui_theme.format_rial(max_p, unit='ریال')}")
        self.lbl_max_risk.setText(f"حداکثر ریسک: {ui_theme.format_rial(max_l, unit='ریال')}")

        # تنظیم رنگ‌ها
        self.lbl_roi.setStyleSheet("color: #3fb950; font-weight: bold;" if roi_val >= 0 else "color: #f85149; font-weight: bold;")
        self.lbl_margin.setStyleSheet("color: #d29922; font-weight: bold;")

        # پر کردن جدول پایه‌ها
        legs = getattr(strategy, 'legs', [])
        self.legs_table.setRowCount(len(legs))
        for r, leg in enumerate(legs):
            contract = getattr(leg, 'contract', None)
            symbol_str = contract.ticker if contract else 'سهام پایه'
            expiry_str = ui_theme.format_jalali_date(getattr(contract, 'expiry_date', '')) if contract else '-'
            price_val = getattr(leg, 'entry_price', getattr(contract, 'close_price', 0))
            ratio_val = getattr(leg, 'ratio', 1)
            side_str = "خرید" if str(getattr(leg, 'side', '')).upper() in ("BUY", "SIDE.BUY") else "فروش"
            opt_type = str(getattr(contract, 'option_type', 'STOCK'))

            self.legs_table.setItem(r, 0, QTableWidgetItem(opt_type))
            self.legs_table.setItem(r, 1, QTableWidgetItem(f"{symbol_str} ({expiry_str})"))
            self.legs_table.setItem(r, 2, QTableWidgetItem(ui_theme.format_rial(price_val)))
            self.legs_table.setItem(r, 3, QTableWidgetItem(str(ratio_val)))
            
            side_item = QTableWidgetItem(side_str)
            side_item.setForeground(QBrush(QColor("#3fb950" if side_str == "خرید" else "#f85149")))
            self.legs_table.setItem(r, 4, side_item)

        self.slider.setValue(0)
        self._on_slider_changed(0)

    def _on_slider_changed(self, value: int):
        self.lbl_slider_val.setText(f"{value:+d}%")
        if not self.current_strategy:
            return

        expected_pnl = getattr(self.current_strategy, 'expected_pnl', 0)
        metadata = getattr(self.current_strategy, 'metadata', {})
        if not expected_pnl and isinstance(metadata, dict):
            expected_pnl = metadata.get('expected_pnl', 1000000)

        # مدل‌سازی پیوسته تقریب سود/زیان تحت کشش نوسان دارایی پایه
        simulated_pnl = float(expected_pnl) * (1.0 + (value * 0.05))
        pnl_color = ui_theme.get_pnl_qcolor(simulated_pnl, self._theme_mode)
        
        self.lbl_sim_pnl.setText(f"سود/زیان برآورد: {ui_theme.format_rial(simulated_pnl, unit='ریال', show_sign=True)}")
        self.lbl_sim_pnl.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {pnl_color.name()};")

    def clear_inspector(self):
        self.current_strategy = None
        self.lbl_strategy_title.setText("عنوان: -")
        self.lbl_margin.setText("وجه تضمین: -")
        self.lbl_roi.setText("بازده روی مارجین: -")
        self.lbl_max_profit.setText("حداکثر سود: -")
        self.lbl_max_risk.setText("حداکثر ریسک: -")
        self.lbl_sim_pnl.setText("سود/زیان برآورد در سررسید: ۰ ریال")
        self.legs_table.setRowCount(0)

    def _on_execute_clicked(self):
        if self.current_strategy:
            self.execute_requested.emit(self.current_strategy)

    def _on_bale_clicked(self):
        if self.current_strategy:
            self.send_bale_requested.emit(self.current_strategy)


class MainWindow(QMainWindow):
    """
    پنجره اصلی برنامه Option Strategy Scanner با معماری مدرن و پاسخ‌دهی بالا
    """
    status_update_signal = Signal(str)
    
    def __init__(self, scanner_engine: Any, config_dict: Optional[Dict] = None):
        super().__init__()

        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.timeout.connect(self.start_scan)
        
        self.scanner_engine = scanner_engine
        self.config = settings_manager.get_active_settings()
        if config_dict:
            self.config.update(config_dict)
        
        self.price_range_config = self.config.get(
            'price_range', 
            config.PRICE_RANGE_CONFIG
        )
        
        self.worker: Optional[ScannerWorker] = None
        self.auto_worker: Optional[AutoScannerWorker] = None
        self.telemetry_worker: Optional[TelemetryWorker] = None
        self.batch_manager: Optional[BatchUpdateManager] = None
        
        self.current_results: List = []
        self.price_steps: List[float] = []
        self._theme_mode: ui_theme.ThemeMode = ui_theme.resolve_theme(
            self.config.get("theme", ui_theme.THEME_LIGHT)
        )
        
        # ۱. راه‌اندازی رابط کاربری
        self.init_ui()
        self._apply_theme(self.config.get("theme", ui_theme.THEME_LIGHT))
        
        # ۲. راه‌اندازی اعلان‌گر بله
        bale_cfg = settings_manager.get_bale_config()
        self._bale_notifier = BaleNotifier(
            bot_token=bale_cfg.get("bot_token", ""),
            chat_id=bale_cfg.get("chat_id", ""),
        )
        self._bale_enabled = bale_cfg.get("enabled", False)
        self._bale_top_n   = bale_cfg.get("top_n", 2)

        # ۳. یکپارچه‌سازی با کارگزاری
        self._broker = None
        self._broker_connected = False
        self._login_worker: Optional[BrokerLoginWorker] = None

        # ۴. راه‌اندازی تردهای تلمتری و پایش سیستم
        self._init_background_services()

        self.load_settings()
        self._show_empty_state()
        
        logger.info("Main window initialized with advanced inspector and telemetry")

    def _generate_price_step_columns(self) -> List[str]:
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
        """راه‌اندازی ساختار بصری، چیدمان Splitter و نوار ابزارها"""
        self.setWindowTitle("Option Strategy Scanner - دستیار هوشمند اختیار معامله")
        self.resize(1400, 820)
        self.showMaximized()
        
        layout_dir = self.config.get("layout_direction", "راست‌چین (RTL)")
        self._apply_layout_direction(layout_dir)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 8, 10, 8)

        # نوار ابزار بالا
        self._top_toolbar = self._create_toolbar()
        main_layout.addWidget(self._top_toolbar)

        # نوار پیشرفت
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(18)
        main_layout.addWidget(self.progress_bar)

        # چیدمان ماژولار با Splitter (جدول اصلی + پنل Inspector)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.table = self._create_table()
        self.splitter.addWidget(self.table)

        self.inspector = StrategyInspectorWidget()
        self.inspector.execute_requested.connect(self._on_quick_execute)
        self.inspector.send_bale_requested.connect(self._on_quick_send_bale)
        self.splitter.addWidget(self.inspector)

        # نسبت ابعاد: ۷۰٪ جدول و ۳۰٪ پنل جزئیات
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        main_layout.addWidget(self.splitter, stretch=1)

        # نوار ابزار پایین
        self._bottom_toolbar = self._create_bottom_toolbar()
        main_layout.addWidget(self._bottom_toolbar)

        # نوار وضعیت هوشمند و تلمتری
        self._setup_status_bar()

    def _setup_status_bar(self):
        """ساخت نوار وضعیت تلمتری جهت پایش سلامت شبکه، پینگ و مصرف RAM"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_broker_badge = QLabel("○ کارگزاری: قطع")
        self.lbl_broker_badge.setStyleSheet("color: #8c9bae; margin-left: 10px;")
        
        self.lbl_bale_badge = QLabel("○ بله: غیرفعال")
        self.lbl_bale_badge.setStyleSheet("color: #8c9bae; margin-left: 10px;")

        self.lbl_ping = QLabel("پینگ TSETMC: -- ms")
        self.lbl_ping.setStyleSheet("color: #8c9bae; margin-left: 10px;")

        self.lbl_ram = QLabel("RAM: -- MB")
        self.lbl_ram.setStyleSheet("color: #8c9bae; margin-left: 10px;")

        self.status_bar.addPermanentWidget(self.lbl_broker_badge)
        self.status_bar.addPermanentWidget(self.lbl_bale_badge)
        self.status_bar.addPermanentWidget(self.lbl_ping)
        self.status_bar.addPermanentWidget(self.lbl_ram)
        
        self.status_update_signal.connect(self.status_bar.showMessage)
        self.status_bar.showMessage("✅ آماده به کار - برای شروع، دکمه '🔄 اسکن دستی' را بزنید")

    def _init_background_services(self):
        """راه‌اندازی سرویس‌های پس‌زمینه (Telemetry و Batch Manager)"""
        # راه‌اندازی بروزرسانی دسته‌ای
        self.batch_manager = BatchUpdateManager(interval_ms=150, parent=self)
        
        # راه‌اندازی پایشگر تلمتری
        self.telemetry_worker = TelemetryWorker(host="tsetmc.com", interval_sec=2.5, parent=self)
        self.telemetry_worker.telemetry_updated.connect(self._on_telemetry_updated)
        self.telemetry_worker.start()

    @Slot(dict)
    def _on_telemetry_updated(self, data: dict):
        """دریافت و بروزرسانی داده‌های زنده تلمتری"""
        ping = data.get("ping_ms", -1)
        ram = data.get("ram_usage_mb", 0.0)

        if ping >= 0:
            self.lbl_ping.setText(f"🌐 پینگ TSETMC: {ping}ms")
            self.lbl_ping.setStyleSheet("color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_ping.setText("🌐 پینگ TSETMC: قطع")
            self.lbl_ping.setStyleSheet("color: #f85149; margin-left: 10px;")

        self.lbl_ram.setText(f"💾 RAM: {ram:.1f} MB")

        # وضعیت ربات بله
        if self._bale_enabled and self._bale_notifier.is_configured:
            self.lbl_bale_badge.setText("● بله: آنلاین")
            self.lbl_bale_badge.setStyleSheet("color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_bale_badge.setText("○ بله: غیرفعال")
            self.lbl_bale_badge.setStyleSheet("color: #8c9bae; margin-left: 10px;")

        # وضعیت اتصال کارگزاری
        if self._broker_connected:
            self.lbl_broker_badge.setText("● کارگزاری: متصل")
            self.lbl_broker_badge.setStyleSheet("color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_broker_badge.setText("○ کارگزاری: قطع")
            self.lbl_broker_badge.setStyleSheet("color: #8c9bae; margin-left: 10px;")

    def _apply_theme(self, theme_setting: str) -> None:
        """اعمال پوسته روی پنجره اصلی، جداول و پنل Inspector"""
        self._theme_mode = ui_theme.resolve_theme(theme_setting)
        app = QApplication.instance()
        if app is not None:
            ui_theme.apply_app_theme(app, theme_setting)
        self._refresh_widget_styles()
        self.inspector.set_theme_mode(self._theme_mode)
        if self.current_results:
            self.populate_table(self.current_results)
        elif self.table.rowCount() == 1:
            self._show_empty_state()

    def _apply_layout_direction(self, layout_dir: str) -> None:
        app = QApplication.instance()
        is_ltr = "چپ‌چین" in layout_dir or "LTR" in layout_dir.upper() or layout_dir == "ltr"
        
        if app:
            ui_theme.apply_layout_direction(app, "ltr" if is_ltr else "rtl")
        
        direction = Qt.LayoutDirection.LeftToRight if is_ltr else Qt.LayoutDirection.RightToLeft
        self.setLayoutDirection(direction)
        self._apply_layout_to_all_widgets(direction)

    def _apply_layout_to_all_widgets(self, direction: Qt.LayoutDirection) -> None:
        table_direction = Qt.LayoutDirection.RightToLeft if direction == Qt.LayoutDirection.LeftToRight else Qt.LayoutDirection.LeftToRight
        
        if hasattr(self, "_top_toolbar"):
            self._top_toolbar.setLayoutDirection(direction)
        if hasattr(self, "_bottom_toolbar"):
            self._bottom_toolbar.setLayoutDirection(direction)
        if hasattr(self, "table"):
            self.table.setLayoutDirection(table_direction)
            header = self.table.horizontalHeader()
            if header:
                header.setDefaultAlignment(
                    Qt.AlignmentFlag.AlignRight if direction == Qt.LayoutDirection.LeftToRight 
                    else Qt.AlignmentFlag.AlignLeft
                )

    def _refresh_widget_styles(self) -> None:
        mode = self._theme_mode
        if hasattr(self, "_top_toolbar"):
            self._top_toolbar.setStyleSheet(ui_theme.get_toolbar_frame_style(mode))
        if hasattr(self, "_bottom_toolbar"):
            self._bottom_toolbar.setStyleSheet(ui_theme.get_toolbar_frame_style(mode))
        if hasattr(self, "lbl_interval_min"):
            self.lbl_interval_min.setStyleSheet(ui_theme.get_interval_label_style(mode))

    def _create_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet(ui_theme.get_toolbar_frame_style(self._theme_mode))
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        self.btn_refresh = QPushButton("🔄 اسکن دستی")
        self.btn_refresh.clicked.connect(self.start_scan)
        layout.addWidget(self.btn_refresh)

        layout.addWidget(self._create_separator())

        self.chk_auto_scan = QCheckBox("تکرار خودکار هر:")
        self.chk_auto_scan.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.chk_auto_scan.stateChanged.connect(self.toggle_auto_scan)
        layout.addWidget(self.chk_auto_scan)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(10, 3600)
        self.spin_interval.setValue(self.config.get('auto_scan_interval', 60))
        self.spin_interval.setSuffix(" ثانیه")
        self.spin_interval.setSingleStep(10)
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        layout.addWidget(self.spin_interval)

        self.lbl_interval_min = QLabel()
        self._update_interval_label(self.spin_interval.value())
        self.lbl_interval_min.setStyleSheet(ui_theme.get_interval_label_style(self._theme_mode))
        layout.addWidget(self.lbl_interval_min)

        self.chk_auto_scan.setChecked(True)
        layout.addStretch()

        self.btn_symbol_filter = QPushButton("🔍 فیلتر نمادها")
        self.btn_symbol_filter.clicked.connect(self.open_symbol_filter_dialog)
        layout.addWidget(self.btn_symbol_filter)

        self.btn_settings = QPushButton("⚙️ تنظیمات سیستم")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        layout.addWidget(self.btn_settings)

        return toolbar

    def _create_separator(self) -> QFrame:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setMaximumWidth(2)
        separator.setStyleSheet(ui_theme.get_separator_style(self._theme_mode))
        return separator

    def _create_table(self) -> QTableWidget:
        table = QTableWidget()
        fixed_headers = ["✓", "Rank", "Strategy", "Positions", "DTE / سررسید", "Ticker", "Breakeven"]
        dynamic_price_headers = self._generate_price_step_columns()
        all_headers = fixed_headers + dynamic_price_headers
        
        table.setColumnCount(len(all_headers))
        table.setHorizontalHeaderLabels(all_headers)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSortIndicatorShown(True)
        
        table.setColumnWidth(0, 35)   # Checkbox
        table.setColumnWidth(1, 50)   # Rank
        table.setColumnWidth(2, 130)  # Strategy
        table.setColumnWidth(3, 220)  # Positions
        table.setColumnWidth(4, 110)  # DTE + تاریخ شمسی
        table.setColumnWidth(5, 85)   # Ticker
        table.setColumnWidth(6, 110)  # Breakeven

        for col_idx in range(len(fixed_headers), len(all_headers)):
            table.setColumnWidth(col_idx, 75)

        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # فعال کردن منوی کلیک راست
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)
        
        table.itemChanged.connect(self._on_checkbox_changed)
        table.itemClicked.connect(self._on_table_row_clicked)
        table.itemDoubleClicked.connect(self._on_table_row_double_clicked)
        
        return table

    def _on_table_row_clicked(self, item: QTableWidgetItem):
        """هنگام کلیک روی هر سطر، جزئیات آن بلافاصله در Inspector بارگذاری می‌شود"""
        row = item.row()
        check_item = self.table.item(row, 0)
        if check_item:
            strategy = check_item.data(Qt.ItemDataRole.UserRole + 1)
            if strategy:
                self.inspector.load_strategy(strategy)

    def _on_table_row_double_clicked(self, item: QTableWidgetItem):
        """هنگام دابل‌کلیک روی سطر، پنجره نمودار سود و زیان باز می‌شود"""
        self._open_payoff_chart_for_row(item.row())
    
    def _on_table_context_menu(self, pos):
        """نمایش منوی کلیک راست روی جدول"""
        # پیدا کردن سطر کلیک‌شده
        item = self.table.itemAt(pos)
        if not item:
            logger.debug("No item found at click position")
            return
        
        row = item.row()
        if row < 0:
            logger.debug(f"Invalid row index: {row}")
            return
        
        logger.debug(f"Context menu requested for row: {row}")
        
        # بررسی اینکه آیا استراتژی در این سطر وجود دارد
        check_item = self.table.item(row, 0)
        if not check_item:
            logger.debug(f"No check item found for row: {row}")
            return
        
        strategy = check_item.data(Qt.ItemDataRole.UserRole + 1)
        if not strategy:
            logger.debug(f"No strategy data found for row: {row}")
            return
        
        logger.debug(f"Found strategy: {getattr(strategy, 'strategy_name', 'Unknown')}")
        
        # ایجاد منو
        menu = QMenu(self.table)
        
        # گزینه ترسیم نمودار سود و زیان
        chart_action = menu.addAction("📊 ترسیم نمودار سود و زیان")
        chart_action.triggered.connect(lambda: self._open_payoff_chart_for_row(row))
        
        menu.addSeparator()
        
        # گزینه ارسال به کارگزاری
        send_broker_action = menu.addAction("🚀 ارسال به کارگزاری")
        send_broker_action.triggered.connect(lambda: self._send_to_broker_from_row(row))
        
        # گزینه ارسال به بله
        send_bale_action = menu.addAction("📱 ارسال به بله")
        send_bale_action.triggered.connect(lambda: self._send_to_bale_from_row(row))
        
        menu.exec(self.table.mapToGlobal(pos))
    
    def _open_payoff_chart_for_row(self, row: int):
        """باز کردن نمودار سود و زیان برای سطر مشخص"""
        if row < 0:
            logger.warning(f"Invalid row index for chart: {row}")
            return
        
        check_item = self.table.item(row, 0)
        if not check_item:
            logger.warning(f"No check item found for row: {row}")
            return
        
        strategy = check_item.data(Qt.ItemDataRole.UserRole + 1)
        if not strategy:
            logger.warning(f"No strategy found for row: {row}")
            return
        
        try:
            logger.info(f"Opening payoff chart for strategy: {getattr(strategy, 'strategy_name', 'Unknown')}")
            dialog = PayoffChartDialog(self)
            dialog.load_strategy(strategy, self._theme_mode)
            dialog.exec()
            logger.info("Payoff chart dialog opened successfully")
        except Exception as e:
            logger.error(f"Error opening payoff chart dialog: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در باز کردن نمودار سود و زیان:\n{str(e)}")
    
    def _send_to_broker_from_row(self, row: int):
        """ارسال استراتژی از سطر مشخص به کارگزاری"""
        if row < 0:
            return
        
        # انتخاب سطر
        check_item = self.table.item(row, 0)
        if not check_item:
            return
        
        # تیک‌زدن سطر (اگر قبلاً انتخاب نشده)
        if check_item.checkState() != Qt.CheckState.Checked:
            check_item.setCheckState(Qt.CheckState.Checked)
        
        # ارسال به کارگزاری
        self.send_selected_to_broker()
    
    def _send_to_bale_from_row(self, row: int):
        """ارسال استراتژی از سطر مشخص به بله"""
        if row < 0:
            return
        
        # انتخاب سطر
        check_item = self.table.item(row, 0)
        if not check_item:
            return
        
        # تیک‌زدن سطر (اگر قبلاً انتخاب نشده)
        if check_item.checkState() != Qt.CheckState.Checked:
            check_item.setCheckState(Qt.CheckState.Checked)
        
        # ارسال به بله
        self.send_selected_to_bale()

    def _on_checkbox_changed(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        if item.checkState() != Qt.CheckState.Checked:
            self._update_stats()
            return

        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if r == item.row():
                continue
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                chk.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)

        strategy = item.data(Qt.ItemDataRole.UserRole + 1)
        if strategy:
            self.inspector.load_strategy(strategy)

        self._update_stats()

    def _create_bottom_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet(ui_theme.get_toolbar_frame_style(self._theme_mode))
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_stats = QLabel("📊 ۰ استراتژی یافت شد")
        layout.addWidget(self.lbl_stats)

        layout.addStretch()

        self.btn_broker_connect = QPushButton("🏦 اتصال به کارگزاری")
        self.btn_broker_connect.clicked.connect(self.connect_to_broker)
        layout.addWidget(self.btn_broker_connect)

        self.btn_send_broker = QPushButton("⚡ ارسال به کارگزاری")
        self.btn_send_broker.clicked.connect(self.send_selected_to_broker)
        self.btn_send_broker.setEnabled(False)
        layout.addWidget(self.btn_send_broker)

        self.btn_send_bale = QPushButton("📱 ارسال به بله")
        self.btn_send_bale.clicked.connect(self.send_selected_to_bale)
        layout.addWidget(self.btn_send_bale)

        self.btn_export_excel = QPushButton("📊 ذخیره اکسل")
        self.btn_export_excel.clicked.connect(self.export_results_to_excel)
        layout.addWidget(self.btn_export_excel)

        self.btn_clear_results = QPushButton("🗑️ پاک کردن")
        self.btn_clear_results.clicked.connect(self.clear_results)
        layout.addWidget(self.btn_clear_results)

        return toolbar

    def load_settings(self):
        auto_scan_enabled = self.config.get('auto_scan_enabled', True)
        self.chk_auto_scan.setChecked(auto_scan_enabled)

    # ==================== متدهای اسکن و بروزرسانی ====================

    def start_scan(self):
        """شروع اسکن ناهمگام بازار"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.current_results = []
        self.inspector.clear_inspector()
        self._show_empty_state()

        self._set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_update_signal.emit("🔄 در حال دریافت تابلوی معاملات و تحلیل استراتژی‌ها...")

        self.worker = ScannerWorker(self.scanner_engine)
        self.worker.scan_finished.connect(self.on_scan_finished)
        self.worker.scan_failed.connect(self.on_scan_failed)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_changed.connect(self.status_update_signal.emit)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

        logger.info("Market scan initiated")

    def _on_worker_finished(self):
        self._set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def on_scan_finished(self, results):
        all_results = results or []
        excluded = set(settings_manager.get_excluded_symbols())
        if excluded:
            all_results = [
                opp for opp in all_results
                if getattr(opp, 'underlying_ticker', '') not in excluded
            ]

        self.current_results = all_results
        count = len(self.current_results)
        self.status_update_signal.emit(f"✅ اسکن پایان یافت - {count} استراتژی بهینه یافت شد")
        self.populate_table(self.current_results)
        self._update_stats()

        if self.current_results:
            self.inspector.load_strategy(self.current_results[0])

        self._send_bale_alert(self.current_results)

    def on_scan_failed(self, error_msg):
        self.status_update_signal.emit(f"❌ خطا در اسکن: {error_msg}")
        QMessageBox.critical(
            self,
            "خطا در اسکن",
            f"خطایی رخ داد:\n\n{error_msg}\n\nلطفاً ارتباط با اینترنت یا تنظیمات را بررسی کنید."
        )
        logger.error(f"Scan failed: {error_msg}")

    def on_progress_updated(self, percent: int, status: str):
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}% - {status}")

    def populate_table(self, results: List):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if not results:
            self._show_empty_state()
            return

        excluded = set(settings_manager.get_excluded_symbols())

        row_idx = 0
        for strat in results:
            if excluded:
                legs = getattr(strat, 'legs', [])
                positions_text = ""
                if legs:
                    parts = []
                    for leg in legs:
                        ticker = leg.contract.ticker if leg.contract else 'Stock'
                        side = leg.side.value if hasattr(leg.side, 'value') else str(leg.side)
                        parts.append(f"{ticker} ({leg.ratio}x{side})")
                    positions_text = " | ".join(parts)

                if any(sym in positions_text for sym in excluded):
                    continue

            self.table.insertRow(row_idx)
            self._populate_row(row_idx, strat)
            row_idx += 1

        self.table.setSortingEnabled(True)
        self._update_stats()

    def _populate_row(self, row: int, strategy: Any):
        """پر کردن سطرها با فرمت‌های استاندارد ریالی، تاریخ شمسی و رنگ‌های سود/زیان"""
        # ۰. ستون انتخاب Checkbox
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Unchecked)
        check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        check_item.setData(Qt.ItemDataRole.UserRole + 1, strategy)
        self.table.setItem(row, 0, check_item)

        # ۱. رتبه (Rank)
        rank_val = getattr(strategy, 'rank', row + 1)
        rank_item = NumericTableWidgetItem(str(rank_val))
        rank_item.setData(Qt.ItemDataRole.UserRole, int(rank_val))
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, rank_item)

        # ۲. نام استراتژی
        strat_name = str(getattr(strategy, 'strategy_name', 'N/A'))
        item_strat = QTableWidgetItem(strat_name)
        font = item_strat.font()
        font.setBold(True)
        item_strat.setFont(font)
        self.table.setItem(row, 2, item_strat)

        # ۳. پایه‌ها (Positions)
        legs = getattr(strategy, 'legs', [])
        if legs:
            positions_parts = []
            for leg in legs:
                ticker = leg.contract.ticker if leg.contract else 'سهام'
                side = "خرید" if str(getattr(leg, 'side', '')).upper() in ("BUY", "SIDE.BUY") else "فروش"
                ratio = getattr(leg, 'ratio', 1)
                positions_parts.append(f"{ticker} ({ratio}x{side})")
            positions = " | ".join(positions_parts)
        else:
            positions = 'N/A'
        self._set_item(row, 3, positions)

        # ۴. تاریخ شمسی و DTE
        dte_val = int(getattr(strategy, 'days_to_maturity', 0))
        contract = legs[0].contract if legs else None
        expiry_val = getattr(contract, 'expiry_date', None)
        dte_str = ui_theme.format_jalali_date(expiry_val, include_dte=True) if expiry_val else f"{dte_val} روز"
        
        dte_item = NumericTableWidgetItem(dte_str)
        dte_item.setData(Qt.ItemDataRole.UserRole, dte_val)
        dte_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, dte_item)

        # ۵. نماد پایه (Ticker)
        ticker = str(getattr(strategy, 'underlying_ticker', 'N/A'))
        self._set_item(row, 5, ticker, bold=True)

        # ۶. نقطه سربه‌سر (Breakeven)
        be_list = getattr(strategy, 'break_even_points', [])
        metadata = getattr(strategy, 'metadata', {})
        if not be_list and isinstance(metadata, dict):
            be_list = metadata.get('break_even_points', [])
        if be_list:
            be_str = ", ".join(ui_theme.format_rial(p) for p in be_list)
        else:
            be_str = '-'
        self._set_item(row, 6, be_str)

        # ۷. ستون‌های پویا بازدهی سود و زیان (P&L)
        pnl_data = metadata.get('returns_monthly_pct', [])
        if not pnl_data:
            pnl_data = metadata.get('net_returns_closed', [])

        fixed_col_offset = 7
        pos_color, neg_color = ui_theme.get_pnl_colors(self._theme_mode)
        
        for i, step_pct in enumerate(self.price_steps):
            col_idx = fixed_col_offset + i
            val = pnl_data[i] if i < len(pnl_data) else None

            if val is not None:
                try:
                    num_val = float(val)
                    item_pnl = NumericTableWidgetItem(ui_theme.format_rial(num_val, show_sign=True))
                    item_pnl.setData(Qt.ItemDataRole.UserRole, num_val)
                    item_pnl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    if num_val > 0:
                        item_pnl.setForeground(QBrush(pos_color))
                    elif num_val < 0:
                        item_pnl.setForeground(QBrush(neg_color))
                        
                    self.table.setItem(row, col_idx, item_pnl)
                except (ValueError, TypeError):
                    self._set_item(row, col_idx, str(val))
            else:
                self._set_item(row, col_idx, "-")

    def _set_item(self, row: int, col: int, text: str, bold: bool = False):
        item = QTableWidgetItem(str(text))
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.table.setItem(row, col, item)

    def _show_empty_state(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(1)
        for col in range(self.table.columnCount()):
            self.table.setItem(0, col, QTableWidgetItem(""))
        
        empty_item = QTableWidgetItem("🔍 برای شروع، دکمه '🔄 اسکن دستی' را بزنید")
        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_item.setForeground(QBrush(ui_theme.get_empty_state_color(self._theme_mode)))
        font = empty_item.font()
        font.setPointSize(12)
        empty_item.setFont(font)
        
        self.table.setItem(0, 1, empty_item)
        self.table.setSpan(0, 1, 1, self.table.columnCount() - 1)
        self.table.setSortingEnabled(True)

    def _update_stats(self):
        is_empty = (
            self.table.rowCount() == 1 and
            self.table.item(0, 1) and
            ("برای شروع" in self.table.item(0, 1).text())
        )
        total = 0 if is_empty else self.table.rowCount()
        checked = 0 if is_empty else sum(
            1 for r in range(total)
            if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        )

        if checked > 0:
            self.lbl_stats.setText(f"📊 {total} استراتژی یافت شد | ✅ {checked} انتخاب‌شده")
        else:
            self.lbl_stats.setText(f"📊 {total} استراتژی یافت شد")

    def _set_controls_enabled(self, enabled: bool):
        self.btn_refresh.setEnabled(enabled)
        self.chk_auto_scan.setEnabled(enabled)
        self.spin_interval.setEnabled(enabled and self.chk_auto_scan.isChecked())
        self.btn_symbol_filter.setEnabled(enabled)
        self.btn_settings.setEnabled(enabled)

    # ==================== عملیات اشتراک‌گذاری و اجرای سفارش ====================

    def _on_quick_execute(self, strategy: Any):
        """ارسال مستقیم از پنل Inspector"""
        self._execute_strategy_to_broker(strategy)

    def _on_quick_send_bale(self, strategy: Any):
        """ارسال تکی از پنل Inspector به پیام‌رسان بله"""
        if not self._bale_enabled or not self._bale_notifier.is_configured:
            QMessageBox.warning(self, "تنظیمات بله", "اعلان‌گر بله پیکربندی نشده است.")
            return
        self._bale_notifier.send_scan_results([strategy], top_n=1)
        self.status_update_signal.emit("📱 استراتژی با موفقیت به بله ارسال شد")

    def send_selected_to_broker(self):
        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if not checked_rows:
            QMessageBox.warning(self, "هشدار", "لطفاً یک استراتژی را از جدول انتخاب کنید.")
            return
        
        item = self.table.item(checked_rows[0], 0)
        strategy = item.data(Qt.ItemDataRole.UserRole + 1) if item else None
        if strategy:
            self._execute_strategy_to_broker(strategy)

    def _execute_strategy_to_broker(self, strategy: Any):
        if not self._broker_connected or not self._broker:
            QMessageBox.warning(self, "عدم اتصال", "ابتدا با دکمه «🏦 اتصال به کارگزاری» وارد شوید.")
            return

        strat_name = getattr(strategy, 'strategy_name', 'استراتژی')
        reply = QMessageBox.question(
            self,
            "تأیید امنیتی ارسال سفارش",
            f"آیا از ارسال خودکار سفارش‌های استراتژی «{strat_name}» به کارگزاری اطمینان دارید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_update_signal.emit("⏳ در حال پردازش و ارسال سفارش به هسته معاملاتی...")
        try:
            # ارسال پایه‌ها به کارگزاری
            existing = self._broker.extract_open_positions() if hasattr(self._broker, 'extract_open_positions') else {}
            positions_text = self.table.item(self.table.currentRow(), 3).text() if self.table.currentRow() >= 0 else ""
            result = self._broker.submit_strategy(positions_text, existing)

            if result.get('success', False):
                self.status_update_signal.emit(f"✅ {result.get('message', 'سفارش با موفقیت ثبت شد')}")
                QMessageBox.information(self, "موفق", result.get('message', 'سفارش ثبت شد'))
            else:
                self.status_update_signal.emit(f"❌ {result.get('message', 'خطا در ثبت سفارش')}")
                QMessageBox.critical(self, "خطا در کارگزاری", result.get('message', 'خطا'))
        except Exception as e:
            self.status_update_signal.emit(f"❌ خطا: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در ارتباط با وب‌سرویس:\n{e}")

    def send_selected_to_bale(self):
        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if not checked_rows:
            QMessageBox.warning(self, "هشدار", "لطفاً یک سطر را با تیک انتخاب کنید.")
            return

        selected_opps = [
            self.table.item(r, 0).data(Qt.ItemDataRole.UserRole + 1)
            for r in checked_rows if self.table.item(r, 0)
        ]
        self._bale_notifier.send_scan_results(selected_opps, top_n=len(selected_opps))
        self.status_update_signal.emit(f"📱 ارسال {len(selected_opps)} استراتژی به بله انجام شد")

    def _send_bale_alert(self, opportunities: List) -> None:
        if not self._bale_enabled or not self._bale_notifier.is_configured:
            return
        self._bale_notifier.send_scan_results(opportunities, top_n=self._bale_top_n)

    def toggle_auto_scan(self, state: int):
        is_checked = (state == Qt.CheckState.Checked.value or state is True)
        if is_checked:
            seconds = self.spin_interval.value()
            self.auto_scan_timer.start(seconds * 1000)
            self.spin_interval.setEnabled(True)
            self.status_update_signal.emit(f"اسکن خودکار هر {seconds} ثانیه فعال شد")
        else:
            self.auto_scan_timer.stop()
            self.spin_interval.setEnabled(False)
            self.status_update_signal.emit("اسکن خودکار غیرفعال شد")

    def _update_interval_label(self, seconds: int) -> None:
        mins = seconds / 60
        text = f"({seconds} ثانیه)" if mins < 1 else f"({mins:.1f} دقیقه)"
        if hasattr(self, 'lbl_interval_min'):
            self.lbl_interval_min.setText(text)

    def _on_interval_changed(self, value: int):
        self._update_interval_label(value)
        if self.chk_auto_scan.isChecked():
            self.auto_scan_timer.start(value * 1000)

    def open_symbol_filter_dialog(self):
        try:
            available = list(config.SYMBOL_INFO.keys()) if hasattr(config, 'SYMBOL_INFO') else []
            dialog = SymbolFilterDialog(available_symbols=available, parent=self)
            dialog.symbols_updated.connect(self._on_excluded_symbols_changed)
            dialog.exec()
        except Exception as e:
            logger.warning(f"Error in SymbolFilterDialog: {e}")

    def _on_excluded_symbols_changed(self, excluded: list):
        self.config['excluded_symbols'] = excluded
        count = len(excluded)
        self.status_update_signal.emit(f"🚫 {count} نماد استثنا شد" if count else "✅ همه نمادها فعالند")

    def open_settings_dialog(self):
        try:
            dialog = SettingsDialog(self)
            dialog.settings_saved.connect(self._on_settings_saved)
            dialog.exec()
        except Exception as e:
            logger.warning(f"Error in SettingsDialog: {e}")

    def _on_settings_saved(self, new_settings: dict):
        self.config.update(new_settings)
        self._bale_enabled = new_settings.get("bale_enabled", False)
        self._bale_top_n   = new_settings.get("bale_top_n", 2)
        self._bale_notifier.update_config(
            bot_token=new_settings.get("bale_bot_token", ""),
            chat_id=new_settings.get("bale_chat_id", ""),
        )
        self._apply_theme(new_settings.get("theme", ui_theme.THEME_LIGHT))
        self._apply_layout_direction(new_settings.get("layout_direction", "راست‌چین (RTL)"))

    def connect_to_broker(self):
        if self._broker_connected:
            reply = QMessageBox.question(
                self, "قطع اتصال", "آیا می‌خواهید اتصال به کارگزاری را قطع کنید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._disconnect_broker()
            return

        if self._login_worker and self._login_worker.isRunning():
            return

        try:
            from automation.brokers.Omex_khobregan import OmexKhobreganBroker
            broker_cfg = settings_manager.get_broker_config()
            self._broker = OmexKhobreganBroker(
                username=broker_cfg.get('username', ''),
                password=broker_cfg.get('password', ''),
            )
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"بارگذاری ماژول کارگزاری با خطا مواجه شد:\n{e}")
            return

        self.btn_broker_connect.setText("⏳ در حال اتصال...")
        self.btn_broker_connect.setEnabled(False)
        self.status_update_signal.emit("🌐 در حال باز کردن مرورگر و ورود به کارگزاری...")

        self._login_worker = BrokerLoginWorker(self._broker)
        self._login_worker.login_success.connect(self._on_broker_login_success)
        self._login_worker.login_failed.connect(self._on_broker_login_failed)
        self._login_worker.status_changed.connect(self.status_update_signal.emit)
        self._login_worker.finished.connect(self._login_worker.deleteLater)
        self._login_worker.start()

    def _on_broker_login_success(self):
        self._broker_connected = True
        self.btn_broker_connect.setText("🔌 قطع اتصال")
        self.btn_broker_connect.setEnabled(True)
        self.btn_send_broker.setEnabled(True)
        self.status_update_signal.emit("✅ اتصال به کارگزاری برقرار شد")

    def _on_broker_login_failed(self, error_msg: str):
        self._broker_connected = False
        self._broker = None
        self.btn_broker_connect.setText("🏦 اتصال به کارگزاری")
        self.btn_broker_connect.setEnabled(True)
        self.btn_send_broker.setEnabled(False)
        self.status_update_signal.emit(f"❌ اتصال ناموفق: {error_msg}")
        QMessageBox.warning(self, "اتصال به کارگزاری", f"اتصال ناموفق:\n{error_msg}")

    def _disconnect_broker(self):
        if self._broker:
            try:
                self._broker.close_browser()
            except Exception:
                pass
            self._broker = None

        self._broker_connected = False
        self.btn_broker_connect.setText("🏦 اتصال به کارگزاری")
        self.btn_send_broker.setEnabled(False)
        self.status_update_signal.emit("🔌 اتصال به کارگزاری قطع شد")

    def clear_results(self):
        if self.table.rowCount() > 0:
            reply = QMessageBox.question(
                self, "پاک کردن نتایج", "آیا از پاک کردن تمام نتایج اطمینان دارید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.table.setSortingEnabled(False)
                self.table.setRowCount(0)
                self.current_results = []
                self.inspector.clear_inspector()
                self._show_empty_state()
                self._update_stats()
                self.status_update_signal.emit("🗑️ نتایج پاک شد")

    def export_results_to_excel(self):
        if not self.current_results:
            QMessageBox.information(self, "اطلاعات", "نتیجه‌ای برای ذخیره وجود ندارد.")
            return

        try:
            import jdatetime
            default_name = f"scan_results_{jdatetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        except ImportError:
            from datetime import datetime
            default_name = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        default_dir = str(config.OUTPUT_DIR)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "ذخیره نتایج اسکن", f"{default_dir}/{default_name}",
            "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not filepath:
            return

        try:
            import pandas as pd
            rows = []
            col_count = self.table.columnCount()
            headers = [self.table.horizontalHeaderItem(c).text() for c in range(1, col_count)]

            for r in range(self.table.rowCount()):
                if self.table.item(r, 1) and "برای شروع" in self.table.item(r, 1).text():
                    continue
                row_data = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(1, col_count)]
                rows.append(row_data)

            df = pd.DataFrame(rows, columns=headers)
            if filepath.endswith(".csv"):
                df.to_csv(filepath, index=False, encoding="utf-8-sig")
            else:
                if not filepath.endswith(".xlsx"):
                    filepath += ".xlsx"
                df.to_excel(filepath, index=False, engine="openpyxl")

            self.status_update_signal.emit(f"فایل ذخیره شد: {filepath}")
            QMessageBox.information(self, "موفق", f"گزارش در مسیر زیر ذخیره شد:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره اکسل:\n{e}")

    def closeEvent(self, event):
        """توقف ایمن تایمرها و تردها هنگام خروج از برنامه"""
        if self.auto_scan_timer.isActive():
            self.auto_scan_timer.stop()

        if self.telemetry_worker and self.telemetry_worker.isRunning():
            self.telemetry_worker.stop()

        if self._login_worker and self._login_worker.isRunning():
            self._login_worker.stop()
            self._login_worker.wait(1500)

        if self._broker_connected:
            try:
                self._broker.close_browser()
            except Exception:
                pass

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)

        event.accept()
        logger.info("Application terminated cleanly")