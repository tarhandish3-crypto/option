# position_saver/ui/main_widget.py
# -*- coding: utf-8 -*-

"""
ویجت اصلی مدیریت موقعیت‌های استراتژی آپشن.

معماری:
    - OptionLeg:        معامله‌ی خام
    - StrategyPosition: واحد معاملاتی (Lot) — چند-لگ

تب‌ها:
    - 🟢 فعال
    - ⚠️ نیازمند تعیین تکلیف
    - 📜 تاریخچه

ویژگی‌های کلیدی:
    ✅ آلرت پویا (target ماهانه × d/30)
    ✅ نمایش ستون‌های تارگت + آستانه + Pace
    ✅ ویرایش موقعیت‌های بسته (تاریخچه)
    ✅ دکمه‌ی چک استراتژی جدید
    ✅ دکمه‌ی گزارش‌گیری
    ✅ حذف کامل گروه‌بندی (StrategyGroup)
"""

import re
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Tuple

import jdatetime
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QHeaderView, QMessageBox, QFileDialog, QFrame,
    QCheckBox, QSpinBox, QAbstractItemView,
    QMenu, QStatusBar, QMainWindow,
)
from PySide6.QtCore import Qt, Slot, QItemSelectionModel
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from position_saver.models import (
    StrategyPosition, PositionStatus,
)
from position_saver.storage import PositionStorage
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.shared_analytics import SharedAnalytics
from position_saver.live_monitor import (
    LivePositionMonitorThread, is_expired_date,
)
from position_saver.ui.dialogs import (
    PositionEditDialog, CashSettlementDialog,
    OffsetDialog, ImportHistoryDialog,
)

from position_saver.providers import get_market_snapshot
from position_saver.theme import (
    Theme, CURRENCY,
    fmt_money, fmt_pct, fmt_pnl,
    pnl_tone, set_kind, set_tone,
)


logger = logging.getLogger("PositionSaver.UI.MainWidget")


# ═════════════════════════════════════════════════════
# ثابت‌ها
# ═════════════════════════════════════════════════════

ROW_HEIGHT = 32
DAY_WARN_THRESHOLD = 7
DAY_CRITICAL_THRESHOLD = 3
ACTIONS_BAR_HEIGHT = 40

TAB_ACTIVE = 0
TAB_PENDING = 1
TAB_HISTORY = 2

# آستانه‌ی Pace
PACE_NEAR = 0.8   # ۸۰٪ آستانه = نزدیک
PACE_HIT = 1.0    # رسید


# ═════════════════════════════════════════════════════
# SortableItem
# ═════════════════════════════════════════════════════

class SortableItem(QTableWidgetItem):
    """آیتم جدول با سورت عددی."""

    def __init__(self, display_text: str, sort_value: Any = None):
        super().__init__(str(display_text))
        self._sort_value = (
            sort_value if sort_value is not None else display_text)
        self.setTextAlignment(Qt.AlignCenter)

    def __lt__(self, other):
        if isinstance(other, SortableItem):
            try:
                if isinstance(self._sort_value, (int, float)) and \
                        isinstance(other._sort_value, (int, float)):
                    return self._sort_value < other._sort_value
                return str(self._sort_value) < str(other._sort_value)
            except Exception:
                return str(self._sort_value) < str(other._sort_value)
        return super().__lt__(other)


# ═════════════════════════════════════════════════════
# ویجت اصلی
# ═════════════════════════════════════════════════════

class PositionSaverWidget(QWidget):
    """
    ویجت اصلی مدیریت موقعیت‌های استراتژی.

    شامل:
        - ۳ تب: فعال / نیازمند تعیین تکلیف / تاریخچه
        - آلرت پویا (بر اساس target ماهانه)
        - گزارش‌گیری
        - چک استراتژی جدید
    """

    # ─── ستون‌های جدول position ───
    COL_ID = 0
    COL_STRATEGY = 1
    COL_BROKER = 2
    COL_UNDERLYING = 3
    COL_EXEC_DATE = 4
    COL_EXPIRY_DATE = 5
    COL_DAYS_INFO = 6
    COL_LEGS = 7
    COL_NET_COST = 8
    COL_TARGET_MONTHLY = 9
    COL_THRESHOLD = 10
    COL_LIVE_PNL = 11
    COL_CURRENT_ROI = 12
    COL_PACE = 13
    COL_TARGET_STATUS = 14
    COL_STATUS = 15
    COL_SOURCE = 16
    N_COLS = 17

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        storage: Optional[PositionStorage] = None,
        auto_start_monitor: bool = True,
    ):
        super().__init__(parent)

        self.storage = storage if storage is not None else PositionStorage()

        # ─── state اصلی ───
        self.positions: List[StrategyPosition] = []

        # ─── state ترد ───
        self._monitor_started = False
        self._expired_alerted = set()
        self._last_success_time: Optional[datetime] = None
        self._market_snapshot = None
        self._alerted_position_ids = set()

        self.setObjectName("PositionSaver")

        # ─── ترد پس‌زمینه ───
        self.monitor_thread = LivePositionMonitorThread(
            self.storage, check_interval=10)
        self.monitor_thread.prices_updated.connect(
            self.on_prices_updated)
        self.monitor_thread.alerts_found.connect(
            self.on_alerts_found)
        self.monitor_thread.expired_found.connect(
            self.on_expired_found)
        self.monitor_thread.connection_status.connect(
            self.on_connection_status)

        self.init_ui()
        self._setup_shortcuts()
        self.load_data()

        if auto_start_monitor:
            self.start_monitor()

    # ═══════════════════════════════════════════════════
    # چرخه حیات
    # ═══════════════════════════════════════════════════

    def start_monitor(self):
        if not self._monitor_started:
            self.monitor_thread.start()
            self._monitor_started = True

    def stop_monitor(self):
        if self._monitor_started:
            self.monitor_thread.stop()
            self.monitor_thread.wait(3000)
            self._monitor_started = False

    def closeEvent(self, event):
        self.stop_monitor()
        super().closeEvent(event)

    # ═══════════════════════════════════════════════════
    # میانبرها
    # ═══════════════════════════════════════════════════

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_position)
        QShortcut(QKeySequence("F5"), self, self.manual_refresh_data)
        QShortcut(QKeySequence("Ctrl+B"), self,
                  self.send_positions_to_bale)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_to_excel)
        QShortcut(QKeySequence("Ctrl+I"), self, self.import_from_excel)
        QShortcut(QKeySequence("Ctrl+R"), self, self.show_report)
        QShortcut(QKeySequence("Ctrl+K"), self, self.check_new_strategy)

    # ═══════════════════════════════════════════════════
    # نوار وضعیت
    # ═══════════════════════════════════════════════════

    def _get_status_bar(self) -> Optional[QStatusBar]:
        try:
            window = self.window()
            if isinstance(window, QMainWindow) and window.statusBar():
                return window.statusBar()
        except (AttributeError, RuntimeError):
            pass
        return None

    def _show_status(self, message: str, timeout: int = 5000):
        bar = self._get_status_bar()
        if bar:
            bar.showMessage(message, timeout)

    # ═══════════════════════════════════════════════════
    # ساخت UI
    # ═══════════════════════════════════════════════════

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        main_layout.addLayout(self._build_toolbar())

        self.tabs = QTabWidget()

        # ─── تب ۱: فعال ───
        self.tab_active, self.lbl_sum_active, self.lbl_empty_active = \
            self._build_table_tab("active")
        self.tabs.addTab(self.tab_active, "🟢 فعال")

        # ─── تب ۲: نیازمند تعیین تکلیف ───
        self.tab_pending, self.lbl_sum_pending, self.lbl_empty_pending = \
            self._build_table_tab("pending")
        self.tabs.addTab(self.tab_pending, "⚠️ نیازمند تعیین تکلیف")

        # ─── تب ۳: تاریخچه ───
        self.tab_history, self.lbl_sum_history, self.lbl_empty_history = \
            self._build_table_tab("history")
        self.tabs.addTab(self.tab_history, "📜 تاریخچه")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        self.summary_frame = self._build_summary_panel()
        main_layout.addWidget(self.summary_frame)

    def _on_tab_changed(self, idx: int):
        """به‌روزرسانی هنگام تعویض تب."""
        if idx == TAB_ACTIVE:
            self._populate_table(
                self.tab_active, self._get_active_positions())
        elif idx == TAB_PENDING:
            self._populate_table(
                self.tab_pending, self._get_pending_positions())
        elif idx == TAB_HISTORY:
            self._populate_table(
                self.tab_history, self._get_history_positions())

    # ═══════════════════════════════════════════════════
    # پنل کارت‌های خلاصه
    # ═══════════════════════════════════════════════════

    def _build_summary_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setFixedHeight(84)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(20)

        self.card_open_pnl = self._make_card("سود/زیان باز", "0")
        layout.addWidget(self.card_open_pnl)
        layout.addWidget(self._make_separator())

        self.card_realized_pnl = self._make_card(
            "سود/زیان محقق‌شده", "0")
        layout.addWidget(self.card_realized_pnl)
        layout.addWidget(self._make_separator())

        self.card_total_pnl = self._make_card("مجموع کل", "0")
        layout.addWidget(self.card_total_pnl)
        layout.addWidget(self._make_separator())

        self.card_count = self._make_card("موقعیت‌های فعال", "0")
        layout.addWidget(self.card_count)
        layout.addWidget(self._make_separator())

        self.card_alerts = self._make_card("آلرت‌های امروز", "0")
        layout.addWidget(self.card_alerts)
        layout.addWidget(self._make_separator())

        self.card_nearest = self._make_card("نزدیک‌ترین سررسید", "—")
        layout.addWidget(self.card_nearest)
        layout.addStretch()

        return frame

    def _make_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(12, 8, 12, 8)
        vbox.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("cardTitle")

        lbl_value = QLabel(value)
        lbl_value.setObjectName("cardValue")
        lbl_value.setAlignment(Qt.AlignCenter)

        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)
        card.value_label = lbl_value
        return card

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {Theme.BORDER};")
        return sep

    def _set_card_value(self, card, value_text, tone=""):
        card.value_label.setText(value_text)
        set_tone(card.value_label, tone, big=False)

    # ═══════════════════════════════════════════════════
    # تولبار
    # ═══════════════════════════════════════════════════

    def _build_toolbar(self) -> QHBoxLayout:
        tb = QHBoxLayout()
        tb.setSpacing(6)

        # ─── گروه ۱: ثبت و ویرایش ───
        self.btn_add = QPushButton("➕ ثبت موقعیت جدید")
        self.btn_add.clicked.connect(self.add_position)
        self.btn_add.setToolTip("ثبت موقعیت جدید (Ctrl+N)")
        set_kind(self.btn_add, "primary")
        tb.addWidget(self.btn_add)

        self.btn_check_strategy = QPushButton("🔍 چک استراتژی جدید")
        self.btn_check_strategy.clicked.connect(
            self.check_new_strategy)
        self.btn_check_strategy.setToolTip(
            "بررسی تداخل لگ‌های استراتژی جدید با موقعیت‌های باز (Ctrl+K)")
        tb.addWidget(self.btn_check_strategy)

        tb.addSpacing(8)

        self.btn_edit = QPushButton("✏️ ویرایش")
        self.btn_edit.clicked.connect(self.edit_position)
        tb.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 حذف")
        self.btn_delete.clicked.connect(self.delete_position)
        self.btn_delete.setToolTip("حذف موقعیت")
        set_kind(self.btn_delete, "danger")
        tb.addWidget(self.btn_delete)

        tb.addSpacing(16)

        # ─── گروه ۲: ایمپورت/اکسپورت ───
        self.btn_import = QPushButton("📥 ایمپورت اکسل")
        self.btn_import.clicked.connect(self.import_from_excel)
        self.btn_import.setToolTip("ایمپورت اکسل کارگزاری (Ctrl+I)")
        tb.addWidget(self.btn_import)

        self.btn_export = QPushButton("📤 خروجی اکسل")
        self.btn_export.clicked.connect(self.export_to_excel)
        self.btn_export.setToolTip("خروجی به اکسل (Ctrl+E)")
        tb.addWidget(self.btn_export)

        self.btn_import_history = QPushButton("📋 تاریخچه ایمپورت")
        self.btn_import_history.clicked.connect(self.show_import_history)
        tb.addWidget(self.btn_import_history)

        tb.addSpacing(16)

        # ─── گروه ۳: گزارش و ارسال ───
        self.btn_report = QPushButton("📊 گزارش‌گیری")
        self.btn_report.clicked.connect(self.show_report)
        self.btn_report.setToolTip("گزارش دوره‌ای (Ctrl+R)")
        tb.addWidget(self.btn_report)

        self.btn_send_bale = QPushButton("📨 ارسال به بله")
        self.btn_send_bale.clicked.connect(self.send_positions_to_bale)
        self.btn_send_bale.setToolTip("ارسال (Ctrl+B)")
        tb.addWidget(self.btn_send_bale)

        tb.addSpacing(16)

        # ─── گروه ۴: پایش لایو ───
        self.btn_manual = QPushButton("⚡ دریافت دستی")
        self.btn_manual.clicked.connect(self.manual_refresh_data)
        tb.addWidget(self.btn_manual)

        self.chk_auto_refresh = QCheckBox("دریافت خودکار")
        self.chk_auto_refresh.setChecked(True)
        self.chk_auto_refresh.toggled.connect(self.toggle_auto_refresh)
        tb.addWidget(self.chk_auto_refresh)

        tb.addWidget(QLabel("تایمر:"))
        self.spin_timer = QSpinBox()
        self.spin_timer.setRange(5, 3600)
        self.spin_timer.setValue(10)
        self.spin_timer.setSuffix(" ثانیه")
        self.spin_timer.valueChanged.connect(self.change_timer_interval)
        tb.addWidget(self.spin_timer)

        tb.addStretch()
        return tb

    # ═══════════════════════════════════════════════════
    # تب position
    # ═══════════════════════════════════════════════════

    def _build_table_tab(self, tab_kind: str) -> Tuple[QWidget, QLabel, QLabel]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        actions_bar = self._build_tab_actions_bar(tab_kind)
        actions_bar.setFixedHeight(ACTIONS_BAR_HEIGHT)
        layout.addWidget(actions_bar)

        table = QTableWidget(0, self.N_COLS)
        table.setHorizontalHeaderLabels([
            "شناسه",
            "نام استراتژی",
            "کارگزاری",
            "نماد پایه",
            "تاریخ اجرا",
            "تاریخ سررسید",
            "روزها (سپری/کل/مانده)",
            "لنگه‌ها",
            "هزینه ورود",
            "تارگت ماهانه",
            "آستانه امروز",
            "سود/زیان لحظه‌ای",
            "ROI فعلی",
            "Pace",
            "وضعیت تارگت",
            "وضعیت",
            "منبع",
        ])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignCenter)

        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setWordWrap(False)
        table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        table.setColumnHidden(self.COL_ID, True)

        # تنظیم عرض ستون‌ها
        table.setColumnWidth(self.COL_STRATEGY, 120)
        table.setColumnWidth(self.COL_BROKER, 90)
        table.setColumnWidth(self.COL_UNDERLYING, 75)
        table.setColumnWidth(self.COL_EXEC_DATE, 80)
        table.setColumnWidth(self.COL_EXPIRY_DATE, 80)
        table.setColumnWidth(self.COL_DAYS_INFO, 130)
        table.setColumnWidth(self.COL_NET_COST, 110)
        table.setColumnWidth(self.COL_TARGET_MONTHLY, 90)
        table.setColumnWidth(self.COL_THRESHOLD, 90)
        table.setColumnWidth(self.COL_LIVE_PNL, 120)
        table.setColumnWidth(self.COL_CURRENT_ROI, 85)
        table.setColumnWidth(self.COL_PACE, 70)
        table.setColumnWidth(self.COL_TARGET_STATUS, 110)
        table.setColumnWidth(self.COL_STATUS, 130)
        table.setColumnWidth(self.COL_SOURCE, 80)

        header.setSectionResizeMode(self.COL_LEGS, QHeaderView.Stretch)

        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_context_menu(t, pos))

        # double-click برای ویرایش
        table.cellDoubleClicked.connect(
            lambda r, c: self.edit_position())

        layout.addWidget(table, 1)

        lbl_sum = QLabel("جمع: —")
        lbl_sum.setStyleSheet(
            f"color: {Theme.MUTED}; font-size: 11px; "
            f"padding: 6px 10px; background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px;")
        layout.addWidget(lbl_sum)

        lbl_empty = QLabel("📭 هنوز موقعیتی در این تب وجود ندارد")
        lbl_empty.setAlignment(Qt.AlignCenter)
        lbl_empty.setStyleSheet(
            f"color: {Theme.MUTED}; font-size: 14px; padding: 40px;")
        lbl_empty.setVisible(False)
        layout.addWidget(lbl_empty)

        return container, lbl_sum, lbl_empty

    def _build_tab_actions_bar(self, tab_kind: str) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if tab_kind == "active":
            self.btn_offset = QPushButton("🔁 آفست (بستن موقعیت باز)")
            self.btn_offset.clicked.connect(self.offset_position)
            self.btn_offset.setToolTip(
                "بستن موقعیت باز با معامله معکوس")
            set_kind(self.btn_offset, "primary")
            layout.addWidget(self.btn_offset)

        elif tab_kind == "pending":
            self.btn_cash_settle = QPushButton("📌 تسویه نقدی / نکول")
            self.btn_cash_settle.clicked.connect(self.settle_cash)
            self.btn_cash_settle.setToolTip(
                "ثبت تسویه نقدی یا نکول CALL")
            set_kind(self.btn_cash_settle, "primary")
            layout.addWidget(self.btn_cash_settle)

            self.btn_exercise = QPushButton("🏦 اعمال فیزیکی")
            self.btn_exercise.clicked.connect(self.settle_exercise)
            layout.addWidget(self.btn_exercise)

            self.btn_manual_close = QPushButton("✏️ بستن دستی")
            self.btn_manual_close.clicked.connect(self.close_manually)
            layout.addWidget(self.btn_manual_close)

            self.btn_default = QPushButton("⚖️ نکول CALL")
            self.btn_default.clicked.connect(self.register_default)
            set_kind(self.btn_default, "danger")
            layout.addWidget(self.btn_default)

        elif tab_kind == "history":
            lbl_hint = QLabel(
                "ℹ️ این تب برای مشاهده و ویرایش تاریخچه است — "
                "برای ویرایش، ردیف را دابل‌کلیک کنید")
            lbl_hint.setStyleSheet(
                f"color: {Theme.MUTED}; font-size: 11px; "
                f"padding: 4px 10px; "
                f"background-color: {Theme.CARD}; "
                f"border: 1px solid {Theme.BORDER}; "
                f"border-radius: 4px;")
            lbl_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(lbl_hint)

        layout.addStretch()
        return w

    # ═══════════════════════════════════════════════════
    # منوی راست‌کلیک
    # ═══════════════════════════════════════════════════

    def _show_context_menu(self, table: QTableWidget, pos):
        """منوی راست‌کلیک با ترتیب منطقی."""
        has_selection = bool(table.selectedIndexes())
        menu = QMenu(self)

        action_edit = None
        action_delete = None
        action_offset = None
        action_settle = None
        action_exercise = None
        action_close = None
        action_bale = None

        if has_selection:
            # ─── اکشن‌های اصلی ───
            action_edit = menu.addAction("✏️ ویرایش")
            action_delete = menu.addAction("🗑 حذف")

            menu.addSeparator()

            # ─── اکشن‌های مخصوص تب ───
            idx = self.tabs.currentIndex()
            if idx == TAB_ACTIVE:
                action_offset = menu.addAction("🔁 آفست")
                action_settle = menu.addAction("📌 تسویه نقدی")
            elif idx == TAB_PENDING:
                action_settle = menu.addAction("📌 تسویه/نکول")
                action_exercise = menu.addAction("🏦 اعمال فیزیکی")
                action_close = menu.addAction("✏️ بستن دستی")

            menu.addSeparator()

            # ─── ابزار ───
            action_bale = menu.addAction("📨 ارسال به بله")

        # ─── اکشن‌های عمومی (همیشه) ───
        if has_selection:
            menu.addSeparator()

        action_add = menu.addAction("➕ ثبت موقعیت جدید")
        action_check = menu.addAction("🔍 چک استراتژی جدید")
        action_import = menu.addAction("📥 ایمپورت اکسل")
        action_report = menu.addAction("📊 گزارش‌گیری")

        menu.addSeparator()

        action_history = menu.addAction("📋 تاریخچه ایمپورت‌ها")

        chosen = menu.exec(table.viewport().mapToGlobal(pos))

        if chosen is None:
            return

        # ─── اجرای اکشن ───
        if chosen == action_add:
            self.add_position()
        elif chosen == action_check:
            self.check_new_strategy()
        elif chosen == action_import:
            self.import_from_excel()
        elif chosen == action_report:
            self.show_report()
        elif chosen == action_history:
            self.show_import_history()
        elif action_edit and chosen == action_edit:
            self.edit_position()
        elif action_delete and chosen == action_delete:
            self.delete_position()
        elif action_offset and chosen == action_offset:
            self.offset_position()
        elif action_settle and chosen == action_settle:
            self.settle_cash()
        elif action_exercise and chosen == action_exercise:
            self.settle_exercise()
        elif action_close and chosen == action_close:
            self.close_manually()
        elif action_bale and chosen == action_bale:
            self.send_positions_to_bale()

    # ═══════════════════════════════════════════════════
    # فیلترها
    # ═══════════════════════════════════════════════════

    def _is_pending_settlement(self, pos: StrategyPosition) -> bool:
        return (
            pos.status == PositionStatus.OPEN
            and bool(pos.expiry_date)
            and is_expired_date(pos.expiry_date)
        )

    def _get_active_positions(self) -> List[StrategyPosition]:
        return [
            p for p in self.positions
            if p.status == PositionStatus.OPEN
            and not self._is_pending_settlement(p)
        ]

    def _get_pending_positions(self) -> List[StrategyPosition]:
        return [p for p in self.positions
                if self._is_pending_settlement(p)]

    def _get_history_positions(self) -> List[StrategyPosition]:
        return [p for p in self.positions
                if p.status != PositionStatus.OPEN]

    # ═══════════════════════════════════════════════════
    # Snapshot
    # ═══════════════════════════════════════════════════

    def _get_market_snapshot(self, force_refresh: bool = False):
        try:
            if not force_refresh and self._market_snapshot is not None:
                return self._market_snapshot
            self._market_snapshot = get_market_snapshot(
                use_cache=True, force_refresh=force_refresh)
            return self._market_snapshot
        except Exception as e:
            logger.warning(f"Snapshot failed: {e}")
            return None

    def _invalidate_snapshot(self):
        self._market_snapshot = None

    # ═══════════════════════════════════════════════════
    # اسلات‌های ترد
    # ═══════════════════════════════════════════════════

    def toggle_auto_refresh(self, checked: bool):
        self.monitor_thread.set_auto_refresh(checked)
        self._show_status(
            "دریافت خودکار " + ("فعال" if checked else "غیرفعال"))

    def change_timer_interval(self, value: int):
        self.monitor_thread.set_interval(value)
        self._show_status(f"تایمر روی {value} ثانیه تنظیم شد")

    def manual_refresh_data(self):
        self.monitor_thread.trigger_manual_refresh()
        self._show_status("درخواست دریافت دستی ارسال شد...")

    @Slot(dict)
    def on_prices_updated(self, payload: dict):
        """
        به‌روزرسانی قیمت‌ها — بدون save_positions (فقط RAM).
        """
        prices = payload.get("prices", {})
        self._invalidate_snapshot()

        for pos in self.positions:
            if pos.status != PositionStatus.OPEN:
                continue
            for leg in pos.legs:
                if leg.symbol in prices:
                    leg.current_price = prices[leg.symbol]
            if pos.underlying_symbol in prices:
                pos.underlying_price = prices[pos.underlying_symbol]

        self.refresh_all_tabs()

    @Slot(list)
    def on_alerts_found(self, alerts: list):
        """آلرت‌های پویا دریافت و ارسال."""
        for alert in alerts:
            pid = alert.get("position_id", "")
            if pid:
                self._alerted_position_ids.add(pid)
            self.monitor_thread.send_bale_alert(alert)

        if alerts:
            self.refresh_all_tabs()
            self._show_status(
                f"🎯 {len(alerts)} آلرت پویا ارسال شد", 8000)

    @Slot(list)
    def on_expired_found(self, position_ids: list):
        new_ids = [pid for pid in position_ids
                   if pid not in self._expired_alerted]
        if not new_ids:
            return
        self._expired_alerted.update(new_ids)
        self._update_tab_badges()
        self._show_status(
            f"⚠️ {len(new_ids)} موقعیت منقضی شد — "
            f"به تب «نیازمند تعیین تکلیف» بروید", 8000)

    @Slot(dict)
    def on_connection_status(self, status: dict):
        ok = status.get("ok", False)
        message = status.get("message", "")
        timestamp = status.get("timestamp")
        ts_str = timestamp.strftime("%H:%M:%S") if timestamp else "—"

        if ok:
            self._last_success_time = timestamp
            self._show_status(f"🟢 {ts_str} — {message}", 4000)
        else:
            last_ok = self._last_success_time.strftime("%H:%M:%S") \
                if self._last_success_time else "—"
            self._show_status(
                f"🔴 {ts_str} — {message} (آخرین موفق: {last_ok})",
                8000)

    # ═══════════════════════════════════════════════════
    # بارگذاری
    # ═══════════════════════════════════════════════════

    def load_data(self):
        self.positions = self.storage.load_positions()
        self.refresh_all_tabs()

    def refresh_all_tabs(self):
        self._populate_table(
            self.tab_active, self._get_active_positions())
        self._populate_table(
            self.tab_pending, self._get_pending_positions())
        self._populate_table(
            self.tab_history, self._get_history_positions())
        self._update_tab_badges()
        self._update_summary()

    # ═══════════════════════════════════════════════════
    # ساخت آیتم‌ها
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _make_text_item(text: str, color: str = None) -> SortableItem:
        item = SortableItem(str(text), str(text))
        item.setToolTip(str(text))
        if color:
            item.setForeground(QColor(color))
        return item

    @staticmethod
    def _make_number_item(display_text: str, value: float,
                          color: str = None) -> SortableItem:
        item = SortableItem(display_text, float(value))
        item.setToolTip(display_text)
        if color:
            item.setForeground(QColor(color))
        return item

    # ═══════════════════════════════════════════════════
    # پر کردن جدول position
    # ═══════════════════════════════════════════════════

    def _populate_table(self, container: QWidget,
                        positions: List[StrategyPosition]):
        table = container.findChild(QTableWidget)
        if table is None:
            return

        # حفظ selection
        selected_ids = set()
        for idx in table.selectedIndexes():
            id_item = table.item(idx.row(), self.COL_ID)
            if id_item:
                selected_ids.add(id_item.text())

        scroll_pos = table.verticalScrollBar().value()
        sort_col = table.horizontalHeader().sortIndicatorSection()
        sort_order = table.horizontalHeader().sortIndicatorOrder()

        table.setSortingEnabled(False)
        table.setRowCount(0)

        for idx, pos in enumerate(positions):
            row = table.rowCount()
            table.insertRow(row)
            self._fill_row(table, row, pos, idx)

        # sort قبل از selection
        table.setSortingEnabled(True)
        if sort_col >= 0:
            table.sortItems(sort_col, sort_order)
        table.verticalScrollBar().setValue(scroll_pos)

        # انتخاب چندگانه
        if selected_ids:
            table.clearSelection()
            for r in range(table.rowCount()):
                id_item = table.item(r, self.COL_ID)
                if id_item and id_item.text() in selected_ids:
                    idx_m = table.model().index(r, 0)
                    table.selectionModel().select(
                        idx_m,
                        QItemSelectionModel.Select
                        | QItemSelectionModel.Rows)

        self._update_tab_summary(container, positions)

    def _fill_row(self, table: QTableWidget, row: int,
                  pos: StrategyPosition, idx: int):
        """پر کردن یک ردیف با تمام ستون‌ها."""

        # ─── محاسبات ───
        try:
            net_cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
            live_pnl, live_roi = \
                PositionPnLCalculator.calculate_live_pnl(pos)
            realized_pnl, realized_roi = \
                PositionPnLCalculator.calculate_realized_pnl(pos)
        except Exception as e:
            logger.warning(f"PnL calc failed for {pos.position_id}: {e}")
            net_cost = 0.0
            live_pnl, live_roi = 0.0, 0.0
            realized_pnl, realized_roi = 0.0, 0.0

        # ─── روزها ───
        d_elapsed = pos.days_elapsed()
        d_total = pos.total_days()
        d_remaining = max(0, d_total - d_elapsed)

        # ─── آستانه‌ی پویا ───
        threshold = SharedAnalytics.calculate_dynamic_threshold(
            pos.target_roi_maturity, d_elapsed)

        # ─── Pace ───
        pace = 0.0
        if threshold > 0:
            if pos.status == PositionStatus.OPEN:
                pace = live_roi / threshold
            else:
                pace = realized_roi / threshold

        # ─── لگ‌ها ───
        legs_str = " | ".join([
            f"{l.leg_type.label_fa}: {l.symbol}" for l in pos.legs
        ])

        # ─── ستون‌ها ───
        table.setItem(row, self.COL_ID,
                      self._make_text_item(pos.position_id))

        table.setItem(row, self.COL_STRATEGY,
                      self._make_text_item(pos.strategy_name))
        table.setItem(row, self.COL_BROKER,
                      self._make_text_item(pos.broker_name or "—"))
        table.setItem(row, self.COL_UNDERLYING,
                      self._make_text_item(pos.underlying_symbol))
        table.setItem(row, self.COL_EXEC_DATE,
                      self._make_text_item(pos.execution_date))
        table.setItem(row, self.COL_EXPIRY_DATE,
                      self._make_text_item(pos.expiry_date))

        # ─── روزها (سپری/کل/مانده) ───
        days_text = f"{d_elapsed} / {d_total} / {d_remaining}"
        days_color = self._days_color(d_remaining) \
            if pos.status == PositionStatus.OPEN else Theme.MUTED
        days_item = SortableItem(days_text, float(d_remaining))
        days_item.setTextAlignment(Qt.AlignCenter)
        days_item.setToolTip(
            f"سپری: {d_elapsed} روز | کل: {d_total} روز | "
            f"مانده: {d_remaining} روز")
        days_item.setForeground(QColor(days_color))
        table.setItem(row, self.COL_DAYS_INFO, days_item)

        table.setItem(row, self.COL_LEGS,
                      self._make_text_item(legs_str))
        table.setItem(row, self.COL_NET_COST,
                      self._make_number_item(
                          fmt_money(net_cost), net_cost))

        # ─── تارگت ماهانه ───
        target = pos.target_roi_maturity
        if target > 0:
            target_item = self._make_number_item(
                fmt_pct(target, digits=1, signed=False),
                target,
                Theme.PRIMARY)
        else:
            target_item = self._make_number_item(
                "—", 0.0, Theme.MUTED)
        target_item.setToolTip(
            f"تارگت ماهانه: {fmt_pct(target, digits=1, signed=False)}")
        table.setItem(row, self.COL_TARGET_MONTHLY, target_item)

        # ─── آستانه‌ی امروز ───
        if threshold > 0:
            threshold_item = self._make_number_item(
                fmt_pct(threshold, digits=2, signed=False),
                threshold,
                Theme.INFO)
            threshold_item.setToolTip(
                f"آستانه‌ی امروز: "
                f"{fmt_pct(threshold, digits=2, signed=False)}\n"
                f"فرمول: target × (d/30) = {target:.1f}% × "
                f"({d_elapsed}/30)")
        else:
            threshold_item = self._make_number_item(
                "—", 0.0, Theme.MUTED)
        table.setItem(row, self.COL_THRESHOLD, threshold_item)

        # ─── سود/زیان ───
        current_roi = 0.0
        if pos.status == PositionStatus.OPEN:
            if self._is_pending_settlement(pos):
                pnl_text = "⚠️ منقضی - تسویه کنید"
                pnl_item = SortableItem(pnl_text, -999999999.0)
                pnl_item.setTextAlignment(Qt.AlignCenter)
                pnl_item.setToolTip(pnl_text)
                pnl_item.setForeground(QColor(Theme.WARN))
                current_roi = 0.0
            else:
                pnl_text = fmt_money(live_pnl)
                pnl_item = SortableItem(pnl_text, float(live_pnl))
                pnl_item.setTextAlignment(Qt.AlignCenter)
                pnl_item.setToolTip(
                    f"سود/زیان لایو: {fmt_money(live_pnl)} {CURRENCY}")
                pnl_item.setForeground(
                    QColor(self._tone_color(pnl_tone(live_pnl))))
                current_roi = live_roi
        else:
            pnl_text = fmt_money(realized_pnl)
            pnl_item = SortableItem(pnl_text, float(realized_pnl))
            pnl_item.setTextAlignment(Qt.AlignCenter)
            pnl_item.setToolTip(
                f"سود/زیان محقق‌شده: {fmt_money(realized_pnl)} "
                f"{CURRENCY}")
            pnl_item.setForeground(
                QColor(self._tone_color(pnl_tone(realized_pnl))))
            current_roi = realized_roi

        table.setItem(row, self.COL_LIVE_PNL, pnl_item)

        # ─── ROI فعلی ───
        roi_item = self._make_number_item(
            fmt_pct(current_roi, digits=2),
            current_roi,
            self._tone_color(pnl_tone(current_roi)))
        roi_item.setToolTip(
            f"ROI فعلی: {fmt_pct(current_roi, digits=2)}")
        table.setItem(row, self.COL_CURRENT_ROI, roi_item)

        # ─── Pace ───
        if threshold > 0 and pos.status == PositionStatus.OPEN:
            pace_text = f"{pace:.2f}x"
            if pace >= PACE_HIT:
                pace_color = Theme.PROFIT
            elif pace >= PACE_NEAR:
                pace_color = Theme.WARN
            elif pace >= 0:
                pace_color = Theme.INFO
            else:
                pace_color = Theme.LOSS

            pace_item = SortableItem(pace_text, float(pace))
            pace_item.setTextAlignment(Qt.AlignCenter)
            pace_item.setToolTip(
                f"Pace = ROI / آستانه = {pace:.2f}x\n"
                f"{'🎯 رسید' if pace >= PACE_HIT else ('🟡 نزدیک' if pace >= PACE_NEAR else '🔵 دور')}")
            pace_item.setForeground(QColor(pace_color))
        else:
            pace_item = SortableItem("—", -1.0)
            pace_item.setTextAlignment(Qt.AlignCenter)
            pace_item.setToolTip("آستانه تنظیم نشده")
            pace_item.setForeground(QColor(Theme.MUTED))
        table.setItem(row, self.COL_PACE, pace_item)

        # ─── وضعیت تارگت ───
        is_open = pos.status == PositionStatus.OPEN
        status_text, status_color, status_sort = \
            SharedAnalytics.get_target_status(
                current_roi=current_roi,
                monthly_target=target,
                days_elapsed=d_elapsed,
                is_open=is_open,
            )
        target_status_item = SortableItem(status_text, status_sort)
        target_status_item.setTextAlignment(Qt.AlignCenter)
        target_status_item.setToolTip(status_text)
        target_status_item.setForeground(QColor(status_color))
        table.setItem(row, self.COL_TARGET_STATUS, target_status_item)

        # ─── وضعیت ───
        status_text_main = pos.status.label_fa
        status_color_main = self._status_color(pos.status.value)

        if self._is_pending_settlement(pos):
            status_text_main = "⚠️ منقضی (تعیین تکلیف)"
            status_color_main = Theme.WARN

        if pos.needs_review or pos.has_incomplete_legs:
            status_text_main = "⚠️ " + status_text_main
            status_color_main = Theme.WARN

        table.setItem(row, self.COL_STATUS,
                      self._make_text_item(status_text_main,
                                            status_color_main))

        # ─── منبع ───
        source_text = "📥 ایمپورت" if pos.source == "excel_import" \
            else "✏️ دستی"
        source_color = Theme.PRIMARY if pos.source == "excel_import" \
            else Theme.MUTED
        table.setItem(row, self.COL_SOURCE,
                      self._make_text_item(source_text, source_color))

    # ═══════════════════════════════════════════════════
    # رنگ‌ها
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _tone_color(tone: str) -> str:
        return {
            "profit": Theme.PROFIT, "loss": Theme.LOSS,
            "warn": Theme.WARN, "muted": Theme.MUTED,
            "primary": Theme.PRIMARY, "neutral": Theme.TEXT,
        }.get(tone, Theme.TEXT)

    @staticmethod
    def _days_color(days: int) -> str:
        if days <= DAY_CRITICAL_THRESHOLD:
            return Theme.LOSS
        if days <= DAY_WARN_THRESHOLD:
            return Theme.WARN
        return Theme.MUTED

    @staticmethod
    def _status_color(status_value: str) -> str:
        return {
            "open": Theme.PROFIT, "closed": Theme.MUTED,
            "exercised": Theme.PRIMARY, "cash_settled": Theme.PROFIT,
            "defaulted": Theme.LOSS, "you_defaulted": Theme.LOSS,
        }.get(status_value, Theme.TEXT)

    # ═══════════════════════════════════════════════════
    # جمع و حالت خالی
    # ═══════════════════════════════════════════════════

    def _update_tab_summary(self, container: QWidget,
                            positions: List[StrategyPosition]):
        labels = container.findChildren(QLabel)
        if len(labels) < 2:
            return
        lbl_sum, lbl_empty = labels[0], labels[1]
        table = container.findChild(QTableWidget)

        if not positions:
            if table:
                table.setVisible(False)
            lbl_sum.setVisible(False)
            lbl_empty.setVisible(True)
            return

        if table:
            table.setVisible(True)
        lbl_empty.setVisible(False)
        lbl_sum.setVisible(True)

        total_pnl = 0.0
        total_cost = 0.0
        alert_count = 0

        for pos in positions:
            if self._is_pending_settlement(pos):
                continue
            try:
                if pos.status == PositionStatus.OPEN:
                    pnl, roi = \
                        PositionPnLCalculator.calculate_live_pnl(pos)
                    if pos.target_roi_maturity > 0:
                        threshold = SharedAnalytics.calculate_dynamic_threshold(
                            pos.target_roi_maturity, pos.days_elapsed())
                        if threshold > 0 and roi >= threshold:
                            alert_count += 1
                else:
                    pnl, _ = \
                        PositionPnLCalculator.calculate_realized_pnl(pos)
                cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
                total_pnl += pnl
                total_cost += cost
            except Exception as e:
                logger.warning(
                    f"summary calc failed for "
                    f"{pos.position_id}: {e}")

        text = (f"جمع: {len(positions)} موقعیت  |  "
                f"سود/زیان: {fmt_money(total_pnl)} {CURRENCY}  |  "
                f"هزینه: {fmt_money(total_cost)} {CURRENCY}")
        if alert_count > 0:
            text += f"  |  🎯 {alert_count} آلرت فعال"

        lbl_sum.setText(text)

        color = self._tone_color(pnl_tone(total_pnl))
        lbl_sum.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 6px 10px; "
            f"background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px;")

    # ═══════════════════════════════════════════════════
    # کارت‌های سرجمع
    # ═══════════════════════════════════════════════════

    def _update_summary(self):
        """به‌روزرسانی کارت‌های خلاصه."""
        sum_open = 0.0
        sum_realized = 0.0
        active_count = 0
        alert_count = 0
        nearest_days = None

        for pos in self.positions:
            try:
                if pos.status == PositionStatus.OPEN:
                    if self._is_pending_settlement(pos):
                        continue
                    pnl, roi = \
                        PositionPnLCalculator.calculate_live_pnl(pos)
                    if pnl != pnl:  # NaN check
                        pnl = 0.0
                    sum_open += pnl
                    active_count += 1

                    # بررسی آلرت پویا
                    if pos.target_roi_maturity > 0:
                        threshold = SharedAnalytics.calculate_dynamic_threshold(
                            pos.target_roi_maturity,
                            pos.days_elapsed())
                        if threshold > 0 and roi >= threshold:
                            alert_count += 1

                    days = self._calc_days_left(pos.expiry_date)
                    if days is not None and days >= 0:
                        if nearest_days is None or days < nearest_days:
                            nearest_days = days
                else:
                    pnl, _ = \
                        PositionPnLCalculator.calculate_realized_pnl(pos)
                    if pnl != pnl:
                        pnl = 0.0
                    sum_realized += pnl
            except Exception as e:
                logger.warning(
                    f"Summary failed for {pos.position_id}: {e}")

        total = sum_open + sum_realized

        self._set_card_value(
            self.card_open_pnl,
            f"{fmt_money(sum_open)} {CURRENCY}",
            pnl_tone(sum_open))
        self._set_card_value(
            self.card_realized_pnl,
            f"{fmt_money(sum_realized)} {CURRENCY}",
            pnl_tone(sum_realized))
        self._set_card_value(
            self.card_total_pnl,
            f"{fmt_money(total)} {CURRENCY}",
            pnl_tone(total))
        self._set_card_value(
            self.card_count, str(active_count), "primary")

        # کارت آلرت‌ها
        alert_tone = "warn" if alert_count > 0 else "muted"
        self._set_card_value(
            self.card_alerts, str(alert_count), alert_tone)

        if nearest_days is None:
            self._set_card_value(self.card_nearest, "—", "muted")
        else:
            tone = ("loss" if nearest_days <= DAY_CRITICAL_THRESHOLD
                    else ("warn" if nearest_days <= DAY_WARN_THRESHOLD
                          else "muted"))
            self._set_card_value(self.card_nearest,
                                 f"{nearest_days} روز", tone)

    def _calc_days_left(self, expiry_date_str: str) -> Optional[int]:
        """محاسبه‌ی روزهای باقی‌مانده تا سررسید."""
        if not expiry_date_str:
            return None
        try:
            s = str(expiry_date_str).strip()
            m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
            if not m:
                return None
            expiry = jdatetime.date(
                int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return (expiry - jdatetime.date.today()).days
        except Exception:
            return None

    # ═══════════════════════════════════════════════════
    # عملیات CRUD — Position
    # ═══════════════════════════════════════════════════

    def _current_table(self) -> Optional[QTableWidget]:
        container = self.tabs.currentWidget()
        if container:
            return container.findChild(QTableWidget)
        return None

    def _get_selected_positions(self) -> List[StrategyPosition]:
        """گرفتن موقعیت‌های انتخاب‌شده."""
        table = self._current_table()
        if table is None:
            return []

        rows = sorted(set(i.row() for i in table.selectedIndexes()))
        positions, seen = [], set()

        for row in rows:
            id_item = table.item(row, self.COL_ID)
            if id_item is None:
                continue
            pid = id_item.text()
            if pid in seen:
                continue
            seen.add(pid)
            for pos in self.positions:
                if pos.position_id == pid:
                    positions.append(pos)
                    break

        return positions

    def _get_selected_position(self) -> Optional[StrategyPosition]:
        p = self._get_selected_positions()
        return p[0] if p else None

    def add_position(self):
        """ثبت موقعیت جدید."""
        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(
            self,
            snapshot=snapshot,
            storage=self.storage,
        )
        try:
            if dlg.exec():
                self.positions.append(dlg.position)
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
                self._show_status(
                    f"✅ موقعیت {dlg.position.position_id} ثبت شد")
        finally:
            dlg.deleteLater()

    def edit_position(self):
        """
        ویرایش موقعیت — برای OPEN و CLOSED.
        """
        pos = self._get_selected_position()
        if pos is None:
            self._show_status("⚠️ ابتدا یک موقعیت را انتخاب کنید")
            return

        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(
            self, pos, snapshot=snapshot, storage=self.storage)
        try:
            if dlg.exec():
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
                self._show_status(
                    f"✅ موقعیت {pos.position_id} ویرایش شد")
        finally:
            dlg.deleteLater()

    def delete_position(self):
        """حذف موقعیت با تأیید دوگانه."""
        pos = self._get_selected_position()
        if pos is None:
            self._show_status("⚠️ ابتدا یک موقعیت را انتخاب کنید")
            return

        # ─── تأیید اول ───
        reply = QMessageBox.question(
            self, "تأیید حذف",
            f"آیا از حذف موقعیت زیر اطمینان دارید؟\n\n"
            f"شناسه: {pos.position_id}\n"
            f"استراتژی: {pos.strategy_name}\n"
            f"وضعیت: {pos.status.label_fa}",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # ─── تأیید دوم ───
        reply2 = QMessageBox.warning(
            self, "⚠️ تأیید نهایی",
            f"این عمل قابل بازگشت نیست!\n\n"
            f"شناسه: {pos.position_id}\n\n"
            f"اگر بعداً نیاز داشتید، باید موقعیت را دوباره وارد "
            f"کنید.\n"
            f"ادامه؟",
            QMessageBox.Yes | QMessageBox.No)
        if reply2 != QMessageBox.Yes:
            return

        self.positions = [
            p for p in self.positions
            if p.position_id != pos.position_id
        ]
        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        self._show_status(
            f"🗑 موقعیت {pos.position_id} حذف شد")

    # ═══════════════════════════════════════════════════
    # Import / Export
    # ═══════════════════════════════════════════════════

    def import_from_excel(self):
        """اجرای Wizard ایمپورت."""
        try:
            from position_saver.ui.import_wizard_dialog import (
                ImportWizardDialog,
            )
        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"Wizard ایمپورت در دسترس نیست:\n{e}")
            return

        dlg = ImportWizardDialog(parent=self, storage=self.storage)
        try:
            if dlg.exec():
                self.load_data()
                self._show_status(
                    "✅ ایمپورت اکسل انجام شد", 8000)
        finally:
            dlg.deleteLater()

    def show_import_history(self):
        """نمایش تاریخچه‌ی ایمپورت‌ها."""
        dlg = ImportHistoryDialog(parent=self, storage=self.storage)
        try:
            if dlg.exec():
                self.load_data()
                self._show_status("تاریخچه به‌روز شد")
        finally:
            dlg.deleteLater()

    def show_report(self):
        """باز کردن دیالوگ گزارش‌گیری."""
        try:
            from position_saver.ui.report_dialog import ReportDialog
        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"دیالوگ گزارش در دسترس نیست:\n{e}")
            return

        dlg = ReportDialog(
            parent=self,
            positions=self.positions,
        )
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    def check_new_strategy(self):
        """باز کردن پنجره‌ی چک استراتژی جدید."""
        try:
            from position_saver.ui.strategy_check_dialog import (
                StrategyCheckDialog)
        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"پنجره‌ی چک استراتژی در دسترس نیست:\n{e}")
            return

        snapshot = self._get_market_snapshot()
        dlg = StrategyCheckDialog(
            self,
            storage=self.storage,
            snapshot=snapshot,
        )
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    def export_to_excel(self):
        """خروجی اکسل."""
        if not self.positions:
            self._show_status("⚠️ موقعیتی برای خروجی وجود ندارد")
            return

        default_name = (
            f"positions_export_"
            f"{jdatetime.date.today().strftime('%Y%m%d')}.xlsx")

        file_path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره خروجی اکسل", default_name,
            "Excel Files (*.xlsx)")
        if not file_path:
            return

        try:
            active = (self._get_active_positions()
                      + self._get_pending_positions())
            history = self._get_history_positions()

            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                if active:
                    df = PositionStorage.positions_to_dataframe(active)
                    df.to_excel(writer,
                                sheet_name="Active_Positions",
                                index=False)
                else:
                    pd.DataFrame(columns=["پیام"]).to_excel(
                        writer, sheet_name="Active_Positions",
                        index=False)

                if history:
                    df = PositionStorage.positions_to_dataframe(
                        history)
                    df.to_excel(writer,
                                sheet_name="Closed_Positions",
                                index=False)
                else:
                    pd.DataFrame(columns=["پیام"]).to_excel(
                        writer, sheet_name="Closed_Positions",
                        index=False)

            self._show_status(
                f"✅ اکسل ذخیره شد — باز: {len(active)} | "
                f"بسته: {len(history)}", 8000)

        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"openpyxl نصب نیست.\n\npip install openpyxl\n\n{e}")
        except Exception as e:
            QMessageBox.critical(
                self, "خطا", f"خطا در ذخیره اکسل:\n{e}")

    # ═══════════════════════════════════════════════════
    # ارسال به بله
    # ═══════════════════════════════════════════════════

    def send_positions_to_bale(self):
        """ارسال گزارش موقعیت‌ها به بله."""
        positions = self._get_selected_positions()
        if not positions:
            self._show_status("⚠️ ابتدا یک یا چند موقعیت انتخاب کنید")
            return

        if not self.monitor_thread.notifier.is_configured:
            QMessageBox.warning(
                self, "خطا",
                "تنظیمات بله کامل نیست.")
            return

        n = len(positions)
        if n == 1:
            msg = (f"آیا گزارش موقعیت زیر به بله ارسال شود؟\n\n"
                   f"شناسه: {positions[0].position_id}\n"
                   f"استراتژی: {positions[0].strategy_name}")
        else:
            ids = "\n".join(
                f"  • {p.position_id} ({p.strategy_name})"
                for p in positions[:10])
            if n > 10:
                ids += f"\n  ... و {n - 10} مورد دیگر"
            msg = f"آیا گزارش {n} موقعیت زیر ارسال شود؟\n\n{ids}"

        if QMessageBox.question(
                self, "تأیید ارسال", msg,
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        success = 0
        for pos in positions:
            try:
                if self.monitor_thread.send_position_report(pos):
                    success += 1
            except Exception as e:
                logger.exception(f"Bale send error: {e}")

        if success == n:
            self._show_status(
                f"✅ همه {success} موقعیت ارسال شدند")
        elif success > 0:
            self._show_status(f"⚠️ {success} از {n} ارسال شد")
        else:
            QMessageBox.critical(
                self, "خطا",
                f"❌ ارسال هیچ‌کدام از {n} موفق نبود.")

    # ═══════════════════════════════════════════════════
    # آفست
    # ═══════════════════════════════════════════════════

    def offset_position(self):
        """آفست تک-موقعیت."""
        pos = self._get_selected_position()
        if pos is None:
            self._show_status("⚠️ ابتدا یک موقعیت را انتخاب کنید")
            return
        if pos.status != PositionStatus.OPEN:
            QMessageBox.warning(
                self, "خطا",
                f"وضعیت «{pos.status.label_fa}» است.")
            return
        if self._is_pending_settlement(pos):
            QMessageBox.warning(
                self, "خطا",
                "این موقعیت منقضی شده است.")
            return

        dlg = OffsetDialog(self, pos)
        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return

            for i, leg in enumerate(pos.legs):
                cp = result["close_prices"][i]
                leg.close_price = float(cp)
                leg.close_fee = \
                    PositionPnLCalculator.calculate_leg_close_fee(
                        leg, float(cp))

            pos.status = PositionStatus.CLOSED
            pos.close_date = (
                jdatetime.date.today().strftime("%Y/%m/%d"))
            pos.close_reason = "offset"

            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()

            pnl = result["realized_pnl"]
            roi = result["realized_roi"]
            self._show_status(
                f"✅ {pos.position_id} آفست شد — "
                f"سود/زیان: {fmt_money(pnl)} {CURRENCY} "
                f"({fmt_pct(roi, digits=2)})", 8000)
        finally:
            dlg.deleteLater()

    # ═══════════════════════════════════════════════════
    # تسویه / نکول / اعمال / بستن
    # ═══════════════════════════════════════════════════

    def settle_cash(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            self._show_status("⚠️ یک موقعیت منقضی انتخاب کنید")
            return

        dlg = CashSettlementDialog(self, pos, default_mode="cash")
        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return
            mode = result.get("mode")
            if mode == "cash":
                self._apply_cash_settlement(
                    pos, result.get("amount", 0))
            elif mode in ("default", "you_default"):
                self._apply_default_settlement(pos, result)
        finally:
            dlg.deleteLater()

    def register_default(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            self._show_status("⚠️ یک موقعیت منقضی انتخاب کنید")
            return
        if not any(l.is_call for l in pos.legs):
            QMessageBox.warning(
                self, "خطا",
                "این موقعیت CALL ندارد.")
            return

        dlg = CashSettlementDialog(
            self, pos, default_mode="default")
        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return
            if result.get("mode") in ("default", "you_default"):
                self._apply_default_settlement(pos, result)
            else:
                self._apply_cash_settlement(
                    pos, result.get("amount", 0))
        finally:
            dlg.deleteLater()

    def _apply_cash_settlement(self, pos: StrategyPosition,
                                amount: float):
        pos.cash_settlement_amount = float(amount)
        pos.status = PositionStatus.CASH_SETTLED
        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")
        pos.close_reason = "cash_settle"

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        self._show_status(
            f"✅ تسویه نقدی {pos.position_id} — "
            f"مبلغ: {fmt_money(amount)} {CURRENCY}", 6000)

    def _apply_default_settlement(self, pos: StrategyPosition,
                                   result: dict):
        S_T = result.get("S_T", 0)
        exercise_rate = result.get("exercise_rate", 0.0005)
        mode = result.get("mode")
        is_self_default = (mode == "you_default")

        for leg in pos.legs:
            if not leg.is_call:
                if leg.is_stock and leg.close_price is None:
                    leg.close_price = float(S_T)
                    leg.close_fee = 0.0
                elif leg.close_price is None:
                    leg.close_price = 0.0
                    leg.close_fee = 0.0
                continue

            r = PositionPnLCalculator.calculate_call_default(
                leg, S_T,
                exercise_rate=exercise_rate,
                is_self_default=is_self_default,
            )
            if not r["valid"]:
                continue

            leg.is_defaulted = True
            leg.default_penalty = r["penalty"]
            leg.default_payment = r["payment"]
            leg.settlement_price = S_T
            leg.close_price = r["effective_price"]
            leg.close_fee = r["exercise_fee"]

        if mode == "default":
            pos.status = PositionStatus.DEFAULTED
            pos.close_reason = "defaulted"
        elif mode == "you_default":
            pos.status = PositionStatus.YOU_DEFAULTED
            pos.close_reason = "you_defaulted"

        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        self._show_status(
            f"✅ نکول {pos.position_id} — "
            f"S_T: {fmt_money(S_T)}", 6000)

    def settle_exercise(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            self._show_status("⚠️ یک موقعیت منقضی انتخاب کنید")
            return

        S_T = pos.underlying_price or 0.0
        try:
            snapshot = self._get_market_snapshot()
            if snapshot is not None:
                ua = snapshot.get_underlying_assets(
                    pos.underlying_symbol)
                if ua is not None and hasattr(ua, 'close_price') \
                        and ua.close_price > 0:
                    S_T = float(ua.close_price)
        except Exception:
            pass

        if S_T <= 0:
            QMessageBox.warning(
                self, "خطا",
                f"قیمت پایانی «{pos.underlying_symbol}» "
                f"در دسترس نیست.")
            return

        total_intrinsic = 0.0
        details = []
        for leg in pos.legs:
            if not leg.is_option:
                continue
            r = PositionPnLCalculator.calculate_exercise_total(
                leg, S_T)
            total_intrinsic += r["total_value"]
            details.append(
                f"  • {leg.symbol}: "
                + (fmt_money(r['intrinsic_per_share'])
                   if r["is_itm"] else "OTM (صفر)"))

        if QMessageBox.question(
                self, "تأیید اعمال فیزیکی",
                f"آیا اعمال فیزیکی {pos.position_id} را "
                f"تأیید می‌کنید؟\n\n"
                f"📊 قیمت پایانی: {fmt_money(S_T)}\n"
                f"💰 ارزش ذاتی کل: {fmt_money(total_intrinsic)} "
                f"{CURRENCY}\n\n"
                f"جزئیات:\n" + "\n".join(details),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        for leg in pos.legs:
            if not leg.is_option:
                if leg.close_price is None:
                    leg.close_price = float(S_T)
                    leg.close_fee = 0.0
                continue
            K = leg.strike_price
            intrinsic = (max(0.0, S_T - K) if leg.is_call
                         else max(0.0, K - S_T))
            leg.close_price = float(intrinsic)
            leg.close_fee = 0.0

        pos.status = PositionStatus.EXERCISED
        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")
        pos.close_reason = "exercise"

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        self._show_status(
            f"✅ اعمال فیزیکی {pos.position_id} — "
            f"ارزش ذاتی: {fmt_money(total_intrinsic)} {CURRENCY}",
            8000)

    def close_manually(self):
        """بستن دستی موقعیت منقضی."""
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            self._show_status("⚠️ یک موقعیت منقضی انتخاب کنید")
            return

        dlg = OffsetDialog(self, pos)
        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return

            for i, leg in enumerate(pos.legs):
                cp = result["close_prices"][i]
                leg.close_price = float(cp)
                leg.close_fee = \
                    PositionPnLCalculator.calculate_leg_close_fee(
                        leg, float(cp))

            pos.status = PositionStatus.CLOSED
            pos.close_date = (
                jdatetime.date.today().strftime("%Y/%m/%d"))
            pos.close_reason = "offset"

            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()
            self._show_status(f"✅ {pos.position_id} بسته شد")
        finally:
            dlg.deleteLater()

    # ═══════════════════════════════════════════════════
    # تب‌بندی
    # ═══════════════════════════════════════════════════

    def _update_tab_badges(self):
        """به‌روزرسانی نشان‌های تب."""
        pending_count = len(self._get_pending_positions())
        tab_bar = self.tabs.tabBar()
        if pending_count > 0:
            self.tabs.setTabText(
                TAB_PENDING,
                f"⚠️ نیازمند تعیین تکلیف ({pending_count})")
            tab_bar.setTabTextColor(TAB_PENDING, QColor(Theme.WARN))
        else:
            self.tabs.setTabText(
                TAB_PENDING, "⚠️ نیازمند تعیین تکلیف")
            tab_bar.setTabTextColor(TAB_PENDING, QColor(Theme.MUTED))

        # بج آلرت برای تب فعال
        active_count = len(self._get_active_positions())
        alert_count = 0
        for pos in self._get_active_positions():
            if pos.target_roi_maturity > 0:
                try:
                    threshold = SharedAnalytics.calculate_dynamic_threshold(
                        pos.target_roi_maturity, pos.days_elapsed())
                    _, roi = PositionPnLCalculator.calculate_live_pnl(pos)
                    if threshold > 0 and roi >= threshold:
                        alert_count += 1
                except Exception:
                    pass

        if alert_count > 0:
            self.tabs.setTabText(
                TAB_ACTIVE,
                f"🟢 فعال ({active_count}) 🎯{alert_count}")
        elif active_count > 0:
            self.tabs.setTabText(
                TAB_ACTIVE, f"🟢 فعال ({active_count})")
        else:
            self.tabs.setTabText(TAB_ACTIVE, "🟢 فعال")


__all__ = ["PositionSaverWidget", "SortableItem"]