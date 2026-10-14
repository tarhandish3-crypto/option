# position_saver/ui/main_widget.py
# -*- coding: utf-8 -*-

"""
ویجت اصلی مدیریت موقعیت‌ها و گروه‌های استراتژی آپشن.

معماری سه‌سطحی:
    - OptionLeg:       معامله‌ی خام
    - StrategyPosition: واحد معاملاتی (Lot)
    - StrategyGroup:   ماسک گروه‌بندی استراتژی

تب‌ها:
    - 📁 گروه‌ها (جدید)
    - 🟢 فعال
    - ⚠️ نیازمند تعیین تکلیف
    - 📜 تاریخچه
"""

import re
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
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from position_saver.models import (
    StrategyPosition, StrategyGroup, PositionStatus,
)
from position_saver.storage import PositionStorage
from position_saver.pnl_calculator import PositionPnLCalculator
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

TAB_GROUPS = 0
TAB_ACTIVE = 1
TAB_PENDING = 2
TAB_HISTORY = 3


# ═════════════════════════════════════════════════════
# SortableItem
# ═════════════════════════════════════════════════════

class SortableItem(QTableWidgetItem):
    """آیتم جدول با سورت عددی"""

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
    ویجت اصلی مدیریت موقعیت‌ها و گروه‌های استراتژی.

    شامل:
        - ۴ تب: گروه‌ها / فعال / نیازمند تعیین تکلیف / تاریخچه
        - نمایش گروه‌ها با PnL تجمیعی
        - پایش لحظه‌ای آلرت‌های position و group
    """

    # ─── ستون‌های جدول position ───
    COL_ID = 0
    COL_STRATEGY = 1
    COL_BROKER = 2
    COL_UNDERLYING = 3
    COL_EXEC_DATE = 4
    COL_EXPIRY_DATE = 5
    COL_DAYS_LEFT = 6
    COL_LEGS = 7
    COL_NET_COST = 8
    COL_TARGET_ROI = 9
    COL_LIVE_PNL = 10
    COL_STATUS = 11
    COL_SOURCE = 12
    N_COLS = 13

    # ─── ستون‌های جدول group ───
    GCOL_ID = 0
    GCOL_NAME = 1
    GCOL_TYPE = 2
    GCOL_NUM_POS = 3
    GCOL_OPEN_POS = 4
    GCOL_CLOSED_POS = 5
    GCOL_LIVE_PNL = 6
    GCOL_REALIZED_PNL = 7
    GCOL_TOTAL_PNL = 8
    GCOL_ROI = 9
    GCOL_STATUS = 10
    GCOL_CREATED = 11
    N_GROUP_COLS = 12

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
        self.groups: List[StrategyGroup] = []

        # ─── state ترد ───
        self._monitor_started = False
        self._expired_alerted = set()
        self._last_success_time: Optional[datetime] = None
        self._market_snapshot = None
        self._group_alerted = set()    # ✅ گروه‌های آلرت‌شده

        self.setObjectName("PositionSaver")

        # ─── ترد پس‌زمینه ───
        self.monitor_thread = LivePositionMonitorThread(
            self.storage, check_interval=10)
        self.monitor_thread.prices_updated.connect(
            self.on_prices_updated)
        self.monitor_thread.alerts_found.connect(
            self.on_alerts_found)
        self.monitor_thread.group_alerts_found.connect(
            self.on_group_alerts_found)          # ✅ جدید
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
        QShortcut(QKeySequence("Delete"), self, self.delete_position)
        QShortcut(QKeySequence("F5"), self, self.manual_refresh_data)
        QShortcut(QKeySequence("Ctrl+B"), self,
                  self.send_positions_to_bale)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_to_excel)
        QShortcut(QKeySequence("Ctrl+I"), self, self.import_from_excel)
        QShortcut(QKeySequence("Ctrl+G"), self,
                  self.create_group_from_selection)  # ✅ جدید

    # ═══════════════════════════════════════════════════
    # نوار وضعیت
    # ═══════════════════════════════════════════════════

    def _get_status_bar(self) -> Optional[QStatusBar]:
        try:
            window = self.window()
            if isinstance(window, QMainWindow) and window.statusBar():
                return window.statusBar()
        except Exception:
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

        # ─── تب ۱: گروه‌ها ───
        self.tab_groups, self.lbl_sum_groups, self.lbl_empty_groups = \
            self._build_groups_tab()
        self.tabs.addTab(self.tab_groups, "📁 گروه‌ها")

        # ─── تب ۲: فعال ───
        self.tab_active, self.lbl_sum_active, self.lbl_empty_active = \
            self._build_table_tab("active")
        self.tabs.addTab(self.tab_active, "🟢 فعال")

        # ─── تب ۳: نیازمند تعیین تکلیف ───
        self.tab_pending, self.lbl_sum_pending, self.lbl_empty_pending = \
            self._build_table_tab("pending")
        self.tabs.addTab(self.tab_pending, "⚠️ نیازمند تعیین تکلیف")

        # ─── تب ۴: تاریخچه ───
        self.tab_history, self.lbl_sum_history, self.lbl_empty_history = \
            self._build_table_tab("history")
        self.tabs.addTab(self.tab_history, "📜 تاریخچه")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        self.summary_frame = self._build_summary_panel()
        main_layout.addWidget(self.summary_frame)

    def _on_tab_changed(self, idx: int):
        """به‌روزرسانی جدول هنگام تعویض تب"""
        if idx == TAB_GROUPS:
            self._populate_groups_table()

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

        # ✅ کارت گروه‌ها
        self.card_groups = self._make_card("گروه‌های باز", "0")
        layout.addWidget(self.card_groups)
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

        self.btn_add = QPushButton("➕ ثبت موقعیت جدید")
        self.btn_add.clicked.connect(self.add_position)
        self.btn_add.setToolTip("ثبت موقعیت جدید (Ctrl+N)")
        set_kind(self.btn_add, "primary")
        tb.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ ویرایش")
        self.btn_edit.clicked.connect(self.edit_position)
        tb.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 حذف")
        self.btn_delete.clicked.connect(self.delete_position)
        self.btn_delete.setToolTip("حذف (Del)")
        set_kind(self.btn_delete, "danger")
        tb.addWidget(self.btn_delete)

        tb.addSpacing(12)

        # ✅ دکمه‌ی تعریف گروه
        self.btn_create_group = QPushButton("📁 تعریف گروه")
        self.btn_create_group.clicked.connect(
            self.create_group_from_selection)
        self.btn_create_group.setToolTip(
            "تعریف گروه استراتژی از موقعیت‌های انتخاب‌شده (Ctrl+G)")
        set_kind(self.btn_create_group, "primary")
        tb.addWidget(self.btn_create_group)

        tb.addSpacing(12)

        # ✅ دکمه‌ی ایمپورت اکسل
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

        tb.addSpacing(12)

        self.btn_send_bale = QPushButton("📨 ارسال به بله")
        self.btn_send_bale.clicked.connect(self.send_positions_to_bale)
        self.btn_send_bale.setToolTip("ارسال (Ctrl+B)")
        tb.addWidget(self.btn_send_bale)

        tb.addSpacing(12)

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
    # ✅ تب گروه‌ها
    # ═══════════════════════════════════════════════════

    def _build_groups_tab(self) -> Tuple[QWidget, QLabel, QLabel]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ─── نوار ابزار گروه ───
        actions_bar = QWidget()
        actions_bar.setFixedHeight(ACTIONS_BAR_HEIGHT)
        ab = QHBoxLayout(actions_bar)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(6)

        self.btn_group_edit = QPushButton("✏️ ویرایش گروه")
        self.btn_group_edit.clicked.connect(self.edit_group)
        ab.addWidget(self.btn_group_edit)

        self.btn_group_delete = QPushButton("🗑 حذف گروه")
        self.btn_group_delete.clicked.connect(self.delete_group)
        set_kind(self.btn_group_delete, "danger")
        ab.addWidget(self.btn_group_delete)

        self.btn_group_dissolve = QPushButton("✂️ بازکردن گروه")
        self.btn_group_dissolve.clicked.connect(self.dissolve_group)
        ab.addWidget(self.btn_group_dissolve)

        ab.addSpacing(12)

        self.btn_group_offset = QPushButton("🔁 آفست گروه")
        self.btn_group_offset.clicked.connect(self.offset_group)
        set_kind(self.btn_group_offset, "primary")
        ab.addWidget(self.btn_group_offset)

        ab.addSpacing(12)

        self.btn_group_view = QPushButton("📊 مشاهده‌ی جزئیات")
        self.btn_group_view.clicked.connect(self.view_group_details)
        ab.addWidget(self.btn_group_view)

        ab.addStretch()
        layout.addWidget(actions_bar)

        # ─── جدول گروه‌ها ───
        table = QTableWidget(0, self.N_GROUP_COLS)
        table.setHorizontalHeaderLabels([
            "شناسه", "نام گروه", "نوع استراتژی",
            "تعداد موقعیت", "باز", "بسته",
            "سود/زیان باز", "سود/زیان محقق",
            "مجموع سود/زیان", "ROI", "وضعیت", "تاریخ ایجاد",
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
        table.setColumnHidden(self.GCOL_ID, True)

        table.setColumnWidth(self.GCOL_NAME, 180)
        table.setColumnWidth(self.GCOL_TYPE, 140)
        table.setColumnWidth(self.GCOL_NUM_POS, 90)
        table.setColumnWidth(self.GCOL_OPEN_POS, 60)
        table.setColumnWidth(self.GCOL_CLOSED_POS, 60)
        table.setColumnWidth(self.GCOL_LIVE_PNL, 130)
        table.setColumnWidth(self.GCOL_REALIZED_PNL, 130)
        table.setColumnWidth(self.GCOL_TOTAL_PNL, 140)
        table.setColumnWidth(self.GCOL_ROI, 90)
        table.setColumnWidth(self.GCOL_STATUS, 110)
        table.setColumnWidth(self.GCOL_CREATED, 100)

        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_group_context_menu(t, pos))

        layout.addWidget(table, 1)

        # ─── نوار جمع ───
        lbl_sum = QLabel("جمع: —")
        lbl_sum.setStyleSheet(
            f"color: {Theme.MUTED}; font-size: 11px; "
            f"padding: 6px 10px; background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px;")
        layout.addWidget(lbl_sum)

        lbl_empty = QLabel(
            "📭 هنوز گروهی تعریف نشده است\n\n"
            "برای تعریف گروه، از تب «فعال» یا «تاریخچه»، "
            "موقعیت‌ها را انتخاب کرده و روی «📁 تعریف گروه» کلیک کنید.")
        lbl_empty.setAlignment(Qt.AlignCenter)
        lbl_empty.setStyleSheet(
            f"color: {Theme.MUTED}; font-size: 14px; padding: 40px;")
        lbl_empty.setVisible(False)
        layout.addWidget(lbl_empty)

        return container, lbl_sum, lbl_empty

    # ═══════════════════════════════════════════════════
    # تب position (فعال / pending / history)
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
            "شناسه", "نام استراتژی", "کارگزاری", "نماد پایه",
            "تاریخ اجرا", "تاریخ سررسید", "روز مانده",
            "لنگه‌ها", "هزینه ورود", "سود انتظاری",
            "سود/زیان لایو", "وضعیت", "منبع",
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

        table.setColumnWidth(self.COL_STRATEGY, 120)
        table.setColumnWidth(self.COL_BROKER, 100)
        table.setColumnWidth(self.COL_UNDERLYING, 75)
        table.setColumnWidth(self.COL_EXEC_DATE, 80)
        table.setColumnWidth(self.COL_EXPIRY_DATE, 80)
        table.setColumnWidth(self.COL_DAYS_LEFT, 70)
        table.setColumnWidth(self.COL_NET_COST, 120)
        table.setColumnWidth(self.COL_TARGET_ROI, 75)
        table.setColumnWidth(self.COL_LIVE_PNL, 130)
        table.setColumnWidth(self.COL_STATUS, 130)
        table.setColumnWidth(self.COL_SOURCE, 80)

        header.setSectionResizeMode(self.COL_LEGS, QHeaderView.Stretch)

        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_context_menu(t, pos))

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

            layout.addSpacing(12)

            # ✅ دکمه‌ی تعریف گروه از position های انتخاب‌شده
            self.btn_group_from_active = QPushButton(
                "📁 تعریف گروه از انتخاب")
            self.btn_group_from_active.clicked.connect(
                self.create_group_from_selection)
            layout.addWidget(self.btn_group_from_active)

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
                "ℹ️ این تب برای مشاهده‌ی تاریخچه است — "
                "موقعیت‌های بسته‌شده، اعمال‌شده، تسویه‌شده و نکول‌شده")
            lbl_hint.setStyleSheet(
                f"color: {Theme.MUTED}; font-size: 11px; "
                f"padding: 4px 10px; "
                f"background-color: {Theme.CARD}; "
                f"border: 1px solid {Theme.BORDER}; "
                f"border-radius: 4px;")
            lbl_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(lbl_hint)

            layout.addSpacing(12)

            # ✅ امکان تعریف گروه از history
            self.btn_group_from_history = QPushButton(
                "📁 تعریف گروه از انتخاب")
            self.btn_group_from_history.clicked.connect(
                self.create_group_from_selection)
            layout.addWidget(self.btn_group_from_history)

        layout.addStretch()
        return w

    # ═══════════════════════════════════════════════════
    # منوی راست‌کلیک — تب position
    # ═══════════════════════════════════════════════════

    def _show_context_menu(self, table: QTableWidget, pos):
        has_selection = bool(table.selectedIndexes())
        menu = QMenu(self)

        action_add = menu.addAction("➕ ثبت موقعیت جدید")
        action_add.setShortcut("Ctrl+N")

        action_import = menu.addAction("📥 ایمپورت اکسل")
        action_import.setShortcut("Ctrl+I")

        action_history = menu.addAction("📋 تاریخچه ایمپورت‌ها")

        action_edit = action_delete = None
        action_offset = action_settle = action_exercise = None
        action_close = action_bale = action_group = None

        if has_selection:
            menu.addSeparator()
            action_edit = menu.addAction("✏️ ویرایش")
            action_delete = menu.addAction("🗑 حذف")
            action_delete.setShortcut("Del")
            menu.addSeparator()

            idx = self.tabs.currentIndex()
            if idx == TAB_ACTIVE:
                action_offset = menu.addAction("🔁 آفست")
            elif idx == TAB_PENDING:
                action_settle = menu.addAction("📌 تسویه/نکول")
                action_exercise = menu.addAction("🏦 اعمال فیزیکی")
                action_close = menu.addAction("✏️ بستن دستی")

            menu.addSeparator()

            # ✅ تعریف گروه
            action_group = menu.addAction("📁 تعریف گروه از انتخاب")
            action_group.setShortcut("Ctrl+G")

            menu.addSeparator()
            action_bale = menu.addAction("📨 ارسال به بله")

        chosen = menu.exec(table.viewport().mapToGlobal(pos))

        if chosen == action_add:
            self.add_position()
        elif chosen == action_import:
            self.import_from_excel()
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
        elif action_group and chosen == action_group:
            self.create_group_from_selection()
        elif action_bale and chosen == action_bale:
            self.send_positions_to_bale()

    # ═══════════════════════════════════════════════════
    # منوی راست‌کلیک — تب گروه‌ها
    # ═══════════════════════════════════════════════════

    def _show_group_context_menu(self, table: QTableWidget, pos):
        has_selection = bool(table.selectedIndexes())
        menu = QMenu(self)

        action_view = menu.addAction("📊 مشاهده‌ی جزئیات")
        action_edit = menu.addAction("✏️ ویرایش نام و نوع")
        action_offset = menu.addAction("🔁 آفست گروه")
        menu.addSeparator()
        action_dissolve = menu.addAction("✂️ بازکردن گروه")
        action_delete = menu.addAction("🗑 حذف گروه")

        chosen = menu.exec(table.viewport().mapToGlobal(pos))

        if chosen == action_view:
            self.view_group_details()
        elif chosen == action_edit:
            self.edit_group()
        elif chosen == action_offset:
            self.offset_group()
        elif chosen == action_dissolve:
            self.dissolve_group()
        elif chosen == action_delete:
            self.delete_group()

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

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()

    @Slot(list)
    def on_alerts_found(self, alerts: list):
        """آلرت‌های position"""
        for alert in alerts:
            self.monitor_thread.send_bale_alert(alert)

        if alerts:
            self.refresh_all_tabs()
            self._show_status(
                f"✅ {len(alerts)} هشدار موقعیت ارسال شد")

    # ✅ جدید: آلرت‌های گروه
    @Slot(list)
    def on_group_alerts_found(self, alerts: list):
        """آلرت‌های گروه استراتژی"""
        for alert in alerts:
            self.monitor_thread.send_group_bale_alert(alert)
            # ذخیره‌ی group_id برای جلوگیری از آلرت تکراری
            gid = alert.get("group_id", "")
            if gid:
                self._group_alerted.add(gid)

        if alerts:
            self.refresh_all_tabs()
            self._show_status(
                f"✅ {len(alerts)} هشدار گروه ارسال شد", 8000)

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
        try:
            self.groups = self.storage.load_groups()
        except Exception as e:
            logger.warning(f"Load groups failed: {e}")
            self.groups = []
        self.refresh_all_tabs()

    def refresh_all_tabs(self):
        self._populate_groups_table()
        self._populate_table(self.tab_active, self._get_active_positions())
        self._populate_table(self.tab_pending, self._get_pending_positions())
        self._populate_table(self.tab_history, self._get_history_positions())
        self._update_tab_badges()
        self._update_summary()

    # ═══════════════════════════════════════════════════
    # پر کردن جدول گروه‌ها
    # ═══════════════════════════════════════════════════

    def _populate_groups_table(self):
        """پر کردن جدول گروه‌ها"""
        table = self.tab_groups.findChild(QTableWidget)
        if table is None:
            return

        # حفظ انتخاب و اسکرول
        selected_ids = set()
        for idx in table.selectedIndexes():
            id_item = table.item(idx.row(), self.GCOL_ID)
            if id_item:
                selected_ids.add(id_item.text())

        scroll_pos = table.verticalScrollBar().value()
        sort_col = table.horizontalHeader().sortIndicatorSection()
        sort_order = table.horizontalHeader().sortIndicatorOrder()

        table.setSortingEnabled(False)
        table.setRowCount(0)

        for group in self.groups:
            row = table.rowCount()
            table.insertRow(row)
            self._fill_group_row(table, row, group)

        if selected_ids:
            for r in range(table.rowCount()):
                id_item = table.item(r, self.GCOL_ID)
                if id_item and id_item.text() in selected_ids:
                    table.selectRow(r)

        table.verticalScrollBar().setValue(scroll_pos)
        table.setSortingEnabled(True)
        if sort_col > 0:
            table.sortItems(sort_col, sort_order)

        self._update_groups_summary()

    def _fill_group_row(self, table: QTableWidget, row: int,
                         group: StrategyGroup):
        """پر کردن یک ردیف جدول گروه"""
        # ─── محاسبات ───
        live_pnl = group.total_live_pnl(self.positions)
        realized = group.total_realized_pnl(self.positions)
        total_pnl = live_pnl + realized
        open_cost = group.total_open_cost(self.positions)

        roi = (total_pnl / open_cost * 100.0) if open_cost > 0 else 0.0

        # ─── شمارش ───
        pos_ids = set(group.position_ids)
        group_positions = [
            p for p in self.positions if p.position_id in pos_ids
        ]
        n_pos = len(group_positions)
        n_open = sum(1 for p in group_positions if p.is_open)
        n_closed = sum(1 for p in group_positions if p.is_closed)

        # ─── وضعیت گروه ───
        if n_open == 0 and n_closed > 0:
            status_text = "🟢 کاملاً بسته"
            status_color = Theme.MUTED
        elif n_open > 0:
            status_text = f"🟡 {n_open} باز"
            status_color = Theme.WARN
        else:
            status_text = "⚪ خالی"
            status_color = Theme.MUTED

        if group.alert_sent:
            status_text = "🎯 " + status_text

        # ─── ستون‌ها ───
        table.setItem(row, self.GCOL_ID,
                      self._make_text_item(group.group_id))
        table.setItem(row, self.GCOL_NAME,
                      self._make_text_item(group.label_fa))
        table.setItem(row, self.GCOL_TYPE,
                      self._make_text_item(
                          group.strategy_type or "سفارشی"))
        table.setItem(row, self.GCOL_NUM_POS,
                      self._make_number_item(
                          str(n_pos), float(n_pos)))
        table.setItem(row, self.GCOL_OPEN_POS,
                      self._make_number_item(
                          str(n_open), float(n_open)))
        table.setItem(row, self.GCOL_CLOSED_POS,
                      self._make_number_item(
                          str(n_closed), float(n_closed)))

        # PnL ها
        table.setItem(row, self.GCOL_LIVE_PNL,
                      self._make_number_item(
                          fmt_money(live_pnl), live_pnl,
                          self._tone_color(pnl_tone(live_pnl))))

        table.setItem(row, self.GCOL_REALIZED_PNL,
                      self._make_number_item(
                          fmt_money(realized), realized,
                          self._tone_color(pnl_tone(realized))))

        table.setItem(row, self.GCOL_TOTAL_PNL,
                      self._make_number_item(
                          fmt_money(total_pnl), total_pnl,
                          self._tone_color(pnl_tone(total_pnl))))

        table.setItem(row, self.GCOL_ROI,
                      self._make_number_item(
                          fmt_pct(roi, digits=1),
                          roi,
                          self._tone_color(pnl_tone(roi))))

        table.setItem(row, self.GCOL_STATUS,
                      self._make_text_item(status_text, status_color))

        table.setItem(row, self.GCOL_CREATED,
                      self._make_text_item(group.created_at or "—"))

    def _update_groups_summary(self):
        """نوار جمع گروه‌ها"""
        labels = self.tab_groups.findChildren(QLabel)
        if len(labels) < 2:
            return

        lbl_sum = labels[0]
        lbl_empty = labels[1]
        table = self.tab_groups.findChild(QTableWidget)

        if not self.groups:
            if table:
                table.setVisible(False)
            lbl_sum.setVisible(False)
            lbl_empty.setVisible(True)
            return

        if table:
            table.setVisible(True)
        lbl_empty.setVisible(False)
        lbl_sum.setVisible(True)

        total_live = 0.0
        total_realized = 0.0

        for g in self.groups:
            total_live += g.total_live_pnl(self.positions)
            total_realized += g.total_realized_pnl(self.positions)

        total = total_live + total_realized

        lbl_sum.setText(
            f"جمع: {len(self.groups)} گروه  |  "
            f"سود/زیان باز: {fmt_money(total_live)} {CURRENCY}  |  "
            f"محقق‌شده: {fmt_money(total_realized)} {CURRENCY}  |  "
            f"مجموع: {fmt_money(total)} {CURRENCY}")

        color = self._tone_color(pnl_tone(total))
        lbl_sum.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 6px 10px; "
            f"background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px;")

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

        if selected_ids:
            for r in range(table.rowCount()):
                id_item = table.item(r, self.COL_ID)
                if id_item and id_item.text() in selected_ids:
                    table.selectRow(r)

        table.verticalScrollBar().setValue(scroll_pos)
        table.setSortingEnabled(True)
        if sort_col > 0:
            table.sortItems(sort_col, sort_order)

        self._update_tab_summary(container, positions)

    def _fill_row(self, table: QTableWidget, row: int,
                  pos: StrategyPosition, idx: int):
        net_cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
        live_pnl, live_roi = PositionPnLCalculator.calculate_live_pnl(pos)
        realized_pnl, realized_roi = \
            PositionPnLCalculator.calculate_realized_pnl(pos)

        legs_str = " | ".join([
            f"{l.leg_type.label_fa}: {l.symbol}" for l in pos.legs
        ])

        # ─── روز مانده ───
        days_left = self._calc_days_left(pos.expiry_date)
        if days_left is None:
            days_text = "—"
            days_color = Theme.MUTED
            days_sort_val = 999999.0
        elif days_left < 0:
            days_text = f"{abs(days_left)}−"
            days_color = Theme.MUTED
            days_sort_val = float(days_left)
        else:
            days_text = str(days_left)
            days_color = self._days_color(days_left)
            days_sort_val = float(days_left)

        # ─── ستون‌ها ───
        table.setItem(row, self.COL_ID,
                      self._make_text_item(pos.position_id))

        # ✅ نمایش نام نمایشی + گروه
        strategy_text = pos.strategy_name
        if pos.has_group:
            group = next(
                (g for g in self.groups
                 if g.group_id == pos.group_id), None)
            if group:
                strategy_text = (
                    f"{group.label_fa} | {pos.strategy_name}"
                    if pos.strategy_name else group.label_fa)

        table.setItem(row, self.COL_STRATEGY,
                      self._make_text_item(strategy_text))

        table.setItem(row, self.COL_BROKER,
                      self._make_text_item(pos.broker_name or "—"))
        table.setItem(row, self.COL_UNDERLYING,
                      self._make_text_item(pos.underlying_symbol))
        table.setItem(row, self.COL_EXEC_DATE,
                      self._make_text_item(pos.execution_date))
        table.setItem(row, self.COL_EXPIRY_DATE,
                      self._make_text_item(pos.expiry_date))

        # روز مانده — عددی
        days_item = SortableItem(days_text, days_sort_val)
        days_item.setToolTip(days_text)
        days_item.setForeground(QColor(days_color))
        table.setItem(row, self.COL_DAYS_LEFT, days_item)

        table.setItem(row, self.COL_LEGS,
                      self._make_text_item(legs_str))
        table.setItem(row, self.COL_NET_COST,
                      self._make_number_item(
                          fmt_money(net_cost), net_cost))
        table.setItem(row, self.COL_TARGET_ROI,
                      self._make_number_item(
                          fmt_pct(pos.target_roi_maturity,
                                  digits=1, signed=False),
                          pos.target_roi_maturity))

        # ─── سود/زیان ───
        if pos.status == PositionStatus.OPEN:
            if self._is_pending_settlement(pos):
                pnl_text = "⚠️ منقضی - تسویه کنید"
                pnl_item = SortableItem(pnl_text, -999999999.0)
                pnl_item.setToolTip(pnl_text)
                pnl_item.setForeground(QColor(Theme.WARN))
            else:
                pnl_text = fmt_pnl(live_pnl, live_roi)
                pnl_item = SortableItem(pnl_text, float(live_pnl))
                pnl_item.setToolTip(
                    f"سود/زیان لایو: {fmt_money(live_pnl)} {CURRENCY}")
                pnl_item.setForeground(
                    QColor(self._tone_color(pnl_tone(live_pnl))))
        else:
            pnl_text = fmt_pnl(realized_pnl, realized_roi)
            pnl_item = SortableItem(pnl_text, float(realized_pnl))
            pnl_item.setToolTip(
                f"سود/زیان محقق‌شده: {fmt_money(realized_pnl)} "
                f"{CURRENCY}")
            pnl_item.setForeground(
                QColor(self._tone_color(pnl_tone(realized_pnl))))

        table.setItem(row, self.COL_LIVE_PNL, pnl_item)

        # ─── وضعیت ───
        status_text = pos.status.label_fa
        status_color = self._status_color(pos.status.value)

        if self._is_pending_settlement(pos):
            status_text = "⚠️ منقضی (تعیین تکلیف)"
            status_color = Theme.WARN

        if pos.needs_review or pos.has_incomplete_legs:
            status_text = "⚠️ " + status_text
            status_color = Theme.WARN

        # ✅ نشانگر گروه
        if pos.has_group:
            status_text = "📁 " + status_text

        table.setItem(row, self.COL_STATUS,
                      self._make_text_item(status_text, status_color))

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

    def _calc_days_left(self, expiry_date_str: str) -> Optional[int]:
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
    # جمع و حالت خالی — position
    # ═══════════════════════════════════════════════════

    def _update_tab_summary(self, container: QWidget,
                            positions: List[StrategyPosition]):
        labels = container.findChildren(QLabel)
        if len(labels) < 2:
            return
        lbl_sum, lbl_empty = labels[0], labels[1]
        table = container.findChild(QTableWidget)

        if not positions:
            table.setVisible(False)
            lbl_sum.setVisible(False)
            lbl_empty.setVisible(True)
            return

        table.setVisible(True)
        lbl_empty.setVisible(False)
        lbl_sum.setVisible(True)

        total_pnl = 0.0
        total_cost = 0.0
        for pos in positions:
            if pos.status == PositionStatus.OPEN:
                pnl, _ = PositionPnLCalculator.calculate_live_pnl(pos)
            else:
                pnl, _ = \
                    PositionPnLCalculator.calculate_realized_pnl(pos)
            cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
            if self._is_pending_settlement(pos):
                continue
            total_pnl += pnl
            total_cost += cost

        lbl_sum.setText(
            f"جمع: {len(positions)} موقعیت  |  "
            f"سود/زیان: {fmt_money(total_pnl)} {CURRENCY}  |  "
            f"هزینه: {fmt_money(total_cost)} {CURRENCY}")

        color = self._tone_color(pnl_tone(total_pnl))
        lbl_sum.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 6px 10px; "
            f"background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px;")

    # ═══════════════════════════════════════════════════
    # کارت‌های سرجمع
    # ═══════════════════════════════════════════════════

    def _update_summary(self):
        sum_open = 0.0
        sum_realized = 0.0
        active_count = 0
        open_groups = 0
        nearest_days = None

        for pos in self.positions:
            if pos.status == PositionStatus.OPEN:
                if self._is_pending_settlement(pos):
                    continue
                pnl, _ = PositionPnLCalculator.calculate_live_pnl(pos)
                sum_open += pnl
                active_count += 1
                days = self._calc_days_left(pos.expiry_date)
                if days is not None and days >= 0:
                    if nearest_days is None or days < nearest_days:
                        nearest_days = days
            else:
                pnl, _ = \
                    PositionPnLCalculator.calculate_realized_pnl(pos)
                sum_realized += pnl

        # ─── شمارش گروه‌های باز ───
        for g in self.groups:
            if g.has_any_open(self.positions):
                open_groups += 1

        total = sum_open + sum_realized

        self._set_card_value(
            self.card_open_pnl, f"{fmt_money(sum_open)} {CURRENCY}",
            pnl_tone(sum_open))
        self._set_card_value(
            self.card_realized_pnl,
            f"{fmt_money(sum_realized)} {CURRENCY}",
            pnl_tone(sum_realized))
        self._set_card_value(
            self.card_total_pnl, f"{fmt_money(total)} {CURRENCY}",
            pnl_tone(total))
        self._set_card_value(
            self.card_count, str(active_count), "primary")

        # ✅ کارت گروه‌ها
        self._set_card_value(
            self.card_groups,
            f"{open_groups} / {len(self.groups)}",
            "primary")

        if nearest_days is None:
            self._set_card_value(self.card_nearest, "—", "muted")
        else:
            tone = ("loss" if nearest_days <= DAY_CRITICAL_THRESHOLD
                    else ("warn" if nearest_days <= DAY_WARN_THRESHOLD
                          else "muted"))
            self._set_card_value(self.card_nearest,
                                 f"{nearest_days} روز", tone)

    # ═══════════════════════════════════════════════════
    # عملیات CRUD — Position
    # ═══════════════════════════════════════════════════

    def _current_table(self) -> Optional[QTableWidget]:
        container = self.tabs.currentWidget()
        if container:
            return container.findChild(QTableWidget)
        return None

    def _get_selected_positions(self) -> List[StrategyPosition]:
        table = self._current_table()
        if table is None:
            return []

        rows = sorted(set(idx.row() for idx in table.selectedIndexes()))
        positions, seen = [], set()

        # اگر تب گروه‌ها فعال است، از گروه پیدا می‌کنیم
        if self.tabs.currentIndex() == TAB_GROUPS:
            group = self._get_selected_group()
            if group:
                pos_ids = set(group.position_ids)
                return [
                    p for p in self.positions
                    if p.position_id in pos_ids
                ]
            return []

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

    def _get_selected_group(self) -> Optional[StrategyGroup]:
        """پیدا کردن گروه انتخاب‌شده در تب گروه‌ها"""
        table = self.tab_groups.findChild(QTableWidget)
        if table is None:
            return None

        rows = sorted(set(idx.row() for idx in table.selectedIndexes()))
        if not rows:
            return None

        id_item = table.item(rows[0], self.GCOL_ID)
        if id_item is None:
            return None

        gid = id_item.text()
        for g in self.groups:
            if g.group_id == gid:
                return g
        return None

    def add_position(self):
        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(self, snapshot=snapshot)
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
        pos = self._get_selected_position()
        if pos is None:
            self._show_status("⚠️ ابتدا یک موقعیت را انتخاب کنید")
            return
        if pos.status != PositionStatus.OPEN:
            QMessageBox.warning(
                self, "خطا",
                f"این موقعیت «{pos.status.label_fa}» است "
                f"و قابل ویرایش نیست.")
            return

        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(self, pos, snapshot=snapshot)
        try:
            if dlg.exec():
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
                self._show_status("✅ موقعیت ویرایش شد")
        finally:
            dlg.deleteLater()

    def delete_position(self):
        pos = self._get_selected_position()
        if pos is None:
            self._show_status("⚠️ ابتدا یک موقعیت را انتخاب کنید")
            return

        reply = QMessageBox.question(
            self, "تأیید حذف",
            f"آیا از حذف موقعیت زیر اطمینان دارید؟\n\n"
            f"شناسه: {pos.position_id}\n"
            f"استراتژی: {pos.strategy_name}",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.positions = [
                p for p in self.positions
                if p.position_id != pos.position_id
            ]
            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()
            self._show_status(
                f"🗑 موقعیت {pos.position_id} حذف شد")

    # ═══════════════════════════════════════════════════
    # ✅ عملیات CRUD — Group
    # ═══════════════════════════════════════════════════

    def create_group_from_selection(self):
        """
        تعریف گروه استراتژی از موقعیت‌های انتخاب‌شده.

        جریان:
            ۱. کاربر چند position را انتخاب می‌کند
            ۲. StrategyDialog باز می‌شود
            ۳. اعتبارسنجی ترکیب
            ۴. گروه تشکیل می‌شود
        """
        positions = self._get_selected_positions()
        if not positions:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند موقعیت را انتخاب کنید.")
            return

        # ─── چک: موقعیت‌ها نباید قبلاً در گروه باشند ───
        already_grouped = [p for p in positions if p.has_group]
        if already_grouped:
            reply = QMessageBox.question(
                self, "هشدار",
                f"⚠️ {len(already_grouped)} موقعیت قبلاً در گروه "
                f"دیگری هستند.\n\n"
                f"آیا می‌خواهید آن‌ها را از گروه قبلی جدا کرده و "
                f"به گروه جدید اضافه کنید؟",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        # ─── تبدیل به pseudo-trades برای StrategyDialog ───
        pseudo_trades = [
            self._position_to_pseudo_trade(p)
            for p in positions
        ]

        # ─── باز کردن StrategyDialog ───
        try:
            from position_saver.ui.strategy_dialog import (
                StrategyDialog)
            dlg = StrategyDialog(self, trades=pseudo_trades)
        except Exception as e:
            logger.exception(f"StrategyDialog failed: {e}")
            QMessageBox.critical(
                self, "خطا",
                f"خطا در باز کردن دیالوگ استراتژی:\n{e}")
            return

        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return

            strategy_type = result.get("strategy_type", "")
            display_name = result.get("display_name", "")

            # ─── ساخت گروه ───
            group = StrategyGroup(
                strategy_type=strategy_type,
                display_name=display_name,
                position_ids=[p.position_id for p in positions],
                created_at=jdatetime.date.today().strftime("%Y/%m/%d"),
            )

            # ─── حذف از گروه‌های قبلی ───
            for old_group in self.groups:
                for p in positions:
                    if p.position_id in old_group.position_ids:
                        old_group.position_ids.remove(p.position_id)

            # ─── حذف گروه‌های خالی ───
            self.groups = [
                g for g in self.groups if g.position_ids
            ]

            # ─── اضافه کردن گروه جدید ───
            self.groups.append(group)

            # ─── به‌روزرسانی position ها ───
            for p in positions:
                p.group_id = group.group_id
                p.strategy_type = strategy_type
                if display_name:
                    p.strategy_name = display_name

            # ─── ذخیره ───
            self.storage.save_positions(self.positions)
            self.storage.save_groups(self.groups)

            self.refresh_all_tabs()

            QMessageBox.information(
                self, "✅ موفق",
                f"گروه «{display_name}» با {len(positions)} موقعیت "
                f"تشکیل شد.")
        finally:
            dlg.deleteLater()

    def _position_to_pseudo_trade(self, pos: StrategyPosition):
        """تبدیل StrategyPosition به یک شیء شبیه TradeRecord"""
        class PseudoTrade:
            pass

        p = PseudoTrade()
        if pos.legs:
            leg = pos.legs[0]
            p.trade_id = leg.trade_ref or pos.position_id
            p.raw_date = leg.open_date or pos.execution_date
            p.raw_time = leg.open_time or ""
            p.symbol = leg.symbol
            p.side = leg.leg_type
            p.quantity = leg.quantity
            p.price = leg.entry_price
            p.option_kind = leg.option_kind
            p.strike_price = leg.strike_price
            p.expiry_date = leg.expiry_date
            p.is_option = leg.is_option
            p.is_call = leg.is_call
            p.is_put = leg.is_put
            p.is_stock = leg.is_stock
            p.effective_contract_size = leg.effective_contract_size
            p.close_reason = leg.close_reason
        else:
            p.trade_id = pos.position_id
            p.raw_date = pos.execution_date
            p.raw_time = ""
            p.symbol = pos.underlying_symbol
            p.side = None
            p.quantity = 0
            p.price = 0
            p.option_kind = None
            p.strike_price = 0
            p.expiry_date = pos.expiry_date
            p.is_option = False
            p.is_call = False
            p.is_put = False
            p.is_stock = True
            p.effective_contract_size = 1
            p.close_reason = pos.close_reason

        return p

    def edit_group(self):
        """ویرایش نام و نوع گروه"""
        group = self._get_selected_group()
        if group is None:
            self._show_status("⚠️ ابتدا یک گروه را انتخاب کنید")
            return

        # ─── جمع‌آوری position های گروه ───
        group_positions = [
            p for p in self.positions
            if p.position_id in group.position_ids
        ]

        if not group_positions:
            QMessageBox.warning(
                self, "خطا",
                "این گروه خالی است.")
            return

        # ─── تبدیل به pseudo-trades ───
        pseudo_trades = [
            self._position_to_pseudo_trade(p)
            for p in group_positions
        ]

        # ─── باز کردن StrategyDialog ───
        try:
            from position_saver.ui.strategy_dialog import (
                StrategyDialog)
            dlg = StrategyDialog(self, trades=pseudo_trades)
            # پیش‌انتخاب نوع استراتژی فعلی
            idx = dlg.cmb_strategy.findData(group.strategy_type)
            if idx >= 0:
                dlg.cmb_strategy.setCurrentIndex(idx)
            dlg.txt_display_name.setText(group.display_name)
        except Exception as e:
            logger.exception(f"StrategyDialog failed: {e}")
            return

        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return

            strategy_type = result.get("strategy_type", "")
            display_name = result.get("display_name", "")

            group.strategy_type = strategy_type
            group.display_name = display_name

            # ─── به‌روزرسانی position ها ───
            for p in group_positions:
                p.strategy_type = strategy_type
                if display_name:
                    p.strategy_name = display_name

            self.storage.save_groups(self.groups)
            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()

            self._show_status(
                f"✅ گروه «{display_name}» ویرایش شد")
        finally:
            dlg.deleteLater()

    def delete_group(self):
        """حذف گروه (بدون حذف position ها)"""
        group = self._get_selected_group()
        if group is None:
            self._show_status("⚠️ ابتدا یک گروه را انتخاب کنید")
            return

        reply = QMessageBox.question(
            self, "تأیید حذف گروه",
            f"آیا از حذف گروه زیر اطمینان دارید؟\n\n"
            f"نام: {group.label_fa}\n"
            f"تعداد موقعیت‌ها: {group.num_positions}\n\n"
            f"⚠️ موقعیت‌ها حذف نمی‌شوند، فقط از گروه خارج می‌شوند.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # ─── حذف گروه ───
        self.groups = [
            g for g in self.groups if g.group_id != group.group_id
        ]

        # ─── پاک کردن group_id از position ها ───
        for p in self.positions:
            if p.group_id == group.group_id:
                p.group_id = ""
                p.strategy_type = ""

        self.storage.save_groups(self.groups)
        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()

        self._show_status(f"🗑 گروه «{group.label_fa}» حذف شد")

    def dissolve_group(self):
        """بازکردن گروه (همان حذف گروه است)"""
        self.delete_group()

    def view_group_details(self):
        """مشاهده‌ی جزئیات گروه (نمایش position ها)"""
        group = self._get_selected_group()
        if group is None:
            self._show_status("⚠️ ابتدا یک گروه را انتخاب کنید")
            return

        # ─── ساخت پیام ───
        group_positions = [
            p for p in self.positions
            if p.position_id in group.position_ids
        ]

        lines = [
            f"📁 گروه: {group.label_fa}",
            f"🏷 نوع: {group.strategy_type or 'سفارشی'}",
            f"📅 تاریخ ایجاد: {group.created_at}",
            "",
            f"📊 موقعیت‌ها ({len(group_positions)}):",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        for i, p in enumerate(group_positions, 1):
            legs_str = " | ".join(
                f"{l.leg_type.label_fa}: {l.symbol}"
                for l in p.legs
            )
            live_pnl, _ = \
                PositionPnLCalculator.calculate_live_pnl(p)
            lines.append(
                f"{i}. {p.position_id}")
            lines.append(f"   {legs_str}")
            lines.append(
                f"   وضعیت: {p.status.label_fa} | "
                f"PnL: {fmt_money(live_pnl)}")

        # ─── خلاصه ───
        total_live = group.total_live_pnl(self.positions)
        total_realized = group.total_realized_pnl(self.positions)
        total = total_live + total_realized
        open_cost = group.total_open_cost(self.positions)
        roi = (total / open_cost * 100.0) if open_cost > 0 else 0.0

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 سود/زیان باز: {fmt_money(total_live)}")
        lines.append(f"💰 سود/زیان محقق: {fmt_money(total_realized)}")
        lines.append(f"📈 مجموع: {fmt_money(total)}")
        lines.append(f"📊 ROI: {fmt_pct(roi, digits=1)}")
        lines.append(f"💼 هزینه‌ی باز: {fmt_money(open_cost)}")

        QMessageBox.information(
            self, f"جزئیات گروه — {group.label_fa}",
            "\n".join(lines))

    def offset_group(self):
        """آفست کل گروه (بستن همه‌ی position های باز)"""
        group = self._get_selected_group()
        if group is None:
            self._show_status("⚠️ ابتدا یک گروه را انتخاب کنید")
            return

        group_positions = [
            p for p in self.positions
            if p.position_id in group.position_ids and p.is_open
        ]

        if not group_positions:
            QMessageBox.information(
                self, "اطلاع",
                "این گروه هیچ موقعیت بازی ندارد.")
            return

        # ─── محاسبه‌ی PnL لحظه‌ای ───
        total_live = group.total_live_pnl(self.positions)
        total_realized = group.total_realized_pnl(self.positions)
        total = total_live + total_realized
        open_cost = group.total_open_cost(self.positions)
        roi = (total / open_cost * 100.0) if open_cost > 0 else 0.0

        # ─── تأیید ───
        reply = QMessageBox.question(
            self, "تأیید آفست گروه",
            f"آیا از آفست کل گروه زیر مطمئن هستید؟\n\n"
            f"📁 نام: {group.label_fa}\n"
            f"📊 موقعیت‌های باز: {len(group_positions)}\n\n"
            f"💰 سود/زیان لحظه‌ای: {fmt_money(total)} {CURRENCY}\n"
            f"📈 ROI: {fmt_pct(roi, digits=1)}\n"
            f"💼 هزینه‌ی باز: {fmt_money(open_cost)}",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # ─── آفست هر position ───
        closed_count = 0
        for pos in group_positions:
            try:
                # آفست: close_price = current_price
                for leg in pos.legs:
                    if leg.is_open:
                        cp = (leg.current_price
                              if leg.current_price > 0
                              else leg.entry_price)
                        leg.close_price = float(cp)
                        leg.close_fee = (
                            PositionPnLCalculator
                            .calculate_leg_close_fee(leg, float(cp))
                        )

                pos.status = PositionStatus.CLOSED
                pos.close_date = (
                    jdatetime.date.today().strftime("%Y/%m/%d"))
                pos.close_reason = "offset"
                closed_count += 1
            except Exception as e:
                logger.exception(f"Offset position failed: {e}")

        # ─── ذخیره ───
        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()

        QMessageBox.information(
            self, "✅ موفق",
            f"{closed_count} موقعیت گروه «{group.label_fa}» آفست شد.")

    # ═══════════════════════════════════════════════════
    # Import / Export
    # ═══════════════════════════════════════════════════

    def import_from_excel(self):
        """اجرای Wizard ایمپورت"""
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
        """نمایش تاریخچه‌ی ایمپورت‌ها"""
        dlg = ImportHistoryDialog(parent=self, storage=self.storage)
        try:
            if dlg.exec():
                self.load_data()
                self._show_status("تاریخچه به‌روز شد")
        finally:
            dlg.deleteLater()

    def export_to_excel(self):
        """خروجی اکسل (positions + groups)"""
        if not self.positions:
            self._show_status("⚠️ موقعیتی برای خروجی وجود ندارد")
            return

        default_name = (f"positions_export_"
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
                # ─── Positions ───
                if active:
                    df = PositionStorage.positions_to_dataframe(active)
                    df.to_excel(writer, sheet_name="Active_Positions",
                                index=False)
                else:
                    pd.DataFrame(columns=["پیام"]).to_excel(
                        writer, sheet_name="Active_Positions",
                        index=False)

                if history:
                    df = PositionStorage.positions_to_dataframe(history)
                    df.to_excel(writer, sheet_name="Closed_Positions",
                                index=False)
                else:
                    pd.DataFrame(columns=["پیام"]).to_excel(
                        writer, sheet_name="Closed_Positions",
                        index=False)

                # ✅ Groups
                if self.groups:
                    df_g = PositionStorage.groups_to_dataframe(
                        self.groups, self.positions)
                    if df_g is not None:
                        df_g.to_excel(
                            writer, sheet_name="Groups", index=False)

            self._show_status(
                f"✅ اکسل ذخیره شد — باز: {len(active)} | "
                f"بسته: {len(history)} | گروه: {len(self.groups)}", 8000)

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
    # آفست تک‌position
    # ═══════════════════════════════════════════════════

    def offset_position(self):
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
        """اعمال تسویه نقدی"""
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
        """اعمال نکول"""
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
            f"✅ نکول {pos.position_id} — S_T: {fmt_money(S_T)}", 6000)

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
            r = PositionPnLCalculator.calculate_exercise_total(leg, S_T)
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
            f"ارزش ذاتی: {fmt_money(total_intrinsic)} {CURRENCY}", 8000)

    def close_manually(self):
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
        """به‌روزرسانی نشان‌های تب"""
        # pending
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

        # groups
        active_groups = sum(
            1 for g in self.groups
            if g.has_any_open(self.positions)
        )
        if self.groups:
            self.tabs.setTabText(
                TAB_GROUPS, f"📁 گروه‌ها ({len(self.groups)})")
        else:
            self.tabs.setTabText(TAB_GROUPS, "📁 گروه‌ها")


__all__ = ["PositionSaverWidget", "SortableItem"]