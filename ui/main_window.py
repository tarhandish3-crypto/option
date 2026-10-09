# ui/main_window.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QCheckBox,
    QSpinBox, QLabel, QHeaderView, QMessageBox, QStatusBar,
    QProgressBar, QFrame, QApplication, QSplitter, QFileDialog,
    QMenu, QLineEdit, QDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor

from ui.workers import (
    ScannerWorker,
    BrokerLoginWorker,
    BrokerExecutionWorker,
    TelemetryWorker
)
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.custom_price_dialog import CustomPriceDialog
from ui.settings_dialog import SettingsDialog
from ui.strategy_settings_dialog import StrategySettingsDialog
from ui.settings_manager import settings_manager
from ui.payoff_chart_dialog import PayoffChartDialog
from ui.strategy_inspector import StrategyInspectorWidget
from ui.table_components import StrategyCellDelegate
from ui.table_components import get_flash_manager
from ui.column_filter_dialog import ColumnFilterDialog, FilterType
from ui.table_filter_manager import TableFilterManager
from ui import theme as ui_theme
from alerts.bale_notifier import BaleNotifier

from automation.brokers.Omex_khobregan import get_devtools_snippet_server

import config

logger = logging.getLogger("OptionScanner.UI.MainWindow")


# ═══════════════════════════════════════════════════════════════
# ثابت‌های شخصیت
# ═══════════════════════════════════════════════════════════════

PERSONALITY_HEADERS = ["محافظه‌کار", "متعادل", "پرریسک"]
PERSONALITY_KEYS = ["conservative", "balanced", "aggressive"]

# آستانه‌های رنگ‌بندی برای هر شخصیت
PERSONALITY_THRESHOLDS = {
    "conservative": {"high": 15.0, "medium": 8.0},
    "balanced":     {"high": 20.0, "medium": 10.0},
    "aggressive":   {"high": 25.0, "medium": 12.0},
}

# ─── حداکثر عرض مجاز ستون‌ها (جلوگیری از بزرگ شدن پنجره) ───
_MAX_DYNAMIC_COLUMN_WIDTH = 100


def _build_strategy_key(strategy: Any) -> tuple:
    """
    ساخت کلید یکتای پایدار برای یک استراتژی، مستقل از شیء پایتونی آن.
    """
    legs = getattr(strategy, 'legs', [])
    leg_signature = tuple(
        (
            getattr(leg.contract, 'ticker', ''),
            getattr(leg.contract, 'strike_price', 0),
            getattr(getattr(leg, 'side', None), 'value',
                    str(getattr(leg, 'side', ''))),
            getattr(leg, 'ratio', 1),
        )
        for leg in legs if getattr(leg, 'contract', None)
    )
    return (
        str(getattr(strategy, 'strategy_name', '')),
        str(getattr(strategy, 'underlying_ticker', '')),
        leg_signature,
    )


class NumericTableWidgetItem(QTableWidgetItem):
    """آیتم اختصاصی جدول جهت مرتب‌سازی صحیح عددی بر مبنای UserRole"""

    def __lt__(self, other):
        try:
            val_self = self.data(Qt.ItemDataRole.UserRole)
            val_other = other.data(Qt.ItemDataRole.UserRole)
            if val_self is not None and val_other is not None:
                return float(val_self) < float(val_other)
            return super().__lt__(other)
        except (ValueError, TypeError):
            return super().__lt__(other)


class MainWindow(QMainWindow):
    """
    پنجره اصلی برنامه Option Strategy Scanner.
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

        active_strats = self.config.get("active_strategies", None)
        if active_strats:
            config.ACTIVE_STRATEGIES = active_strats

        self.price_range_config = self.config.get(
            'price_range',
            config.PRICE_RANGE_CONFIG
        )

        self.worker: Optional[ScannerWorker] = None
        self.telemetry_worker: Optional[TelemetryWorker] = None

        self.current_results: List = []
        self.price_steps: List[float] = []
        self._active_quick_filters: set = set()

        self._fixed_column_count = 0
        self._personality_column_start = 0

        self._flash_manager = get_flash_manager(self)
        self._prev_cell_values: Dict[tuple, Dict[int, float]] = {}

        self._theme_mode: ui_theme.ThemeMode = ui_theme.resolve_theme(
            self.config.get("theme", ui_theme.THEME_LIGHT)
        )

        # ─── ذخیره‌ی حداکثر اندازه‌ی مجاز پنجره ───
        self._max_window_width = 0
        self._max_window_height = 0

        self.init_ui()
        self._apply_theme(self.config.get("theme", ui_theme.THEME_LIGHT))

        bale_cfg = settings_manager.get_bale_config()
        self._bale_notifier = BaleNotifier(
            bot_token=bale_cfg.get("bot_token", ""),
            chat_id=bale_cfg.get("chat_id", ""),
        )
        self._bale_notifier.set_callbacks(
            on_success=self._on_bale_send_success,
            on_error=self._on_bale_send_error
        )
        self._bale_enabled = bale_cfg.get("enabled", False)
        self._bale_top_n = bale_cfg.get("top_n", 2)

        self._broker = None
        self._broker_connected = False
        self._login_worker: Optional[BrokerLoginWorker] = None
        self._broker_execution_worker: Optional[BrokerExecutionWorker] = None

        self._init_background_services()
        self.load_settings()
        self._show_empty_state()

        # شروع خودکار DevTools Snippet Server
        self._snippet_server = None
        try:
            self._snippet_server = get_devtools_snippet_server()
            if not self._snippet_server.is_running:
                self._snippet_server.start()
            logger.info("DevTools Snippet server started")
        except Exception as e:
            logger.warning(f"DevTools Snippet server failed: {e}")
            self._snippet_server = None

        self._backend_online = bool(
            self._snippet_server and self._snippet_server.is_running
        )

        self._spread_window = None
        self._position_manager_window = None

        logger.info("Main window initialized cleanly")

    # ═══════════════════════════════════════════════════════════════
    # Layout & Theme
    # ═══════════════════════════════════════════════════════════════

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

        return [fmt.format(val) for val in self.price_steps]

    def _apply_layout_direction(self, layout_dir: str) -> None:
        """تنظیم جهت چیدمان کل پنجره و جدول نتایج"""
        app = QApplication.instance()
        is_ltr = str(layout_dir).lower() in {
            "ltr", "left-to-right", "left", "left to right"}

        if app:
            ui_theme.apply_layout_direction(app, "ltr" if is_ltr else "rtl")

        direction = Qt.LayoutDirection.LeftToRight if is_ltr else Qt.LayoutDirection.RightToLeft
        self.setLayoutDirection(direction)
        self._apply_layout_to_all_widgets(direction)

    def _apply_layout_to_all_widgets(self, direction: Qt.LayoutDirection) -> None:
        is_ltr = (direction == Qt.LayoutDirection.LeftToRight)

        if hasattr(self, "_top_toolbar"):
            self._top_toolbar.setLayoutDirection(direction)
        if hasattr(self, "_filter_toolbar"):
            self._filter_toolbar.setLayoutDirection(direction)
        if hasattr(self, "_bottom_toolbar"):
            self._bottom_toolbar.setLayoutDirection(direction)

        if hasattr(self, "table"):
            self.table.setLayoutDirection(direction)
            header = self.table.horizontalHeader()
            if header:
                header.setLayoutDirection(direction)
                header.setDefaultAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if is_ltr
                    else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            if self.current_results:
                self.populate_table(self.current_results)

    def init_ui(self):
        self.setWindowTitle(
            "Option Strategy Scanner — دستیار هوشمند معاملات اختیار معامله")

        # ═══════════════════════════════════════════════════════════
        # 🆕 قفل کردن حداکثر اندازه‌ی پنجره به اندازه‌ی مانیتور
        # این جلوگیری می‌کند از بزرگ‌تر شدن پنجره پس از اسکن
        # ═══════════════════════════════════════════════════════════
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self._max_window_width = available.width()
            self._max_window_height = available.height()

            # حداکثر = اندازه‌ی مانیتور
            self.setMaximumWidth(self._max_window_width)
            self.setMaximumHeight(self._max_window_height)

            # حداقل = ۹۰٪ عرض و ۷۰٪ ارتفاع مانیتور
            self.setMinimumWidth(int(self._max_window_width * 0.9))
            self.setMinimumHeight(int(self._max_window_height * 0.7))
        else:
            # Fallback اگر مانیتور شناسایی نشد
            self._max_window_width = 1920
            self._max_window_height = 1080
            self.setMaximumWidth(self._max_window_width)
            self.setMaximumHeight(self._max_window_height)

        self.resize(1440, 840)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.showMaximized()

        layout_dir = self.config.get("layout_direction", "راست‌چین (RTL)")
        self._apply_layout_direction(layout_dir)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(10, 8, 10, 8)

        # ۱. نوار ابزار بالا
        self._top_toolbar = self._create_toolbar()
        main_layout.addWidget(self._top_toolbar)

        # ۲. نوار فیلتر و جستجوی سریع
        self._filter_toolbar = self._create_quick_filter_bar()
        main_layout.addWidget(self._filter_toolbar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(14)
        main_layout.addWidget(self.progress_bar)

        self.splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = self._create_table()
        self.splitter.addWidget(self.table)

        self.inspector = StrategyInspectorWidget()
        self.splitter.addWidget(self.inspector)

        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 1)
        self.inspector.setMinimumHeight(150)
        self.inspector.setMaximumHeight(240)
        main_layout.addWidget(self.splitter, stretch=1)

        self._bottom_toolbar = self._create_bottom_toolbar()
        main_layout.addWidget(self._bottom_toolbar)

        self._setup_status_bar()

        # ۳. مدیریت فیلترهای جدول
        self.table_filter_manager = TableFilterManager(self.table)
        self._setup_table_context_menu()

    # ═══════════════════════════════════════════════════════════════
    # 🆕 resizeEvent — مکانیزم دفاعی
    # ═══════════════════════════════════════════════════════════════

    def resizeEvent(self, event):
        """
        مکانیزم دفاعی: اگر پنجره از اندازه‌ی مانیتور بزرگ‌تر شد،
        آن را محدود کن.

        ⚠️ نکته: چون setMaximumWidth/Height اعمال شده، این متد
        به‌ندرت وارد شرط resize می‌شود.
        """
        super().resizeEvent(event)

        if self._max_window_width <= 0 or self._max_window_height <= 0:
            return

        # بررسی اینکه پنجره از حداکثر بزرگ‌تر نشده
        if (self.width() > self._max_window_width or
                self.height() > self._max_window_height):
            # فقط اگر واقعاً بزرگ‌تر شده، resize کن
            new_w = min(self.width(), self._max_window_width)
            new_h = min(self.height(), self._max_window_height)
            # استفاده از singleShot برای جلوگیری از loop
            QTimer.singleShot(0, lambda: self.resize(new_w, new_h))

    # ═══════════════════════════════════════════════════════════════
    # Toolbar
    # ═══════════════════════════════════════════════════════════════

    def _get_uniform_toolbar_btn_style(self) -> str:
        """
        استایل یکسان برای همه‌ی دکمه‌های نوار بالا.

        رنگ سبز هماهنگ با دکمه‌ی «ذخیره اکسل» در نوار پایین.
        فونت 11px برای جا شدن متن کامل.
        """
        mode = self._theme_mode

        if mode == "dark":
            bg = "#238636"
            bg_hover = "#2ea043"
            bg_pressed = "#1a7f37"
            bg_checked = "#1a7f37"
            text = "#ffffff"
            text_hover = "#ffffff"
            text_checked = "#ffffff"
            text_disabled = "#8b949e"
            border = "#238636"
            border_hover = "#3fb950"
        else:
            bg = "#1f883d"
            bg_hover = "#2c974b"
            bg_pressed = "#1a7f37"
            bg_checked = "#1a7f37"
            text = "#ffffff"
            text_hover = "#ffffff"
            text_checked = "#ffffff"
            text_disabled = "#8c959f"
            border = "#1f883d"
            border_hover = "#2c974b"

        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 5px 10px;
                font-weight: bold;
                font-size: 11px;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
                color: {text_hover};
                border-color: {border_hover};
            }}
            QPushButton:pressed {{
                background-color: {bg_pressed};
                color: {text_checked};
                border-color: {bg_pressed};
            }}
            QPushButton:checked {{
                background-color: {bg_checked};
                color: {text_checked};
                border-color: {bg_checked};
            }}
            QPushButton:disabled {{
                background-color: {bg};
                color: {text_disabled};
                border-color: {border};
                opacity: 0.5;
            }}
        """

    def _create_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet(
            ui_theme.get_toolbar_frame_style(self._theme_mode))
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        uniform_btn_style = self._get_uniform_toolbar_btn_style()

        # ── دکمه اسکن بازار ──
        self.btn_refresh = QPushButton("🔄 اسکن بازار")
        self.btn_refresh.setStyleSheet(uniform_btn_style)
        self.btn_refresh.clicked.connect(self.start_scan)
        layout.addWidget(self.btn_refresh)

        layout.addWidget(self._create_separator())

        # ── تکرار خودکار ──
        self.chk_auto_scan = QCheckBox("تکرار خودکار:")
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
        self.lbl_interval_min.setStyleSheet(
            ui_theme.get_interval_label_style(self._theme_mode))
        layout.addWidget(self.lbl_interval_min)

        self.chk_auto_scan.setChecked(True)
        layout.addStretch()

        # ── همه‌ی دکمه‌های نوار بالا با استایل یکسان ──
        # متن‌های کوتاه برای جا شدن کامل
        toolbar_buttons = [
            ("btn_strategy_settings", "🎯 تنظیمات استراتژی",
             self.open_strategy_settings_dialog),
            ("btn_symbol_filter", "🔍 فیلتر نمادها",
             self.open_symbol_filter_dialog),
            ("btn_custom_price", "💰 قیمت دستی",
             self.open_custom_price_dialog),
            ("btn_settings", "⚙️ تنظیمات سیستم",
             self.open_settings_dialog),
            ("btn_vq_refresh", "📊 داده نوسان تاریخی",
             self._open_volatility_refresh_dialog),
            ("btn_spread_analyzer", "📊 تحلیلگر نقطه‌ای",
             self._open_spread_analyzer),
            ("btn_position_manager", "📋 مدیریت موقعیت‌ها",
             self._open_position_manager),
        ]

        for attr_name, label, callback in toolbar_buttons:
            btn = QPushButton(label)
            btn.setStyleSheet(uniform_btn_style)
            btn.clicked.connect(callback)
            setattr(self, attr_name, btn)
            layout.addWidget(btn)

        # Tooltipها
        self.btn_vq_refresh.setToolTip(
            "به‌روزرسانی داده‌ی نوسان تاریخی (VQ)\n"
            "این داده برای امتیازدهی دقیق فرصت‌ها استفاده می‌شود."
        )
        self.btn_spread_analyzer.setToolTip(
            "نمای نقطه‌ای استراتژی‌ها (R30، M30، سربه‌سر، Cobb-Douglas)"
        )
        self.btn_position_manager.setToolTip(
            "مدیریت موقعیت‌های باز، ثبت سفارش‌ها و پیگیری اجرا"
        )
        self.btn_strategy_settings.setToolTip(
            "تنظیمات و فیلترهای هوشمند استراتژی‌ها"
        )

        return toolbar

    def _create_quick_filter_bar(self) -> QFrame:
        """نوار جستجوی سریع و چیپ‌های فیلتر بلادرنگ"""
        frame = QFrame()
        frame.setStyleSheet(ui_theme.get_toolbar_frame_style(self._theme_mode))
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.txt_quick_search = QLineEdit()
        self.txt_quick_search.setPlaceholderText(
            "🔍 جستجوی زنده در نماد، استراتژی یا پایه‌ها...")
        self.txt_quick_search.setFixedWidth(280)
        self.txt_quick_search.textChanged.connect(self._apply_quick_filters)
        layout.addWidget(self.txt_quick_search)

        layout.addWidget(self._create_separator())

        self.chip_arbitrage = QPushButton("🔒 فقط بدون ریسک (آربیتراژ)")
        self.chip_arbitrage.clicked.connect(
            lambda: self._toggle_chip("arbitrage", self.chip_arbitrage))
        layout.addWidget(self.chip_arbitrage)

        self.chip_dte = QPushButton("📅 سررسید زیر ۳۰ روز")
        self.chip_dte.clicked.connect(
            lambda: self._toggle_chip("dte_30", self.chip_dte))
        layout.addWidget(self.chip_dte)

        self.chip_roi = QPushButton("🚀 بازده بالای ۱۵٪")
        self.chip_roi.clicked.connect(
            lambda: self._toggle_chip("roi_15", self.chip_roi))
        layout.addWidget(self.chip_roi)

        layout.addStretch()
        self._refresh_chips_style()
        return frame

    def _toggle_chip(self, key: str, btn: QPushButton):
        if key in self._active_quick_filters:
            self._active_quick_filters.remove(key)
        else:
            self._active_quick_filters.add(key)
        self._refresh_chips_style()
        self._apply_quick_filters()

    def _refresh_chips_style(self):
        for key, btn in (
            ("arbitrage", self.chip_arbitrage),
            ("dte_30", self.chip_dte),
            ("roi_15", self.chip_roi),
        ):
            active = key in self._active_quick_filters
            btn.setStyleSheet(ui_theme.get_filter_chip_style(
                active, self._theme_mode))

    def _apply_quick_filters(self):
        query = self.txt_quick_search.text().strip().lower()
        filtered = []
        for strat in self.current_results:
            name = str(getattr(strat, 'strategy_name', '')).lower()
            ticker = str(getattr(strat, 'underlying_ticker', '')).lower()

            if query and (query not in name and query not in ticker):
                continue

            if "arbitrage" in self._active_quick_filters:
                if "conversion" not in name and "box" not in name and "آربیتراژ" not in name:
                    continue

            if "dte_30" in self._active_quick_filters:
                dte = int(getattr(strat, 'days_to_maturity', 0))
                if dte > 30:
                    continue

            if "roi_15" in self._active_quick_filters:
                roi = float(getattr(strat, 'return_on_margin', 0.0) or 0.0)
                if roi < 15.0:
                    continue

            filtered.append(strat)

        self.populate_table(filtered)

    def _create_separator(self) -> QFrame:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setMaximumWidth(2)
        separator.setStyleSheet(ui_theme.get_separator_style(self._theme_mode))
        return separator

    # ═══════════════════════════════════════════════════════════════
    # Table
    # ═══════════════════════════════════════════════════════════════

    def _create_table(self) -> QTableWidget:
        table = QTableWidget()

        fixed_headers = ["✓", "Rank", "Strategy", "Positions",
                         "DTE / سررسید", "Ticker", "Breakeven"]
        dynamic_price_headers = self._generate_price_step_columns()
        personality_headers = list(PERSONALITY_HEADERS)

        all_headers = fixed_headers + dynamic_price_headers + personality_headers

        table.setColumnCount(len(all_headers))
        table.setHorizontalHeaderLabels(all_headers)

        table.setItemDelegate(StrategyCellDelegate(table))

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSortIndicatorShown(True)

        # عرض ستون‌های ثابت
        table.setColumnWidth(0, 35)
        table.setColumnWidth(1, 50)
        table.setColumnWidth(2, 130)
        table.setColumnWidth(3, 220)
        table.setColumnWidth(4, 110)
        table.setColumnWidth(5, 85)
        table.setColumnWidth(6, 110)

        # ─── ستون‌های P&L: Interactive (نه ResizeToContents) ───
        price_start = len(fixed_headers)
        price_end = price_start + len(dynamic_price_headers)
        for col_idx in range(price_start, price_end):
            header.setSectionResizeMode(
                col_idx, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(col_idx, 85)

        # ─── ستون‌های شخصیت: Interactive ───
        personality_start = price_end
        personality_end = len(all_headers)
        for col_idx in range(personality_start, personality_end):
            header.setSectionResizeMode(
                col_idx, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(col_idx, 95)

        # ذخیره‌ی شماره‌ی ستون‌ها
        self._fixed_column_count = len(fixed_headers)
        self._personality_column_start = personality_start

        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # ─── 🆕 scroll افقی و عمودی فعال ───
        table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(
            QTableWidget.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(
            QTableWidget.ScrollMode.ScrollPerPixel)

        # ─── 🆕 جدول نباید عرض ذاتی داشته باشد ───
        table.setMinimumWidth(0)
        table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)

        table.itemChanged.connect(self._on_checkbox_changed)
        table.itemClicked.connect(self._on_table_row_clicked)
        table.itemDoubleClicked.connect(self._on_table_row_double_clicked)

        return table

    def _on_table_row_clicked(self, item: QTableWidgetItem):
        row = item.row()
        check_item = self.table.item(row, 0)
        if check_item:
            strategy = check_item.data(Qt.ItemDataRole.UserRole + 1)
            if strategy:
                self.inspector.load_strategy(strategy)

    def _on_table_row_double_clicked(self, item: QTableWidgetItem):
        self._open_payoff_chart_for_row(item.row())

    def _on_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        if row < 0 or row >= self.table.rowCount():
            return

        check_item = self.table.item(row, 0)
        strategy = check_item.data(
            Qt.ItemDataRole.UserRole + 1) if check_item else None
        if not strategy and row < len(self.current_results):
            strategy = self.current_results[row]

        if not strategy:
            return

        menu = QMenu(self.table)
        action_chart = menu.addAction("📊 ترسیم نمودار سود و زیان (Payoff)")
        action_chart.triggered.connect(
            lambda: self._open_payoff_chart_for_row(row))

        menu.addSeparator()
        action_broker = menu.addAction("🚀 ارسال مستقیم به کارگزاری")
        action_broker.triggered.connect(
            lambda: self._send_to_broker_from_row(row))

        action_bale = menu.addAction("📱 ارسال به پیام‌رسان بله")
        action_bale.triggered.connect(lambda: self._send_to_bale_from_row(row))

        menu.addSeparator()
        action_copy = menu.addAction("📋 کپی مشخصات استراتژی")
        action_copy.triggered.connect(
            lambda: self._copy_strategy_to_clipboard(strategy))

        menu.exec(self.table.mapToGlobal(pos))

    def _send_to_broker_from_row(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return
        check_item = self.table.item(row, 0)
        if check_item and check_item.checkState() != Qt.CheckState.Checked:
            check_item.setCheckState(Qt.CheckState.Checked)
        self.send_selected_to_broker()

    def _send_to_bale_from_row(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return
        check_item = self.table.item(row, 0)
        strategy = check_item.data(
            Qt.ItemDataRole.UserRole + 1) if check_item else None
        if strategy:
            self._bale_notifier.send_scan_results([strategy], top_n=1)
            self.status_update_signal.emit(
                f"📱 استراتژی {getattr(strategy, 'strategy_name', '')} به بله ارسال شد")

    def _copy_strategy_to_clipboard(self, strategy: Any):
        strat_name = str(getattr(strategy, 'strategy_name', 'استراتژی'))
        ticker = str(getattr(strategy, 'underlying_ticker', '-'))
        legs = getattr(strategy, 'legs', [])
        parts = []
        for leg in legs:
            contract = getattr(leg, 'contract', None)
            t = contract.ticker if contract else 'سهام'
            s = "خرید" if str(getattr(leg, 'side', '')).upper() in (
                "BUY", "SIDE.BUY") else "فروش"
            r = getattr(leg, 'ratio', 1)
            parts.append(f"{t} ({r}x{s})")
        positions_str = " | ".join(parts)

        scores = getattr(strategy, 'scores', {}) or {}
        score_lines = []
        for key, label in zip(PERSONALITY_KEYS, PERSONALITY_HEADERS):
            val = scores.get(key, -1.0)
            if val > 0:
                score_lines.append(f"  • {label}: {val:.2f}")
            else:
                score_lines.append(f"  • {label}: —")
        scores_str = "\n".join(score_lines)

        text = (
            f"🎯 استراتژی: {strat_name}\n"
            f"📌 نماد پایه: {ticker}\n"
            f"📋 پایه‌ها: {positions_str}\n"
            f"⭐ امتیازها:\n{scores_str}"
        )
        QApplication.clipboard().setText(text)
        self.status_update_signal.emit(
            "📋 اطلاعات استراتژی در کلیپ‌بورد کپی شد")

    def _open_payoff_chart_for_row(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        check_item = self.table.item(row, 0)
        strategy = check_item.data(
            Qt.ItemDataRole.UserRole + 1) if check_item else None
        if not strategy and row < len(self.current_results):
            strategy = self.current_results[row]

        if not strategy:
            QMessageBox.warning(
                self, "خطا", "داده‌های استراتژی برای این سطر یافت نشد.")
            return

        try:
            dialog = PayoffChartDialog(self)
            dialog.load_strategy(strategy, self._theme_mode)
            dialog.exec()
        except Exception as e:
            logger.error(f"Error opening payoff chart: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در باز کردن نمودار:\n{e}")

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

    # ═══════════════════════════════════════════════════════════════
    # Bottom Toolbar
    # ═══════════════════════════════════════════════════════════════

    def _create_bottom_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet(
            ui_theme.get_toolbar_frame_style(self._theme_mode))
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_stats = QLabel("📊 ۰ استراتژی یافت شد")
        layout.addWidget(self.lbl_stats)

        layout.addStretch()

        self.btn_broker_connect = QPushButton("🏦 اتصال به کارگزاری")
        self.btn_broker_connect.clicked.connect(self.connect_to_broker)
        self.btn_broker_connect.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="secondary"))
        layout.addWidget(self.btn_broker_connect)

        self.btn_send_broker = QPushButton("⚡ ارسال به کارگزاری")
        self.btn_send_broker.clicked.connect(self.send_selected_to_broker)
        self.btn_send_broker.setEnabled(False)
        self.btn_send_broker.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="secondary"))
        layout.addWidget(self.btn_send_broker)

        self.btn_send_bale = QPushButton("📱 ارسال به بله")
        self.btn_send_bale.clicked.connect(self.send_selected_to_bale)
        self.btn_send_bale.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="secondary"))
        layout.addWidget(self.btn_send_bale)

        self.btn_export_excel = QPushButton("📊 ذخیره اکسل")
        self.btn_export_excel.clicked.connect(self.export_results_to_excel)
        self.btn_export_excel.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="success"))
        layout.addWidget(self.btn_export_excel)

        self.btn_clear_results = QPushButton("🗑️ پاک کردن")
        self.btn_clear_results.clicked.connect(self.clear_results)
        self.btn_clear_results.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="danger"))
        layout.addWidget(self.btn_clear_results)

        return toolbar

    # ═══════════════════════════════════════════════════════════════
    # Settings / Scan lifecycle
    # ═══════════════════════════════════════════════════════════════

    def load_settings(self):
        auto_scan_enabled = self.config.get('auto_scan_enabled', True)
        self.chk_auto_scan.setChecked(auto_scan_enabled)

    def start_scan(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker.disconnect()
            self.worker.deleteLater()
            self.worker = None

        self._flash_manager.clear()

        self._set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_update_signal.emit(
            "🔄 در حال دریافت تابلوی بازار و غربالگری استراتژی‌ها...")

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

        # ─── 🆕 پس از پایان اسکن، مطمئن شو پنجره بزرگ نشده ───
        QTimer.singleShot(50, self._enforce_window_size)

    def _enforce_window_size(self):
        """
        اجبار پنجره به اندازه‌ی مانیتور.
        """
        if self._max_window_width <= 0 or self._max_window_height <= 0:
            return

        new_w = min(self.width(), self._max_window_width)
        new_h = min(self.height(), self._max_window_height)

        if new_w != self.width() or new_h != self.height():
            logger.debug(
                f"Enforcing window size: {self.width()}x{self.height()} "
                f"→ {new_w}x{new_h}"
            )
            self.resize(new_w, new_h)

    def on_scan_finished(self, results):
        all_results = results or []

        excluded = set(settings_manager.get_excluded_symbols())
        if excluded:
            all_results = [
                opp for opp in all_results
                if getattr(opp, 'underlying_ticker', '') not in excluded
            ]

        active_strategies = settings_manager.get_active_strategies()
        if active_strategies:
            all_results = [
                opp for opp in all_results
                if getattr(opp, 'strategy_name', '') in active_strategies
            ]
            logger.info(
                f"Filtered by active strategies: {len(active_strategies)} strategies, {len(all_results)} results")

        self.current_results = all_results
        count = len(self.current_results)
        self.status_update_signal.emit(
            f"✅ اسکن پایان یافت — {count} استراتژی بهینه یافت شد")
        self.populate_table(self.current_results)
        self._update_stats()

        if self.current_results:
            self.inspector.load_strategy(self.current_results[0])

        self._send_bale_alert(self.current_results)

        import gc
        gc.collect()

    def on_scan_failed(self, error_msg):
        self.status_update_signal.emit(f"❌ خطا در اسکن: {error_msg}")

        # ─── خطای VQ ───
        if "VQ_MISSING" in error_msg or "Historical_Volatility" in error_msg:
            QMessageBox.critical(
                self,
                "فایل Historical_Volatility.xlsx یافت نشد",
                "❌ فایل Historical_Volatility.xlsx یافت نشد!\n\n"
                "برای امتیازدهی فرصت‌ها، ابتدا باید داده‌ی نوسان تاریخی محاسبه شود.\n\n"
                "📌 راه‌حل:\n"
                "   ۱. دکمه‌ی «📊 داده نوسان تاریخی» را بزنید\n"
                "   ۲. در پنجره باز شده، دکمه‌ی «🔄 محاسبه نوسان تاریخی» را بزنید\n"
                "   ۳. پس از ۳۰-۶۰ ثانیه، فایل ساخته می‌شود\n"
                "   ۴. مجدداً اسکن کنید\n\n"
                "⚠️ بدون این فایل، امتیازدهی امکان‌پذیر نیست."
            )
            return

        # ─── خطای عادی ───
        QMessageBox.critical(
            self,
            "خطا در اسکن",
            f"خطایی رخ داد:\n\n{error_msg}\n\nلطفاً ارتباط شبکه یا تنظیمات را بررسی کنید."
        )

    def on_progress_updated(self, percent: int, status: str):
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}% - {status}")

    # ═══════════════════════════════════════════════════════════════
    # Populate table
    # ═══════════════════════════════════════════════════════════════

    def populate_table(self, results: List):
        flash_mgr = get_flash_manager()
        flash_mgr.clear()

        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        if not results:
            self._show_empty_state()
            self._prev_cell_values = {}
            self._update_stats()
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            return

        new_cell_values: Dict[tuple, Dict[int, float]] = {}

        row_idx = 0
        for strat in results:
            self.table.insertRow(row_idx)
            self._populate_row(row_idx, strat, new_cell_values)
            row_idx += 1

        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)

        # ─── 🆕 محدود کردن عرض ستون‌ها ───
        # به جای resizeColumnToContents آزاد، حداکثر عرض را محدود می‌کنیم
        for col_idx in range(self._fixed_column_count, self.table.columnCount()):
            self.table.resizeColumnToContents(col_idx)
            if self.table.columnWidth(col_idx) > _MAX_DYNAMIC_COLUMN_WIDTH:
                self.table.setColumnWidth(
                    col_idx, _MAX_DYNAMIC_COLUMN_WIDTH)

        self._prev_cell_values = new_cell_values
        self._update_heatmap_scale(new_cell_values)

        if self.table_filter_manager:
            self.table_filter_manager.apply_filters()

        self._update_stats()

        # ─── 🆕 پس از populate، اندازه‌ی پنجره را چک کن ───
        QTimer.singleShot(0, self._enforce_window_size)

    def _update_heatmap_scale(self, cell_values: Dict[tuple, Dict[int, float]]) -> None:
        delegate = self.table.itemDelegate()
        if not hasattr(delegate, "set_heatmap_scale"):
            return
        max_abs = 0.0
        for col_map in cell_values.values():
            for v in col_map.values():
                if v is not None:
                    max_abs = max(max_abs, abs(v))
        if max_abs > 0:
            delegate.set_heatmap_scale(max_abs)

    def _populate_row(self, row: int, strategy: Any,
                      cell_values_out: Optional[Dict[tuple, Dict[int, float]]] = None):
        # ── ✓ ──
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                            Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Unchecked)
        check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        check_item.setData(Qt.ItemDataRole.UserRole + 1, strategy)
        self.table.setItem(row, 0, check_item)

        # ── Rank ──
        rank_val = getattr(strategy, 'rank', row + 1)
        rank_item = NumericTableWidgetItem(str(rank_val))
        rank_item.setData(Qt.ItemDataRole.UserRole, int(rank_val))
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, rank_item)

        # ── Strategy ──
        strat_name = str(getattr(strategy, 'strategy_name', 'N/A'))
        item_strat = QTableWidgetItem(strat_name)
        font = item_strat.font()
        font.setBold(True)
        item_strat.setFont(font)

        underlying_ticker = str(getattr(strategy, 'underlying_ticker', 'N/A'))
        custom_prices = settings_manager.get_custom_prices()
        if underlying_ticker in custom_prices:
            item_strat.setText(f"💰 {strat_name}")
            item_strat.setForeground(QBrush(QColor("#f0883e")))

        self.table.setItem(row, 2, item_strat)

        # ── Positions ──
        legs = getattr(strategy, 'legs', [])
        if legs:
            positions_parts = []
            for leg in legs:
                ticker = leg.contract.ticker if leg.contract else 'سهام'
                side = "خرید" if str(getattr(leg, 'side', '')).upper() in (
                    "BUY", "SIDE.BUY") else "فروش"
                ratio = getattr(leg, 'ratio', 1)
                positions_parts.append(f"{ticker} ({ratio}x{side})")
            positions = " | ".join(positions_parts)
        else:
            positions = 'N/A'
        self._set_item(row, 3, positions)

        # ── DTE ──
        dte_val = int(getattr(strategy, 'days_to_maturity', 0))
        dte_item = NumericTableWidgetItem(f"{dte_val}")
        dte_item.setData(Qt.ItemDataRole.UserRole, dte_val)
        dte_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, dte_item)

        # ── Ticker ──
        ticker = str(getattr(strategy, 'underlying_ticker', 'N/A'))
        self._set_item(row, 5, ticker, bold=True)

        # ── Breakeven ──
        be_list = getattr(strategy, 'break_even_points', [])
        if be_list:
            be_str = ", ".join(ui_theme.format_rial(p) for p in be_list)
        else:
            be_str = '0.0'
        self._set_item(row, 6, be_str)

        # ── P&L steps ──
        pnl_data = getattr(strategy, 'returns_monthly_pct', None)
        if pnl_data is None:
            pnl_data = []
        elif hasattr(pnl_data, 'tolist'):
            pnl_data = pnl_data.tolist()
        else:
            pnl_data = list(pnl_data)

        fixed_col_offset = 7
        pos_color, neg_color = ui_theme.get_pnl_colors(self._theme_mode)

        strategy_key = _build_strategy_key(strategy)
        prev_values = self._prev_cell_values.get(strategy_key)
        current_values: Dict[int, float] = {}

        for i, step_pct in enumerate(self.price_steps):
            col_idx = fixed_col_offset + i
            val = pnl_data[i] if i < len(pnl_data) else None

            if val is not None:
                try:
                    num_val = float(val)
                    item_pnl = NumericTableWidgetItem(
                        ui_theme.format_rial(num_val))
                    item_pnl.setData(Qt.ItemDataRole.UserRole, num_val)
                    item_pnl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    if num_val > 0:
                        item_pnl.setForeground(QBrush(pos_color))
                    elif num_val < 0:
                        item_pnl.setForeground(QBrush(neg_color))

                    self.table.setItem(row, col_idx, item_pnl)
                    current_values[col_idx] = num_val

                    if prev_values is not None:
                        old_val = prev_values.get(col_idx)
                        if old_val is not None and round(old_val) != round(num_val):
                            direction = "up" if num_val > old_val else "down"
                            self._flash_manager.flash(item_pnl, direction)
                except (ValueError, TypeError):
                    self._set_item(row, col_idx, str(val))
            else:
                self._set_item(row, col_idx, "-")

        # ── سه ستون امتیاز شخصیتی ──
        scores = getattr(strategy, 'scores', None) or {}
        p_start = self._personality_column_start

        for idx, key in enumerate(PERSONALITY_KEYS):
            col_idx = p_start + idx
            score_val = scores.get(key, -1.0)

            if score_val < 0:
                item = QTableWidgetItem("—")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QBrush(QColor("#8c9bae")))
            else:
                item = NumericTableWidgetItem(f"{score_val:.2f}")
                item.setData(Qt.ItemDataRole.UserRole, score_val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                thresholds = PERSONALITY_THRESHOLDS.get(
                    key, {"high": 20.0, "medium": 10.0})
                if score_val >= thresholds["high"]:
                    item.setForeground(QBrush(QColor("#3fb950")))
                elif score_val >= thresholds["medium"]:
                    item.setForeground(QBrush(QColor("#d29922")))
                elif score_val >= 1.0:
                    item.setForeground(QBrush(QColor("#8c9bae")))
                else:
                    item.setForeground(QBrush(QColor("#f85149")))

            self.table.setItem(row, col_idx, item)

        if cell_values_out is not None:
            cell_values_out[strategy_key] = current_values

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

        empty_item = QTableWidgetItem(
            "🔍 برای شروع اسکن بازار، دکمه '🔄 اسکن بازار' را بزنید")
        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_item.setForeground(
            QBrush(ui_theme.get_empty_state_color(self._theme_mode)))
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
            self.lbl_stats.setText(
                f"📊 {total} استراتژی یافت شد | ✅ {checked} انتخاب‌شده")
        else:
            self.lbl_stats.setText(f"📊 {total} استراتژی یافت شد")

    def _set_controls_enabled(self, enabled: bool):
        """فعال/غیرفعال کردن دکمه‌ها در زمان اسکن."""
        for attr_name in (
            "btn_refresh",
            "chk_auto_scan",
            "btn_strategy_settings",
            "btn_symbol_filter",
            "btn_custom_price",
            "btn_settings",
            "btn_vq_refresh",
            "btn_spread_analyzer",
            "btn_position_manager",
        ):
            if hasattr(self, attr_name):
                getattr(self, attr_name).setEnabled(enabled)

        if hasattr(self, "spin_interval"):
            self.spin_interval.setEnabled(
                enabled and self.chk_auto_scan.isChecked())

    # ═══════════════════════════════════════════════════════════════
    # Dialogs
    # ═══════════════════════════════════════════════════════════════

    def open_strategy_settings_dialog(self):
        dialog = StrategySettingsDialog(self)
        dialog.strategies_updated.connect(self._on_active_strategies_updated)
        dialog.exec()

    def _on_active_strategies_updated(self, active_strategies: list):
        count = len(active_strategies)
        self.status_update_signal.emit(
            f"🎯 تعداد {count} استراتژی با فیلترهای بازه به‌روزرسانی و فعال شدند.")
        logger.info(f"Updated active strategies: {active_strategies}")

    def open_symbol_filter_dialog(self):
        try:
            available = list(config.SYMBOL_INFO.keys()) if hasattr(
                config, 'SYMBOL_INFO') else []
            dialog = SymbolFilterDialog(
                available_symbols=available, parent=self)
            dialog.symbols_updated.connect(self._on_excluded_symbols_changed)
            dialog.exec()
        except Exception as e:
            logger.warning(f"Error in SymbolFilterDialog: {e}")

    def _on_excluded_symbols_changed(self, excluded: list):
        self.config['excluded_symbols'] = excluded
        count = len(excluded)
        self.status_update_signal.emit(
            f"🚫 {count} نماد استثنا شد" if count else "✅ همه نمادها فعالند")

    def open_custom_price_dialog(self):
        try:
            available_symbols = list(config.SYMBOL_INFO.keys()) if hasattr(
                config, 'SYMBOL_INFO') else []
        except Exception:
            available_symbols = []

        dialog = CustomPriceDialog(
            option_symbols=available_symbols, parent=self)
        dialog.prices_updated.connect(self._on_custom_prices_updated)
        dialog.exec()

    def _on_custom_prices_updated(self, prices: dict):
        count = len(prices)
        self.status_update_signal.emit(
            f"💰 {count} قیمت دستی برای نمادها تنظیم شد")
        logger.info(f"Custom prices updated: {count} symbols")

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
        self._bale_top_n = new_settings.get("bale_top_n", 2)
        self._bale_notifier.update_config(
            bot_token=new_settings.get("bale_bot_token", ""),
            chat_id=new_settings.get("bale_chat_id", ""),
        )

        new_price_range = new_settings.get("price_range")
        if new_price_range:
            config.PRICE_RANGE_CONFIG.update(new_price_range)

        self._apply_theme(new_settings.get("theme", ui_theme.THEME_LIGHT))
        self._apply_layout_direction(new_settings.get(
            "layout_direction", "راست‌چین (RTL)"))

        self.price_range_config = self.config.get(
            'price_range',
            config.PRICE_RANGE_CONFIG
        )
        self._rebuild_price_columns()

    def _open_volatility_refresh_dialog(self):
        """
        باز کردن پنجره‌ی به‌روزرسانی داده نوسان تاریخی (VQ).
        """
        try:
            from ui.volatility_refresh_dialog import VolatilityRefreshDialog
        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"بارگذاری پنجره به‌روزرسانی VQ ناموفق بود:\n{e}"
            )
            logger.error(f"VolatilityRefreshDialog import failed: {e}")
            return

        try:
            dialog = VolatilityRefreshDialog(parent=self)
            dialog.exec()
            logger.info("VolatilityRefreshDialog closed")
        except Exception as e:
            logger.error(
                f"Failed to open VolatilityRefreshDialog: {e}",
                exc_info=True
            )
            QMessageBox.critical(
                self, "خطا",
                f"ایجاد پنجره به‌روزرسانی VQ ناموفق بود:\n{e}"
            )

    # ═══════════════════════════════════════════════════════════════
    # Theme
    # ═══════════════════════════════════════════════════════════════

    def _apply_theme(self, theme_setting: str) -> None:
        self._theme_mode = ui_theme.resolve_theme(theme_setting)
        app = QApplication.instance()
        if app is not None:
            ui_theme.apply_app_theme(app, theme_setting)
        self._refresh_widget_styles()
        self.inspector.set_theme_mode(self._theme_mode)
        self._refresh_chips_style()
        if self.current_results:
            self.populate_table(self.current_results)
        elif self.table.rowCount() == 1:
            self._show_empty_state()

    def _rebuild_price_columns(self):
        """بازسازی ستون‌های قیمت و شخصیت پس از تغییر تنظیمات بازه قیمت"""
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        fixed_headers = ["✓", "Rank", "Strategy", "Positions",
                         "DTE / سررسید", "Ticker", "Breakeven"]
        dynamic_headers = self._generate_price_step_columns()
        personality_headers = list(PERSONALITY_HEADERS)
        all_headers = fixed_headers + dynamic_headers + personality_headers

        header = self.table.horizontalHeader()
        current_col_count = self.table.columnCount()
        new_col_count = len(all_headers)

        if new_col_count != current_col_count:
            self.table.setColumnCount(new_col_count)
            if new_col_count > current_col_count:
                for col_idx in range(current_col_count, new_col_count):
                    header.setSectionResizeMode(
                        col_idx, QHeaderView.ResizeMode.Interactive)
                    self.table.setColumnWidth(col_idx, 90)
            else:
                for col_idx in range(current_col_count - 1, new_col_count - 1, -1):
                    header.setSectionResizeMode(
                        col_idx, QHeaderView.ResizeMode.Interactive)

        self.table.setHorizontalHeaderLabels(all_headers)

        # ستون‌های P&L — Interactive
        price_start = len(fixed_headers)
        price_end = price_start + len(dynamic_headers)
        for col_idx in range(price_start, price_end):
            header.setSectionResizeMode(
                col_idx, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col_idx, 85)

        # ستون‌های شخصیت — Interactive
        personality_start = price_end
        for col_idx in range(personality_start, new_col_count):
            header.setSectionResizeMode(
                col_idx, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col_idx, 95)

        self._fixed_column_count = len(fixed_headers)
        self._personality_column_start = personality_start

        # عرض ستون‌های ثابت
        self.table.setColumnWidth(0, 35)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 220)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 85)
        self.table.setColumnWidth(6, 110)

        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)

        if new_col_count != current_col_count:
            self.current_results = []
            self._prev_cell_values = {}
            self.inspector.clear_inspector()
            self._show_empty_state()
            self._update_stats()
        elif self.current_results:
            self.populate_table(self.current_results)
        elif self.table.rowCount() < 1:
            self._show_empty_state()

    def _refresh_widget_styles(self) -> None:
        mode = self._theme_mode

        if hasattr(self, "_top_toolbar"):
            self._top_toolbar.setStyleSheet(
                ui_theme.get_toolbar_frame_style(mode))
        if hasattr(self, "_filter_toolbar"):
            self._filter_toolbar.setStyleSheet(
                ui_theme.get_toolbar_frame_style(mode))
        if hasattr(self, "_bottom_toolbar"):
            self._bottom_toolbar.setStyleSheet(
                ui_theme.get_toolbar_frame_style(mode))
        if hasattr(self, "lbl_interval_min"):
            self.lbl_interval_min.setStyleSheet(
                ui_theme.get_interval_label_style(mode))

        # ── دکمه‌های نوار بالا: استایل یکسان سبز ──
        uniform_style = self._get_uniform_toolbar_btn_style()
        for attr_name in (
            "btn_refresh",
            "btn_strategy_settings",
            "btn_symbol_filter",
            "btn_custom_price",
            "btn_settings",
            "btn_vq_refresh",
            "btn_spread_analyzer",
            "btn_position_manager",
        ):
            if hasattr(self, attr_name):
                getattr(self, attr_name).setStyleSheet(uniform_style)

        # ── دکمه‌های نوار پایین: استایل نقش‌محور ──
        if hasattr(self, "btn_broker_connect"):
            self.btn_broker_connect.setStyleSheet(
                ui_theme.get_button_style(mode, role="secondary"))
        if hasattr(self, "btn_send_broker"):
            self.btn_send_broker.setStyleSheet(
                ui_theme.get_button_style(mode, role="secondary"))
        if hasattr(self, "btn_send_bale"):
            self.btn_send_bale.setStyleSheet(
                ui_theme.get_button_style(mode, role="secondary"))
        if hasattr(self, "btn_export_excel"):
            self.btn_export_excel.setStyleSheet(
                ui_theme.get_button_style(mode, role="success"))
        if hasattr(self, "btn_clear_results"):
            self.btn_clear_results.setStyleSheet(
                ui_theme.get_button_style(mode, role="danger"))

    # ═══════════════════════════════════════════════════════════════
    # Status bar
    # ═══════════════════════════════════════════════════════════════

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_broker_badge = QLabel("○ کارگزاری: قطع")
        self.lbl_broker_badge.setStyleSheet(
            "color: #8c9bae; margin-left: 10px;")

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
        self.status_bar.showMessage(
            "✅ آماده به کار — برای شروع، دکمه '🔄 اسکن بازار' را بزنید")

    def _init_background_services(self):
        self.telemetry_worker = TelemetryWorker(
            host="tsetmc.com", interval_sec=2.5, parent=self)
        self.telemetry_worker.telemetry_updated.connect(
            self._on_telemetry_updated)
        self.telemetry_worker.start()

    @Slot(dict)
    def _on_telemetry_updated(self, data: dict):
        ping = data.get("ping_ms", -1)
        ram = data.get("ram_usage_mb", 0.0)

        if ping >= 0:
            self.lbl_ping.setText(f"🌐 پینگ TSETMC: {ping}ms")
            self.lbl_ping.setStyleSheet("color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_ping.setText("🌐 پینگ TSETMC: قطع")
            self.lbl_ping.setStyleSheet("color: #f85149; margin-left: 10px;")

        self.lbl_ram.setText(f"💾 RAM: {ram:.1f} MB")

        if self._bale_enabled and self._bale_notifier.is_configured:
            self.lbl_bale_badge.setText("● بله: آنلاین")
            self.lbl_bale_badge.setStyleSheet(
                "color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_bale_badge.setText("○ بله: غیرفعال")
            self.lbl_bale_badge.setStyleSheet(
                "color: #8c9bae; margin-left: 10px;")

        if self._broker_connected:
            self.lbl_broker_badge.setText("● کارگزاری: متصل")
            self.lbl_broker_badge.setStyleSheet(
                "color: #3fb950; margin-left: 10px;")
        else:
            self.lbl_broker_badge.setText("○ کارگزاری: قطع")
            self.lbl_broker_badge.setStyleSheet(
                "color: #8c9bae; margin-left: 10px;")

    # ═══════════════════════════════════════════════════════════════
    # Broker
    # ═══════════════════════════════════════════════════════════════

    def send_selected_to_broker(self):
        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if not checked_rows:
            QMessageBox.warning(
                self, "هشدار", "لطفاً یک استراتژی را از جدول با تیک انتخاب کنید.")
            return

        if not self._broker_connected or not self._broker:
            QMessageBox.warning(
                self, "عدم اتصال", "ابتدا با دکمه «🏦 اتصال به کارگزاری» وارد شوید.")
            return

        if self._broker_execution_worker and self._broker_execution_worker.isRunning():
            QMessageBox.information(
                self, "در حال اجرا",
                "یک عملیات کارگزاری در حال انجام است. لطفاً تا پایان عملیات فعلی صبر کنید."
            )
            return

        row = checked_rows[0]
        positions_item = self.table.item(row, 3)
        positions_text = positions_item.text() if positions_item else ""

        if not positions_text.strip():
            QMessageBox.warning(
                self, "اطلاعات ناقص", "اطلاعات موقعیت‌های استراتژی قابل استخراج نیست.")
            return

        reply = QMessageBox.question(
            self, "تأیید ارسال به کارگزاری",
            f"ارسال استراتژی زیر به سامانه کارگزاری:\n\n{positions_text}\n\nادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_send_broker.setEnabled(False)
        self.status_update_signal.emit(
            "⏳ در حال ارسال سفارش به هسته معاملاتی کارگزاری...")

        self._broker_execution_worker = BrokerExecutionWorker(
            broker=self._broker,
            positions_text=positions_text,
            parent=self,
        )
        self._broker_execution_worker.status_changed.connect(
            self.status_update_signal.emit)
        self._broker_execution_worker.execution_finished.connect(
            self._on_broker_execution_finished)
        self._broker_execution_worker.finished.connect(
            self._on_broker_execution_thread_finished)
        self._broker_execution_worker.start()

    @Slot(bool, str)
    def _on_broker_execution_finished(self, success: bool, message: str) -> None:
        if success:
            self.status_update_signal.emit(f"✅ {message}")
            QMessageBox.information(self, "موفق", message)
        else:
            self.status_update_signal.emit(f"❌ {message}")
            QMessageBox.critical(self, "خطا در کارگزاری", message)

    @Slot()
    def _on_broker_execution_thread_finished(self) -> None:
        logger.info("Broker execution worker finished")
        self.btn_send_broker.setEnabled(self._broker_connected)
        worker = self._broker_execution_worker
        if worker is not None:
            worker.deleteLater()
        self._broker_execution_worker = None

    # ═══════════════════════════════════════════════════════════════
    # Bale
    # ═══════════════════════════════════════════════════════════════

    def send_selected_to_bale(self):
        checked_rows = [
            r for r in range(self.table.rowCount())
            if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if not checked_rows:
            QMessageBox.warning(
                self, "هشدار", "لطفاً یک سطر را با تیک انتخاب کنید.")
            return

        selected_opps = [
            self.table.item(r, 0).data(Qt.ItemDataRole.UserRole + 1)
            for r in checked_rows if self.table.item(r, 0)
        ]
        self._bale_notifier.send_scan_results(
            selected_opps, top_n=len(selected_opps))
        self.status_update_signal.emit(
            f"📱 ارسال {len(selected_opps)} استراتژی به بله انجام شد")

    def _on_bale_send_success(self, opportunities, top_n):
        strat_names = ", ".join(
            getattr(o, 'strategy_name', 'استراتژی') for o in opportunities[:3]
        )
        if len(opportunities) > 3:
            strat_names += f" و {len(opportunities) - 3} مورد دیگر"
        self.status_update_signal.emit(
            f"✅ {len(opportunities)} استراتژی با موفقیت به بله ارسال شد: {strat_names}")

    def _on_bale_send_error(self, error_message):
        self.status_update_signal.emit(f"❌ خطا در ارسال به بله: {error_message}")

    def _send_bale_alert(self, opportunities: List) -> None:
        if not self._bale_enabled or not self._bale_notifier.is_configured:
            return
        self._bale_notifier.send_scan_results(
            opportunities, top_n=self._bale_top_n)

    # ═══════════════════════════════════════════════════════════════
    # Auto scan
    # ═══════════════════════════════════════════════════════════════

    def toggle_auto_scan(self, state: int):
        is_checked = (state == Qt.CheckState.Checked.value or state is True)
        if is_checked:
            seconds = self.spin_interval.value()
            self.auto_scan_timer.start(seconds * 1000)
            self.spin_interval.setEnabled(True)
            self.status_update_signal.emit(
                f"اسکن خودکار هر {seconds} ثانیه فعال شد")
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

    # ═══════════════════════════════════════════════════════════════
    # Broker connection
    # ═══════════════════════════════════════════════════════════════

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
            QMessageBox.critical(
                self, "خطا", f"بارگذاری ماژول کارگزاری با خطا مواجه شد:\n{e}")
            return

        self.btn_broker_connect.setText("⏳ در حال اتصال...")
        self.btn_broker_connect.setEnabled(False)
        self.status_update_signal.emit(
            "🌐 در حال باز کردن مرورگر و ورود به کارگزاری...")

        self._login_worker = BrokerLoginWorker(self._broker)
        self._login_worker.login_success.connect(self._on_broker_login_success)
        self._login_worker.login_failed.connect(self._on_broker_login_failed)
        self._login_worker.status_changed.connect(
            self.status_update_signal.emit)
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
        QMessageBox.warning(self, "اتصال به کارگزاری",
                            f"اتصال ناموفق:\n{error_msg}")

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

    # ═══════════════════════════════════════════════════════════════
    # Clear / Export
    # ═══════════════════════════════════════════════════════════════

    def clear_results(self):
        if self.table.rowCount() > 0:
            reply = QMessageBox.question(
                self, "پاک کردن نتایج", "آیا از پاک کردن تمام نتایج اطمینان دارید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._flash_manager.clear()
                self.table.setSortingEnabled(False)
                self.table.setRowCount(0)
                self.current_results = []
                self._prev_cell_values = {}
                self.inspector.clear_inspector()
                self._show_empty_state()
                self._update_stats()
                self.status_update_signal.emit("🗑️ نتایج پاک شد")

    def export_results_to_excel(self):
        if not self.current_results:
            QMessageBox.information(
                self, "اطلاعات", "نتیجه‌ای برای ذخیره وجود ندارد.")
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
            headers = [self.table.horizontalHeaderItem(
                c).text() for c in range(1, col_count)]

            for r in range(self.table.rowCount()):
                if self.table.item(r, 1) and "برای شروع" in self.table.item(r, 1).text():
                    continue
                row_data = [self.table.item(r, c).text() if self.table.item(
                    r, c) else "" for c in range(1, col_count)]
                rows.append(row_data)

            df = pd.DataFrame(rows, columns=headers)
            if filepath.endswith(".csv"):
                df.to_csv(filepath, index=False, encoding="utf-8-sig")
            else:
                if not filepath.endswith(".xlsx"):
                    filepath += ".xlsx"
                df.to_excel(filepath, index=False, engine="openpyxl")

            self.status_update_signal.emit(f"فایل ذخیره شد: {filepath}")
            QMessageBox.information(
                self, "موفق", f"گزارش در مسیر زیر ذخیره شد:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره اکسل:\n{e}")

    # ═══════════════════════════════════════════════════════════════
    # Close
    # ═══════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        if self.auto_scan_timer.isActive():
            self.auto_scan_timer.stop()

        if self.telemetry_worker and self.telemetry_worker.isRunning():
            self.telemetry_worker.stop()

        if self._login_worker and self._login_worker.isRunning():
            self._login_worker.stop()
            self._login_worker.wait(1500)

        if self._broker_execution_worker and self._broker_execution_worker.isRunning():
            self._broker_execution_worker.stop()
            self._broker_execution_worker.wait(2000)

        if self._broker_connected:
            try:
                self._broker.close_browser()
            except Exception:
                pass

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)

        try:
            if self._snippet_server and self._snippet_server.is_running:
                self._snippet_server.stop()
                logger.info("DevTools Snippet server stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Snippet server: {e}")

        try:
            if self._spread_window is not None:
                self._spread_window.close()
                self._spread_window = None
        except Exception:
            pass

        try:
            if self._position_manager_window is not None:
                self._position_manager_window.close()
                self._position_manager_window = None
        except Exception:
            pass

        event.accept()
        logger.info("Application terminated cleanly")

    # ═══════════════════════════════════════════════════════════════
    # Column filter context menu
    # ═══════════════════════════════════════════════════════════════

    def _setup_table_context_menu(self):
        self.table.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(
            self._show_column_filter_menu)

    def _show_column_filter_menu(self, pos):
        header = self.table.horizontalHeader()
        column_index = header.logicalIndexAt(pos)

        if column_index < 0:
            return

        column_name = self.table.horizontalHeaderItem(column_index).text()

        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        filter_type = self._determine_filter_type(column_index, column_name)

        action_filter = menu.addAction(f"🔍 فیلتر: {column_name}")
        action_filter.triggered.connect(lambda: self._open_column_filter(
            column_index, column_name, filter_type))

        menu.addSeparator()

        action_asc = menu.addAction("📈 مرتب‌سازی صعودی")
        action_asc.triggered.connect(lambda: self.table.sortByColumn(
            column_index, Qt.SortOrder.AscendingOrder))

        action_desc = menu.addAction("📉 مرتب‌سازی نزولی")
        action_desc.triggered.connect(lambda: self.table.sortByColumn(
            column_index, Qt.SortOrder.DescendingOrder))

        menu.addSeparator()

        if self.table_filter_manager and column_index in self.table_filter_manager.filters:
            action_clear = menu.addAction("🧹 حذف فیلتر این سرستون")
            action_clear.triggered.connect(
                lambda: self._clear_column_filter(column_index, column_name))

        if self.table_filter_manager and self.table_filter_manager.filters:
            action_clear_all = menu.addAction("🧹 حذف تمام فیلترها")
            action_clear_all.triggered.connect(self._clear_all_filters)

        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _determine_filter_type(self, column_index: int, column_name: str) -> FilterType:
        numeric_keywords = ["Rank", "DTE", "سررسید",
                            "قیمت", "درصد", "%", "ریسک", "سود", "Breakeven",
                            "محافظه‌کار", "متعادل", "پرریسک"]

        for keyword in numeric_keywords:
            if keyword in column_name:
                return FilterType.NUMERIC

        return FilterType.TEXT

    def _open_column_filter(self, column_index: int, column_name: str, filter_type: FilterType):
        dialog = ColumnFilterDialog(
            column_name,
            filter_type,
            self,
            table_filter_manager=self.table_filter_manager,
            column_index=column_index
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            filter_func = dialog.filter_result
            filter_metadata = dialog.filter_metadata

            logger.info(
                f"فیلتر برای {column_name}: filter_func={filter_func is not None}, metadata={filter_metadata}")

            self.table_filter_manager.set_filter(
                column_index, column_name, filter_func, filter_metadata)

            active_count = self.table_filter_manager.get_active_filter_count()
            visible_count = self.table_filter_manager.get_visible_row_count()
            total_count = self.table.rowCount()

            status_msg = f"فیلتر‌های فعال: {active_count} | ردیف‌های قابل نمایش: {visible_count}/{total_count}"
            self.status_update_signal.emit(status_msg)

    def _clear_column_filter(self, column_index: int, column_name: str):
        self.table_filter_manager.set_filter(column_index, column_name, None)

        active_count = self.table_filter_manager.get_active_filter_count()
        visible_count = self.table_filter_manager.get_visible_row_count()
        total_count = self.table.rowCount()

        if active_count > 0:
            status_msg = f"فیلتر‌های فعال: {active_count} | ردیف‌های قابل نمایش: {visible_count}/{total_count}"
        else:
            status_msg = f"تمام فیلترها حذف شدند | {total_count} ردیف نمایش داده می‌شود"

        self.status_update_signal.emit(status_msg)

    def _clear_all_filters(self):
        self.table_filter_manager.clear_all_filters()
        total_count = self.table.rowCount()
        self.status_update_signal.emit(
            f"تمام فیلترها حذف شدند | {total_count} ردیف نمایش داده می‌شود")

    # ═══════════════════════════════════════════════════════════════
    # Position Manager (placeholder) & Spread Analyzer
    # ═══════════════════════════════════════════════════════════════

    def _open_position_manager(self):
        """
        باز کردن پنجره‌ی مدیریت و ثبت موقعیت‌ها.
        فعلاً placeholder است.
        """
        QMessageBox.information(
            self, "مدیریت و ثبت موقعیت‌ها",
            "این پنجره در نسخه‌ی بعدی پیاده‌سازی می‌شود.\n\n"
            "قابلیت‌های پیش‌بینی‌شده:\n"
            "• مشاهده‌ی موقعیت‌های باز\n"
            "• ثبت سفارش‌های اجرا شده\n"
            "• پیگیری وضعیت اجرا\n"
            "• گزارش سود/زیان لحظه‌ای\n"
            "• اتصال به کارگزاری"
        )

    def _open_spread_analyzer(self):
        """
        باز کردن پنجره‌ی تحلیلگر نقطه‌ای.
        """
        try:
            from ui.spread_analyzer_window import SpreadAnalyzerWindow
        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"بارگذاری پنجره تحلیلگر ناموفق بود:\n{e}"
            )
            logger.error(f"SpreadAnalyzerWindow import failed: {e}")
            return

        if self._spread_window is None:
            try:
                self._spread_window = SpreadAnalyzerWindow(
                    scanner_engine=self.scanner_engine,
                    parent=None,
                )
                logger.info("SpreadAnalyzerWindow created")
            except Exception as e:
                logger.error(
                    f"Failed to create SpreadAnalyzerWindow: {e}",
                    exc_info=True
                )
                QMessageBox.critical(
                    self, "خطا",
                    f"ایجاد پنجره تحلیلگر ناموفق بود:\n{e}"
                )
                return

        try:
            self._spread_window.show()
            self._spread_window.raise_()
            self._spread_window.activateWindow()
        except RuntimeError:
            self._spread_window = None
            self._open_spread_analyzer()