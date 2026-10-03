# ui/spread_analyzer_window.py
# -*- coding: utf-8 -*-

"""
پنجره‌ی تحلیلگر نقطه‌ای استراتژی‌ها.

این پنجره:
- از هر دو نوع engine پشتیبانی می‌کند:
  * OptionScanner (از main.py) → متد run_scan_with_progress()
  * ScannerEngine (از engine/) → متد execute_full_scan()
- شاخص‌های نقطه‌ای (R30، M30، سربه‌سر، امتیاز Cobb-Douglas) را استخراج می‌کند
- امکان ارسال به Bale / Selenium / DevTools Snippet را می‌دهد
- کاملاً مستقل از MainWindow است

اجرای مستقیم (تست):
    python -m ui.spread_analyzer_window
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QHeaderView, QMessageBox, QStatusBar, QProgressBar,
    QAbstractItemView, QButtonGroup, QCheckBox, QSpinBox,
    QDoubleSpinBox, QGroupBox,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont

from ui import theme as ui_theme


logger = logging.getLogger("OptionScanner.UI.SpreadAnalyzer")


# ═════════════════════════════════════════════════════════════
# تنظیمات پیش‌فرض
# ═════════════════════════════════════════════════════════════

DEFAULT_REFRESH_SEC = 30
DEFAULT_R_MIN = 5.0
DEFAULT_M_MIN = 10.0
DEFAULT_SCORE_THRESHOLD = 0.5

# نام‌های نمایشی استراتژی‌ها
STRATEGY_LABELS = {
    "bull_call_spread": "Bull Call Spread",
    "covered_call": "Covered Call",
    "long_call": "Long Call",
}

# رنگ استراتژی‌ها
STRATEGY_COLORS = {
    "bull_call_spread": "#3fb950",
    "covered_call": "#58a6ff",
    "long_call": "#d29922",
}


# ═════════════════════════════════════════════════════════════
# جدول RTL با انتخاب تکی
# ═════════════════════════════════════════════════════════════

class _NumericTableWidgetItem(QTableWidgetItem):
    """آیتم جدول با مرتب‌سازی عددی صحیح."""

    def __lt__(self, other):
        try:
            v_self = self.data(Qt.ItemDataRole.UserRole)
            v_other = other.data(Qt.ItemDataRole.UserRole)
            if v_self is not None and v_other is not None:
                return float(v_self) < float(v_other)
            return super().__lt__(other)
        except (ValueError, TypeError):
            return super().__lt__(other)


# ═════════════════════════════════════════════════════════════
# پنجره اصلی
# ═════════════════════════════════════════════════════════════

class SpreadAnalyzerWindow(QMainWindow):
    """
    پنجره‌ی مستقل تحلیلگر نقطه‌ای استراتژی‌ها.

    این پنجره از همان ScannerEngine/OptionScanner موجود استفاده می‌کند و
    شاخص‌های نقطه‌ای را روی Opportunity ها اعمال می‌کند.
    """

    status_message = Signal(str)

    def __init__(self, scanner_engine: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # 🆕 غیرفعال کردن پنجره‌ی والد
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.scanner_engine = scanner_engine

        # State
        self.current_opportunities: List = []
        self.selected_row_idx: Optional[int] = None
        self.active_strategy: str = "bull_call_spread"
        self._backend_online: bool = False

        # Theme
        self._theme_mode = ui_theme.resolve_theme(ui_theme.THEME_DARK)

        # Timers
        self._auto_timer: Optional[QTimer] = None
        self._backend_timer: Optional[QTimer] = None

        # Window setup
        self.setWindowTitle("Spread Analyzer - Point-based View")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1300, 750)

        self._init_ui()
        self._start_auto_scan()
        self._start_backend_check()

        logger.info("SpreadAnalyzerWindow initialized")

    # ═════════════════════════════════════════════════════════
    # ساخت UI
    # ═════════════════════════════════════════════════════════

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        # ۱. نوار بالایی
        layout.addWidget(self._build_top_bar())

        # ۲. انتخاب استراتژی + فیلترها
        layout.addWidget(self._build_strategy_bar())

        # ۳. جدول
        layout.addWidget(self._build_table(), stretch=1)

        # ۴. نوار پایینی
        layout.addWidget(self._build_bottom_bar())

        # ۵. نوار وضعیت
        self._build_status_bar()

    def _build_top_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            ui_theme.get_toolbar_frame_style(self._theme_mode)
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # دکمه اسکن
        self.btn_scan = QPushButton("Scan Market")
        self.btn_scan.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="success")
        )
        self.btn_scan.clicked.connect(self.do_scan)
        layout.addWidget(self.btn_scan)

        layout.addSpacing(15)

        # اسکن خودکار
        self.chk_auto = QCheckBox("Auto Scan")
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(self._toggle_auto_scan)
        layout.addWidget(self.chk_auto)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 3600)
        self.spin_interval.setValue(DEFAULT_REFRESH_SEC)
        self.spin_interval.setSuffix(" sec")
        self.spin_interval.setSingleStep(5)
        layout.addWidget(self.spin_interval)

        layout.addStretch()

        # وضعیت Backend
        self.lbl_backend = QLabel("Backend: offline")
        self.lbl_backend.setStyleSheet("color: #8c9bae;")
        layout.addWidget(self.lbl_backend)

        # تعداد نتایج
        self.lbl_count = QLabel("0 positions")
        self.lbl_count.setStyleSheet(
            "color: #58a6ff; font-weight: bold; padding: 4px 10px;"
        )
        layout.addWidget(self.lbl_count)

        return frame

    def _build_strategy_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            ui_theme.get_toolbar_frame_style(self._theme_mode)
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # عنوان
        lbl = QLabel("Strategy:")
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)

        # دکمه‌های استراتژی
        self.strategy_buttons = {}
        self.strategy_group = QButtonGroup(self)
        self.strategy_group.setExclusive(True)

        for key, label in STRATEGY_LABELS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumWidth(150)
            btn.setStyleSheet(self._strategy_button_style(key))
            btn.clicked.connect(lambda checked, k=key: self._set_strategy(k))
            self.strategy_buttons[key] = btn
            self.strategy_group.addButton(btn)
            layout.addWidget(btn)

        self.strategy_buttons[self.active_strategy].setChecked(True)

        layout.addSpacing(20)

        # فیلتر R30
        layout.addWidget(QLabel("R30 >= "))
        self.spin_r_min = QDoubleSpinBox()
        self.spin_r_min.setRange(-50.0, 200.0)
        self.spin_r_min.setValue(DEFAULT_R_MIN)
        self.spin_r_min.setSuffix(" %")
        self.spin_r_min.setSingleStep(0.5)
        self.spin_r_min.setDecimals(1)
        self.spin_r_min.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.spin_r_min)

        # فیلتر M30
        layout.addWidget(QLabel("M30 >= "))
        self.spin_m_min = QDoubleSpinBox()
        self.spin_m_min.setRange(-50.0, 200.0)
        self.spin_m_min.setValue(DEFAULT_M_MIN)
        self.spin_m_min.setSuffix("")
        self.spin_m_min.setSingleStep(0.5)
        self.spin_m_min.setDecimals(1)
        self.spin_m_min.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.spin_m_min)

        # فیلتر امتیاز
        layout.addWidget(QLabel("Score >= "))
        self.spin_score = QDoubleSpinBox()
        self.spin_score.setRange(0.0, 100.0)
        self.spin_score.setValue(DEFAULT_SCORE_THRESHOLD)
        self.spin_score.setSuffix("")
        self.spin_score.setSingleStep(0.1)
        self.spin_score.setDecimals(2)
        self.spin_score.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.spin_score)

        # دکمه‌ی اعمال فیلتر
        self.btn_apply_filter = QPushButton("Apply Filter")
        self.btn_apply_filter.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="primary")
        )
        self.btn_apply_filter.clicked.connect(self._apply_filter_to_current)
        layout.addWidget(self.btn_apply_filter)

        layout.addStretch()
        return frame

    def _strategy_button_style(self, key: str) -> str:
        """استایل اختصاصی برای دکمه‌ی استراتژی."""
        color = STRATEGY_COLORS.get(key, "#58a6ff")
        return f"""
            QPushButton {{
                background-color: #21262d;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                border-color: {color};
                color: {color};
            }}
            QPushButton:checked {{
                background-color: {color};
                color: #ffffff;
                border-color: {color};
            }}
        """

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Rank",
            "Underlying",
            "Leg 1",
            "Leg 2",
            "Break Even",
            "R30 (%)",
            "M30",
            "Score",
        ])

        # تنظیمات
        self.table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        # استایل
        self.table.setStyleSheet(self._table_style())

        # هدر
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # عرض ستون‌ها
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 90)
        self.table.setColumnWidth(7, 100)

        # انتخاب سطر
        self.table.itemSelectionChanged.connect(self._on_row_selection_changed)

        return self.table

    def _table_style(self) -> str:
        return """
            QTableWidget {
                background-color: #161b22;
                alternate-background-color: #0d1117;
                color: #c9d1d9;
                gridline-color: #30363d;
                border: 1px solid #30363d;
                border-radius: 8px;
                font-family: Tahoma, Segoe UI;
                font-size: 12px;
                selection-background-color: #1f6feb;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 6px;
                border: none;
            }
            QTableWidget::item:hover {
                background-color: #21262d;
            }
            QHeaderView::section {
                background-color: #21262d;
                color: #c9d1d9;
                padding: 8px;
                border: none;
                border-right: 1px solid #30363d;
                border-bottom: 2px solid #58a6ff;
                font-weight: bold;
                font-size: 12px;
            }
        """

    def _build_bottom_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            ui_theme.get_toolbar_frame_style(self._theme_mode)
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # اطلاعات انتخاب
        self.lbl_selected = QLabel("No position selected")
        self.lbl_selected.setStyleSheet(
            "color: #8c9bae; padding: 6px 12px; "
            "background: #21262d; border-radius: 4px;"
        )
        layout.addWidget(self.lbl_selected, stretch=1)

        # دکمه‌های ارسال
        self.btn_send_snippet = QPushButton("Send via Snippet")
        self.btn_send_snippet.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="primary")
        )
        self.btn_send_snippet.setEnabled(False)
        self.btn_send_snippet.setToolTip(
            "Send position to DevTools Snippet (no Selenium)"
        )
        self.btn_send_snippet.clicked.connect(self._send_via_snippet)
        layout.addWidget(self.btn_send_snippet)

        self.btn_send_selenium = QPushButton("Send via Selenium")
        self.btn_send_selenium.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="warning")
        )
        self.btn_send_selenium.setEnabled(False)
        self.btn_send_selenium.clicked.connect(self._send_via_selenium)
        layout.addWidget(self.btn_send_selenium)

        self.btn_send_bale = QPushButton("Send via Bale")
        self.btn_send_bale.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="success")
        )
        self.btn_send_bale.setEnabled(False)
        self.btn_send_bale.clicked.connect(self._send_via_bale)
        layout.addWidget(self.btn_send_bale)

        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_excel.setStyleSheet(
            ui_theme.get_button_style(self._theme_mode, role="secondary")
        )
        self.btn_export_excel.clicked.connect(self._export_to_excel)
        layout.addWidget(self.btn_export_excel)

        return frame

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.status_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # اتصال سیگنال
        self.status_message.connect(self.status_bar.showMessage)

    # ═════════════════════════════════════════════════════════
    # Auto-refresh
    # ═════════════════════════════════════════════════════════

    def _start_auto_scan(self):
        """شروع تایمر اسکن خودکار."""
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self.do_scan)
        if self.chk_auto.isChecked():
            self._auto_timer.start(DEFAULT_REFRESH_SEC * 1000)

        # اولین اسکن بعد از ۱.۵ ثانیه
        QTimer.singleShot(1500, self.do_scan)

    def _toggle_auto_scan(self, state: int):
        if state == Qt.CheckState.Checked.value:
            if self._auto_timer is not None:
                self._auto_timer.start(self.spin_interval.value() * 1000)
            self.status_message.emit("Auto scan enabled")
        else:
            if self._auto_timer is not None:
                self._auto_timer.stop()
            self.status_message.emit("Auto scan disabled")

    def _start_backend_check(self):
        """شروع تایمر بررسی Backend."""
        self._backend_timer = QTimer(self)
        self._backend_timer.timeout.connect(self._check_backend)
        self._backend_timer.start(10000)  # هر ۱۰ ثانیه
        QTimer.singleShot(2000, self._check_backend)

    def _check_backend(self):
        """بررسی وضعیت Backend (Snippet Server)."""
        try:
            import requests
            r = requests.get(
                "http://127.0.0.1:8000/health",
                timeout=2,
            )
            if r.status_code == 200:
                self._backend_online = True
                self.lbl_backend.setText("Backend: online")
                self.lbl_backend.setStyleSheet(
                    "color: #3fb950; font-weight: bold;"
                )
            else:
                raise Exception(f"HTTP {r.status_code}")
        except Exception:
            self._backend_online = False
            self.lbl_backend.setText("Backend: offline")
            self.lbl_backend.setStyleSheet("color: #8c9bae;")

        # به‌روزرسانی دکمه Snippet
        if self.selected_row_idx is not None:
            self.btn_send_snippet.setEnabled(self._backend_online)

    # ═════════════════════════════════════════════════════════
    # استراتژی
    # ═════════════════════════════════════════════════════════

    def _set_strategy(self, strategy_key: str):
        """تغییر استراتژی فعال."""
        if strategy_key == self.active_strategy:
            return

        self.active_strategy = strategy_key
        self.strategy_buttons[strategy_key].setChecked(True)

        # پاک کردن جدول
        self.table.setRowCount(0)
        self.current_opportunities = []
        self.selected_row_idx = None
        self.lbl_selected.setText("No position selected")
        self._set_action_buttons_enabled(False)

        self.status_message.emit(
            f"Strategy: {STRATEGY_LABELS.get(strategy_key, strategy_key)}")

        # اسکن فوری
        QTimer.singleShot(200, self.do_scan)

    # ═════════════════════════════════════════════════════════
    # اسکن
    # ═════════════════════════════════════════════════════════

    @Slot()
    def do_scan(self):
        """اجرای اسکن و پر کردن جدول با شاخص‌های نقطه‌ای."""
        if self.scanner_engine is None:
            self.status_message.emit("Scanner engine not available")
            return

        try:
            self.btn_scan.setEnabled(False)
            self.status_message.emit("Scanning market...")

            # ۱. اجرای اسکن — سازگار با هر دو نوع engine
            all_opps = self._run_scan()

            if not all_opps:
                self.status_message.emit("No opportunities found")
                self.lbl_count.setText("0 positions")
                self.table.setRowCount(0)
                self.current_opportunities = []
                return

            # ۲. تحلیل نقطه‌ای (Enrich + Filter + Sort)
            from scoring.point_analyzer import process_opportunities

            filtered = process_opportunities(
                all_opps,
                strategy_name=self.active_strategy,
                R_min=self.spin_r_min.value(),
                M_min=self.spin_m_min.value(),
                score_threshold=self.spin_score.value(),
                sort_by_score=True,
            )

            # ۳. ذخیره + نمایش
            self.current_opportunities = filtered
            self._populate_table(filtered)

            # ۴. خلاصه
            from scoring.point_analyzer import get_summary
            summary = get_summary(filtered)

            self.status_message.emit(
                f"Scan complete: {summary['total']} positions | "
                f"Avg R30: {summary['avg_R30']}% | "
                f"Avg M30: {summary['avg_M30']} | "
                f"Avg Score: {summary['avg_score']}"
            )
            self.lbl_count.setText(f"{summary['total']} positions")

            logger.info(
                "Scan done. Total=%d AvgR30=%.2f AvgM30=%.2f AvgScore=%.4f",
                summary['total'],
                summary['avg_R30'],
                summary['avg_M30'],
                summary['avg_score'],
            )

        except Exception as e:
            logger.error("Scan failed: %s", e, exc_info=True)
            self.status_message.emit(f"Scan error: {e}")
            QMessageBox.critical(self, "Scan Error", str(e))
        finally:
            self.btn_scan.setEnabled(True)

    def _run_scan(self) -> List:
        """
        اجرای اسکن با هر نوع engine.

        پشتیبانی از:
        - OptionScanner (از main.py): متد run_scan_with_progress()
        - ScannerEngine (از engine/): متد execute_full_scan()

        Returns:
            لیست Opportunity
        """
        engine = self.scanner_engine
        strategy_filter = self.active_strategy

        # ── حالت ۱: OptionScanner (از main.py) ──
        if hasattr(engine, 'run_scan_with_progress'):
            logger.debug("Using OptionScanner.run_scan_with_progress()")
            result = engine.run_scan_with_progress(
                progress_callback=None,
                stop_check_callback=None,
                force_refresh=True,
                strategy_filter=strategy_filter,)
            # OptionScanner مستقیماً لیست برمی‌گرداند
            if isinstance(result, list):
                return result
            if result is None:
                return []
            # اگر ScanResult بود (احتمالاً نه، ولی برای اطمینان)
            return getattr(result, 'opportunities', []) or []

        # ── حالت ۲: ScannerEngine (از engine/) ──
        if hasattr(engine, 'execute_full_scan'):
            logger.debug("Using ScannerEngine.execute_full_scan()")
            result = engine.execute_full_scan(strategy_filter=strategy_filter,)
            if result is None:
                return []
            return getattr(result, 'opportunities', []) or []

        # ── حالت ۳: خودش iterable از Opportunity باشد ──
        if hasattr(engine, '__iter__'):
            logger.debug("Using engine as iterable")
            return list(engine)

        # ── حالت ۴: ناشناخته ──
        logger.error(
            "Unsupported scanner engine type: %s",
            type(engine).__name__,
        )
        raise TypeError(
            f"Scanner engine type '{type(engine).__name__}' is not supported. "
            f"Expected 'OptionScanner' or 'ScannerEngine'."
        )

    # ═════════════════════════════════════════════════════════
    # جدول
    # ═════════════════════════════════════════════════════════

    def _populate_table(self, opportunities: List):
        """پر کردن جدول با Opportunity های Enriched."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_idx, opp in enumerate(opportunities):
            self.table.insertRow(row_idx)
            self._populate_row(row_idx, opp)

        self.table.setSortingEnabled(True)

    def _populate_row(self, row: int, opp):
        """پر کردن یک ردیف جدول."""
        md = getattr(opp, 'metadata', {}) or {}

        # ۱. Rank
        rank_item = _NumericTableWidgetItem(str(row + 1))
        rank_item.setData(Qt.ItemDataRole.UserRole, int(row + 1))
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        rank_item.setData(Qt.ItemDataRole.UserRole + 1, opp)
        self.table.setItem(row, 0, rank_item)

        # ۲. Underlying
        ticker = str(getattr(opp, 'underlying_ticker', '-'))
        ticker_item = QTableWidgetItem(ticker)
        f = ticker_item.font()
        f.setBold(True)
        ticker_item.setFont(f)
        ticker_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, ticker_item)

        # ۳. Leg 1
        legs = getattr(opp, 'legs', []) or []
        leg1_text = self._format_leg(legs[0]) if len(legs) > 0 else "-"
        leg1_item = QTableWidgetItem(leg1_text)
        leg1_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setItem(row, 2, leg1_item)

        # ۴. Leg 2
        leg2_text = self._format_leg(legs[1]) if len(legs) > 1 else "-"
        leg2_item = QTableWidgetItem(leg2_text)
        leg2_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setItem(row, 3, leg2_item)

        # ۵. Break Even
        be_first = md.get('break_even_first')
        if be_first is not None:
            try:
                be_text = f"{int(be_first):,}"
            except (ValueError, TypeError):
                be_text = str(be_first)
        else:
            be_text = "-"
        be_item = QTableWidgetItem(be_text)
        be_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, be_item)

        # ۶. R30
        r30 = float(md.get('R30', 0.0) or 0.0)
        r30_item = _NumericTableWidgetItem(f"{r30:.2f}%")
        r30_item.setData(Qt.ItemDataRole.UserRole, r30)
        r30_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        r30_item.setForeground(QBrush(QColor("#3fb950")))
        f = r30_item.font()
        f.setBold(True)
        r30_item.setFont(f)
        self.table.setItem(row, 5, r30_item)

        # ۷. M30
        m30 = float(md.get('M30', 0.0) or 0.0)
        m30_item = _NumericTableWidgetItem(f"{m30:.2f}")
        m30_item.setData(Qt.ItemDataRole.UserRole, m30)
        m30_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if m30 >= 20:
            m30_item.setForeground(QBrush(QColor("#3fb950")))
        elif m30 >= 10:
            m30_item.setForeground(QBrush(QColor("#d29922")))
        else:
            m30_item.setForeground(QBrush(QColor("#f85149")))
        self.table.setItem(row, 6, m30_item)

        # ۸. Score
        score = float(md.get('composite_score', 0.0) or 0.0)
        score_item = _NumericTableWidgetItem(f"{score:.2f}")
        score_item.setData(Qt.ItemDataRole.UserRole, score)
        score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if score >= 3.0:
            score_item.setForeground(QBrush(QColor("#3fb950")))
        elif score >= 1.5:
            score_item.setForeground(QBrush(QColor("#d29922")))
        else:
            score_item.setForeground(QBrush(QColor("#f85149")))
        f = score_item.font()
        f.setBold(True)
        score_item.setFont(f)
        self.table.setItem(row, 7, score_item)

    def _format_leg(self, leg) -> str:
        """فرمت یک لگ برای نمایش."""
        contract = getattr(leg, 'contract', None)
        if contract is None:
            return "-"

        ticker = str(getattr(contract, 'ticker', '-'))
        side_raw = str(getattr(leg, 'side', '')).upper()
        side = "BUY" if "BUY" in side_raw else "SELL"
        ratio = int(getattr(leg, 'ratio', 1))

        return f"{side} {ticker} ({ratio}x)"

    # ═════════════════════════════════════════════════════════
    # انتخاب سطر
    # ═════════════════════════════════════════════════════════

    def _on_row_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.selected_row_idx = None
            self.lbl_selected.setText("No position selected")
            self._set_action_buttons_enabled(False)
            return

        row = rows[0].row()
        self.selected_row_idx = row

        rank_item = self.table.item(row, 0)
        if rank_item is None:
            return

        opp = rank_item.data(Qt.ItemDataRole.UserRole + 1)
        if opp is None:
            return

        md = getattr(opp, 'metadata', {}) or {}
        ticker = str(getattr(opp, 'underlying_ticker', '-'))
        score = float(md.get('composite_score', 0.0) or 0.0)
        r30 = float(md.get('R30', 0.0) or 0.0)

        self.lbl_selected.setText(
            f"Selected: {ticker} | R30: {r30:.2f}% | Score: {score:.2f}"
        )
        self._set_action_buttons_enabled(True)

    def _set_action_buttons_enabled(self, enabled: bool):
        """فعال/غیرفعال کردن دکمه‌های عملیات."""
        self.btn_send_bale.setEnabled(enabled)
        self.btn_send_selenium.setEnabled(enabled)
        self.btn_send_snippet.setEnabled(enabled and self._backend_online)
        self.btn_export_excel.setEnabled(
            enabled or bool(self.current_opportunities))

    def _get_selected_opportunity(self):
        """دریافت Opportunity انتخاب‌شده."""
        if self.selected_row_idx is None:
            return None

        rank_item = self.table.item(self.selected_row_idx, 0)
        if rank_item is None:
            return None

        return rank_item.data(Qt.ItemDataRole.UserRole + 1)

    # ═════════════════════════════════════════════════════════
    # فیلتر
    # ═════════════════════════════════════════════════════════

    def _on_filter_changed(self):
        """تغییر فیلتر (بدون اعمال خودکار)."""
        pass

    def _apply_filter_to_current(self):
        """اعمال فیلتر روی Opportunity های فعلی (بدون اسکن مجدد)."""
        if not self.current_opportunities:
            self.status_message.emit("No data to filter")
            return

        try:
            from scoring.point_analyzer import apply_point_filters

            filtered = apply_point_filters(
                self.current_opportunities,
                R_min=self.spin_r_min.value(),
                M_min=self.spin_m_min.value(),
                score_threshold=self.spin_score.value(),
            )

            self._populate_table(filtered)
            self.lbl_count.setText(f"{len(filtered)} positions")
            self.status_message.emit(
                f"Filter applied: {len(filtered)}/{len(self.current_opportunities)} passed"
            )
        except Exception as e:
            logger.error("Filter failed: %s", e, exc_info=True)
            self.status_message.emit(f"Filter error: {e}")

    # ═════════════════════════════════════════════════════════
    # ارسال‌ها
    # ═════════════════════════════════════════════════════════

    def _build_positions_text(self, opp) -> str:
        """ساخت متن Positions از Opportunity."""
        legs = getattr(opp, 'legs', []) or []
        parts = []
        for leg in legs:
            contract = getattr(leg, 'contract', None)
            if contract is None:
                continue
            ticker = str(getattr(contract, 'ticker', ''))
            side_raw = str(getattr(leg, 'side', '')).upper()
            side = "BUY" if "BUY" in side_raw else "SELL"
            ratio = int(getattr(leg, 'ratio', 1))
            parts.append(f"{ticker} ({ratio}x{side})")
        return " | ".join(parts)

    def _send_via_snippet(self):
        """ارسال از طریق DevTools Snippet."""
        if not self._backend_online:
            QMessageBox.warning(
                self, "Backend Offline",
                "Snippet server is not running."
            )
            return

        opp = self._get_selected_opportunity()
        if opp is None:
            return

        positions_text = self._build_positions_text(opp)
        if not positions_text.strip():
            QMessageBox.warning(self, "No Data", "Cannot extract positions.")
            return

        try:
            from automation.brokers.Omex_khobregan import (
                OmexKhobreganBroker,
            )

            broker = OmexKhobreganBroker()
            result = broker.submit_via_devtools_snippet(
                positions_text=positions_text,
                strategy_name=str(getattr(opp, 'strategy_name', '')),
                underlying=str(getattr(opp, 'underlying_ticker', '')),
            )

            if result.get('success'):
                self.status_message.emit(
                    f"Snippet: {result.get('order_id', '?')}"
                )
                QMessageBox.information(
                    self, "Sent",
                    result.get('message', 'Position sent.')
                )
            else:
                self.status_message.emit(
                    f"Snippet error: {result.get('message', '?')}"
                )
                QMessageBox.critical(
                    self, "Error",
                    result.get('message', 'Unknown error.')
                )
        except Exception as e:
            logger.error("Snippet send failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _send_via_selenium(self):
        """ارسال از طریق Selenium (نیاز به ورود دستی)."""
        opp = self._get_selected_opportunity()
        if opp is None:
            return

        positions_text = self._build_positions_text(opp)
        if not positions_text.strip():
            QMessageBox.warning(self, "No Data", "Cannot extract positions.")
            return

        QMessageBox.information(
            self, "Selenium",
            f"Position for Selenium:\n\n{positions_text}\n\n"
            "Use the main window for Selenium-based sending."
        )

    def _send_via_bale(self):
        """ارسال به Bale."""
        opp = self._get_selected_opportunity()
        if opp is None:
            return

        try:
            from alerts.bale_notifier import BaleNotifier
            from ui.settings_manager import settings_manager

            bale_cfg = settings_manager.get_bale_config()
            notifier = BaleNotifier(
                bot_token=bale_cfg.get('bot_token', ''),
                chat_id=bale_cfg.get('chat_id', ''),
            )

            if not notifier.is_configured:
                QMessageBox.warning(
                    self, "Bale",
                    "Bale is not configured."
                )
                return

            notifier.send_scan_results([opp], top_n=1)
            self.status_message.emit("Sending to Bale...")

        except Exception as e:
            logger.error("Bale send failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ═════════════════════════════════════════════════════════
    # Export
    # ═════════════════════════════════════════════════════════

    def _export_to_excel(self):
        """خروجی به Excel."""
        if not self.current_opportunities:
            QMessageBox.information(
                self, "Info",
                "No data to export."
            )
            return

        try:
            from reports.excel_exporter import ExcelExporter
            exporter = ExcelExporter()
            path = exporter.export(self.current_opportunities)
            QMessageBox.information(
                self, "Saved",
                f"Report saved to:\n{path}"
            )
            self.status_message.emit(f"Exported: {path}")
        except Exception as e:
            logger.error("Export failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ═════════════════════════════════════════════════════════
    # Close
    # ═════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """بستن پنجره."""
        try:
            if self._auto_timer is not None:
                self._auto_timer.stop()
            if self._backend_timer is not None:
                self._backend_timer.stop()
        except Exception:
            pass

        event.accept()
        logger.info("SpreadAnalyzerWindow closed")


# ═════════════════════════════════════════════════════════════
# اجرای مستقل (تست)
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # تلاش برای ساخت ScannerEngine
    try:
        from data.manager import get_market_snapshot
        from engine.scanner_engine import ScannerEngine

        logger.info("Loading market snapshot...")
        snapshot = get_market_snapshot(use_cache=True)
        engine = ScannerEngine(snapshot)
        logger.info("Scanner engine ready")
    except Exception as e:
        logger.error("Failed to create scanner engine: %s", e)
        engine = None

    window = SpreadAnalyzerWindow(scanner_engine=engine)
    window.show()

    sys.exit(app.exec())