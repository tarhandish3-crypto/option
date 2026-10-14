# position_saver/ui/import_wizard_dialog.py
# -*- coding: utf-8 -*-

"""
جادوگر ایمپورت اکسل کارگزاری — سه تب.

ساختار:
    📋 معاملات خام:          خلوت‌سازی + تکمیل اطلاعات پایه
    ✅ تأیید موقعیت‌ها:      تعیین نوع بستن هر trade
    📁 گروه‌بندی استراتژی‌ها: تعریف استراتژی + ایمپورت نهایی

قواعد کلیدی:
    ✅ trades منتقل‌شده از تب مبدأ حذف می‌شوند
    ✅ چک‌باکس «انتخاب هم‌نام» در تب ۱ و ۲
    ✅ انتخاب هوشمند: با انتخاب یک نماد، نمادهای دیگر لغو می‌شوند
    ✅ دکمه‌های «انتخاب همه» و «لغو همه» در هر دو تب
    ✅ نوع بستن الزامی برای انتقال از تب ۲ به تب ۳
    ✅ گروه‌بندی الزامی برای ذخیره‌ی نهایی
    ✅ Sort-safe: استفاده از trade_id برای همه‌ی عملیات
"""

import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QMessageBox,
    QHeaderView, QGroupBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QCheckBox, QSpinBox, QFileDialog,
    QWidget, QTabWidget, QAbstractSpinBox, QInputDialog,
    QFrame, QScrollArea, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator

from position_saver.models import (
    StrategyPosition, StrategyGroup, OptionLeg,
    LegType, PositionStatus,
)
from core.enums import OptionType
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.storage import (
    PositionStorage, today_jalali, infer_underlying_symbol,
)
from position_saver.providers import get_market_snapshot
from position_saver.theme import (
    Theme, CURRENCY, fmt_money, fmt_int, set_kind, set_tone,
)
from position_saver.importer import (
    ImportEngine, ImportSettings, ImportResult, ImportBatch,
    TradeRecord, MatchedLot,
    list_broker_names,
    CLOSE_REASON_OPEN, CLOSE_REASON_OFFSET, CLOSE_REASON_EXERCISE,
    CLOSE_REASON_CASH_SETTLE, CLOSE_REASON_DEFAULTED,
    CLOSE_REASON_YOU_DEFAULTED, CLOSE_REASON_UNKNOWN,
    CLOSE_REASON_STOCK, CLOSE_REASON_INCOMPLETE, CLOSE_REASON_LABELS,
    is_known_underlying,
    get_symbol_info, save_symbol_info, save_from_trade,
    has_symbol, get_symbol_memory_count,
)
from position_saver.ui.strategy_dialog import StrategyDialog
from position_saver.ui.net_position_dialog import NetPositionDialog


logger = logging.getLogger("PositionSaver.UI.ImportWizard")


# ═══════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════

TAB_RAW = 0
TAB_CONFIRM = 1
TAB_GROUP = 2

# ─── ستون‌های تب «📋 معاملات خام» ───
RAW_COLS = ["✓", "تاریخ", "ساعت", "سمت", "نماد",
            "نوع", "تعداد", "قیمت", "قیمت اعمال",
            "سررسید", "وضعیت"]
RAW_COL_STRIKE = 8
RAW_COL_EXPIRY = 9
RAW_COL_STATUS = 10

# ─── ستون‌های تب «✅ تأیید موقعیت‌ها» ───
CONFIRM_COLS = ["✓", "تاریخ", "ساعت", "سمت", "نماد",
                "نوع", "تعداد", "قیمت", "قیمت اعمال",
                "سررسید", "نوع بستن"]
CONFIRM_COL_CLOSE = 10

# ─── گزینه‌های ComboBox نوع بستن ───
CLOSE_OPTIONS = [
    (CLOSE_REASON_OPEN, "🟢 باز"),
    (CLOSE_REASON_OFFSET, "🔄 آفست شده"),
    (CLOSE_REASON_EXERCISE, "🏦 اعمال فیزیکی"),
    (CLOSE_REASON_CASH_SETTLE, "💵 تسویه نقدی"),
    (CLOSE_REASON_DEFAULTED, "⚖️ نکول طرف مقابل"),
    (CLOSE_REASON_YOU_DEFAULTED, "❌ نکول خودم"),
    ("skip", "⏭️ نادیده بگیر"),
]

SYNC_BULK_THRESHOLD = 500


# ═══════════════════════════════════════════════════
# SortableItem
# ═══════════════════════════════════════════════════

class SortableItem(QTableWidgetItem):
    """آیتم جدول با مقدار سورت سفارشی"""

    def __init__(self, display_text: str, sort_value: Any = None):
        super().__init__(str(display_text))
        self._sort_value = (
            sort_value if sort_value is not None else display_text
        )

    def __lt__(self, other):
        if isinstance(other, SortableItem):
            try:
                if (isinstance(self._sort_value, (int, float)) and
                        isinstance(other._sort_value, (int, float))):
                    return self._sort_value < other._sort_value
                return str(self._sort_value) < str(other._sort_value)
            except Exception:
                return str(self._sort_value) < str(other._sort_value)
        return super().__lt__(other)


# ═══════════════════════════════════════════════════
# ImportWizardDialog
# ═══════════════════════════════════════════════════

class ImportWizardDialog(QDialog):
    """جادوگر ایمپورت اکسل — سه تب."""

    def __init__(self, parent=None,
                 storage: Optional[PositionStorage] = None):
        super().__init__(parent)
        self.setWindowTitle("📥 ایمپورت اکسل کارگزاری")
        self.setLayoutDirection(Qt.RightToLeft)

        # ✅ اندازه‌ی متناسب با صفحه
        self.setMinimumSize(900, 600)
        self._fit_to_screen()

        self.storage = storage or PositionStorage()
        self.engine = ImportEngine(storage=self.storage)

        # ─── فایل ───
        self._file_path: str = ""
        self._broker: str = "مفید"
        self._settings = ImportSettings()

        # ─── state اصلی ───
        self._result: Optional[ImportResult] = None
        self._all_trades: List[TradeRecord] = []

        # ─── state تب‌ها ───
        self._raw_trades: List[TradeRecord] = []
        self._confirm_trades: List[TradeRecord] = []
        self._group_positions: List[StrategyPosition] = []
        self._groups: List[StrategyGroup] = []

        # ─── flag ها ───
        self._refreshing = False
        self._syncing = False

        self._build_ui()

    # ═══════════════════════════════════════════════
    # تنظیم اندازه‌ی پنجره
    # ═══════════════════════════════════════════════

    def _fit_to_screen(self):
        """تنظیم اندازه‌ی پنجره متناسب با صفحه"""
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                self.resize(1200, 700)
                return

            available = screen.availableGeometry()
            screen_w = available.width()
            screen_h = available.height()

            # ۹۰٪ عرض و ۹۰٪ ارتفاع
            w = min(1400, int(screen_w * 0.9))
            h = min(900, int(screen_h * 0.9))

            w = max(w, 900)
            h = max(h, 600)

            self.resize(w, h)

            # Centered
            x = available.x() + (screen_w - w) // 2
            y = available.y() + (screen_h - h) // 2
            self.move(x, y)

            logger.debug(
                f"Wizard size: {w}x{h} (screen: {screen_w}x{screen_h})")
        except Exception as e:
            logger.warning(f"Fit to screen failed: {e}")
            self.resize(1200, 700)

    # ═══════════════════════════════════════════════
    # ساخت UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab_raw(), "📋 معاملات خام")
        self.tabs.addTab(self._build_tab_confirm(), "✅ تأیید موقعیت‌ها")
        self.tabs.addTab(self._build_tab_group(), "📁 گروه‌بندی استراتژی‌ها")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        root.addLayout(self._build_footer())

    # -------------------------------------------------
    # هدر
    # -------------------------------------------------

    def _build_header(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(QLabel("🏦 کارگزاری:"))
        self.cmb_broker = QComboBox()
        names = list_broker_names()
        self.cmb_broker.addItems(names)
        if "مفید" in names:
            self.cmb_broker.setCurrentText("مفید")
        self.cmb_broker.setMinimumWidth(140)
        self.cmb_broker.currentTextChanged.connect(self._on_broker_changed)
        lay.addWidget(self.cmb_broker)

        lay.addSpacing(12)
        lay.addWidget(QLabel("📄 فایل:"))
        self.txt_file = QLineEdit()
        self.txt_file.setReadOnly(True)
        self.txt_file.setPlaceholderText("— هیچ فایلی انتخاب نشده —")
        lay.addWidget(self.txt_file, 1)

        self.btn_pick = QPushButton("📂 انتخاب فایل...")
        self.btn_pick.clicked.connect(self._pick_file)
        set_kind(self.btn_pick, "primary")
        lay.addWidget(self.btn_pick)

        self.btn_reload = QPushButton("🔄 بارگذاری مجدد")
        self.btn_reload.clicked.connect(self._reload)
        self.btn_reload.setEnabled(False)
        lay.addWidget(self.btn_reload)

        return w

    def _on_broker_changed(self, broker: str):
        self._broker = broker

    # ═══════════════════════════════════════════════
    # تب ۱: معاملات خام
    # ═══════════════════════════════════════════════

    def _build_tab_raw(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # ─── نوار اول: اطلاعات و ابزارها ───
        bar = QHBoxLayout()
        bar.setSpacing(4)

        self.lbl_raw_info = QLabel("در انتظار انتخاب فایل...")
        set_tone(self.lbl_raw_info, "muted")
        bar.addWidget(self.lbl_raw_info)
        bar.addStretch()

        # چک‌باکس‌ها
        self.chk_raw_select_same = QCheckBox("✓ هم‌نام")
        self.chk_raw_select_same.setChecked(True)
        self.chk_raw_select_same.setToolTip(
            "با تیک یک ردیف، همه‌ی ردیف‌های همان نماد تیک می‌خورند")
        bar.addWidget(self.chk_raw_select_same)

        self.chk_raw_sync = QCheckBox("🔄 همگام‌سازی")
        self.chk_raw_sync.setChecked(True)
        self.chk_raw_sync.setToolTip(
            "با تایپ در یک ردیف، همه‌ی ردیف‌های همان نماد پر می‌شوند")
        bar.addWidget(self.chk_raw_sync)

        # ✅ دکمه‌های انتخاب همه / لغو همه
        self.btn_raw_select_all = QPushButton("✓ همه")
        self.btn_raw_select_all.setToolTip("انتخاب همه‌ی ردیف‌ها")
        self.btn_raw_select_all.clicked.connect(
            lambda: self._toggle_all_raw(True))
        bar.addWidget(self.btn_raw_select_all)

        self.btn_raw_deselect_all = QPushButton("✗ هیچ")
        self.btn_raw_deselect_all.setToolTip("لغو انتخاب همه")
        self.btn_raw_deselect_all.clicked.connect(
            lambda: self._toggle_all_raw(False))
        bar.addWidget(self.btn_raw_deselect_all)

        lay.addLayout(bar)

        # ─── نوار دوم: عملیات ───
        bar2 = QHBoxLayout()
        bar2.setSpacing(4)

        self.btn_bulk_fill = QPushButton("⚡ پر کردن گروهی")
        self.btn_bulk_fill.clicked.connect(self._open_bulk_fill_dialog)
        self.btn_bulk_fill.setEnabled(False)
        bar2.addWidget(self.btn_bulk_fill)

        self.btn_memory = QPushButton("💾 حافظه")
        self.btn_memory.clicked.connect(self._show_symbol_memory)
        bar2.addWidget(self.btn_memory)

        self.btn_raw_view_symbol = QPushButton("📊 مشاهده‌ی نماد")
        self.btn_raw_view_symbol.clicked.connect(
            lambda: self._open_net_position_dialog(from_tab="raw"))
        bar2.addWidget(self.btn_raw_view_symbol)

        bar2.addStretch()

        self.btn_raw_delete = QPushButton("🗑 حذف")
        self.btn_raw_delete.clicked.connect(self._delete_raw_selected)
        set_kind(self.btn_raw_delete, "danger")
        self.btn_raw_delete.setEnabled(False)
        bar2.addWidget(self.btn_raw_delete)

        self.btn_raw_move = QPushButton("➡️ انتقال به تأیید")
        self.btn_raw_move.clicked.connect(self._move_raw_to_confirm)
        set_kind(self.btn_raw_move, "primary")
        self.btn_raw_move.setEnabled(False)
        bar2.addWidget(self.btn_raw_move)

        lay.addLayout(bar2)

        # ─── جدول ───
        self.tbl_raw = QTableWidget(0, len(RAW_COLS))
        self.tbl_raw.setHorizontalHeaderLabels(RAW_COLS)
        self._setup_table(self.tbl_raw)
        self.tbl_raw.itemChanged.connect(self._on_raw_item_changed)
        lay.addWidget(self.tbl_raw, 1)

        hint = QLabel(
            "💡 فیلدهای ناقص را پر کنید. با «🔄 همگام‌سازی»، "
            "همه‌ی ردیف‌های همان نماد یک‌جا پر می‌شوند.")
        set_tone(hint, "muted")
        lay.addWidget(hint)

        return w

    # ═══════════════════════════════════════════════
    # تب ۲: تأیید موقعیت‌ها
    # ═══════════════════════════════════════════════

    def _build_tab_confirm(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # ─── نوار اول: اطلاعات و ابزارها ───
        bar = QHBoxLayout()
        bar.setSpacing(4)

        self.lbl_confirm_info = QLabel("—")
        set_tone(self.lbl_confirm_info, "muted")
        bar.addWidget(self.lbl_confirm_info)
        bar.addStretch()

        # چک‌باکس انتخاب هم‌نام
        self.chk_confirm_select_same = QCheckBox("✓ هم‌نام")
        self.chk_confirm_select_same.setChecked(True)
        self.chk_confirm_select_same.setToolTip(
            "با تیک یک ردیف، همه‌ی ردیف‌های همان نماد تیک می‌خورند "
            "و نمادهای دیگر از تیک خارج می‌شوند")
        bar.addWidget(self.chk_confirm_select_same)

        # ✅ دکمه‌های انتخاب همه / لغو همه
        self.btn_confirm_select_all = QPushButton("✓ همه")
        self.btn_confirm_select_all.setToolTip("انتخاب همه‌ی ردیف‌ها")
        self.btn_confirm_select_all.clicked.connect(
            lambda: self._toggle_all_confirm(True))
        bar.addWidget(self.btn_confirm_select_all)

        self.btn_confirm_deselect_all = QPushButton("✗ هیچ")
        self.btn_confirm_deselect_all.setToolTip("لغو انتخاب همه")
        self.btn_confirm_deselect_all.clicked.connect(
            lambda: self._toggle_all_confirm(False))
        bar.addWidget(self.btn_confirm_deselect_all)

        lay.addLayout(bar)

        # ─── نوار دوم: عملیات ───
        bar2 = QHBoxLayout()
        bar2.setSpacing(4)

        self.btn_confirm_view_symbol = QPushButton("📊 مشاهده‌ی نماد")
        self.btn_confirm_view_symbol.clicked.connect(
            lambda: self._open_net_position_dialog(from_tab="confirm"))
        bar2.addWidget(self.btn_confirm_view_symbol)

        bar2.addStretch()

        self.btn_confirm_back = QPushButton("↩️ بازگشت به معاملات خام")
        self.btn_confirm_back.clicked.connect(
            self._move_confirm_back_to_raw)
        bar2.addWidget(self.btn_confirm_back)

        self.btn_confirm_move = QPushButton("➡️ انتقال به گروه‌بندی")
        self.btn_confirm_move.clicked.connect(
            self._move_confirm_to_group)
        set_kind(self.btn_confirm_move, "primary")
        self.btn_confirm_move.setEnabled(False)
        bar2.addWidget(self.btn_confirm_move)

        lay.addLayout(bar2)

        self.tbl_confirm = QTableWidget(0, len(CONFIRM_COLS))
        self.tbl_confirm.setHorizontalHeaderLabels(CONFIRM_COLS)
        self._setup_table(self.tbl_confirm)
        self.tbl_confirm.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        self.tbl_confirm.itemChanged.connect(
            self._on_confirm_item_changed)
        lay.addWidget(self.tbl_confirm, 1)

        hint = QLabel(
            "💡 نوع بستن هر معامله را از ComboBox تعیین کنید. "
            "تا وقتی همه‌ی ردیف‌های تیک‌خورده نوع بستن نداشته باشند، "
            "انتقال انجام نمی‌شود.")
        set_tone(hint, "muted")
        lay.addWidget(hint)

        return w

    # ═══════════════════════════════════════════════
    # تب ۳: گروه‌بندی استراتژی‌ها
    # ═══════════════════════════════════════════════

    def _build_tab_group(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # ─── نوار ابزار ───
        bar = QHBoxLayout()
        bar.setSpacing(4)

        self.lbl_group_info = QLabel("—")
        set_tone(self.lbl_group_info, "profit", big=True)
        bar.addWidget(self.lbl_group_info)
        bar.addStretch()

        self.btn_group_back = QPushButton("↩️ بازگشت")
        self.btn_group_back.clicked.connect(
            self._move_group_back_to_confirm)
        bar.addWidget(self.btn_group_back)

        self.btn_group_new = QPushButton("➕ تعریف استراتژی جدید")
        self.btn_group_new.clicked.connect(self._create_new_strategy)
        set_kind(self.btn_group_new, "primary")
        bar.addWidget(self.btn_group_new)

        self.btn_group_ungroup = QPushButton("✂️ جدا کردن")
        self.btn_group_ungroup.clicked.connect(self._ungroup_selected)
        self.btn_group_ungroup.setEnabled(False)
        bar.addWidget(self.btn_group_ungroup)

        self.btn_group_delete = QPushButton("🗑 حذف گروه")
        self.btn_group_delete.clicked.connect(self._delete_group)
        set_kind(self.btn_group_delete, "danger")
        self.btn_group_delete.setEnabled(False)
        bar.addWidget(self.btn_group_delete)

        bar.addSpacing(12)

        # ✅ دکمه‌ی شکستن موقعیت
        self.btn_split = QPushButton("🔨 شکستن موقعیت")
        self.btn_split.clicked.connect(self._split_selected_position)
        self.btn_split.setToolTip(
            "شکستن یک موقعیت به چند قطعه")
        bar.addWidget(self.btn_split)

        # ✅ دکمه‌ی ادغام
        self.btn_merge = QPushButton("🔗 ادغام موقعیت‌ها")
        self.btn_merge.clicked.connect(self._merge_selected_positions)
        self.btn_merge.setToolTip(
            "ادغام چند موقعیت سازگار")
        bar.addWidget(self.btn_merge)

        lay.addLayout(bar)

        # ─── ناحیه‌ی کارت‌ها (Scroll) ───
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.setContentsMargins(2, 2, 2, 2)
        self.groups_layout.setSpacing(8)
        self.groups_layout.addStretch()

        scroll.setWidget(self.groups_container)
        lay.addWidget(scroll, 1)

        # ─── نوار پایین ───
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_commit = QPushButton("✅ ارسال به برنامه و ذخیره")
        self.btn_commit.setMinimumHeight(38)
        self.btn_commit.setMinimumWidth(260)
        set_kind(self.btn_commit, "primary")
        self.btn_commit.clicked.connect(self._commit_import)
        self.btn_commit.setEnabled(False)
        bottom.addWidget(self.btn_commit)
        bottom.addStretch()
        lay.addLayout(bottom)

        return w

    # -------------------------------------------------
    # نوار پایین
    # -------------------------------------------------

    def _build_footer(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.addStretch()
        self.btn_close = QPushButton("❌ انصراف")
        self.btn_close.clicked.connect(self.reject)
        lay.addWidget(self.btn_close)
        return lay

    # ═══════════════════════════════════════════════
    # تنظیمات جدول
    # ═══════════════════════════════════════════════

    @staticmethod
    def _setup_table(table: QTableWidget):
        h = table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        table.setSortingEnabled(True)
        h.setSortIndicatorShown(True)
        h.setSectionsClickable(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(28)
        table.verticalHeader().setVisible(False)

    # ═══════════════════════════════════════════════
    # فایل
    # ═══════════════════════════════════════════════

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل اکسل", "",
            "Excel Files (*.xlsx *.xls)")
        if not path:
            return
        self._file_path = path
        self.txt_file.setText(path)
        self.btn_reload.setEnabled(True)
        self._run_import()

    def _reload(self):
        if self._file_path:
            self._run_import()

    # ═══════════════════════════════════════════════
    # اجرای ایمپورت
    # ═══════════════════════════════════════════════

    def _run_import(self):
        if not self._file_path:
            return

        self._broker = self.cmb_broker.currentText() or "مفید"
        self._settings = ImportSettings()

        snapshot = None
        try:
            snapshot = get_market_snapshot(
                use_cache=True, force_refresh=False)
        except Exception as e:
            logger.warning(f"Snapshot failed: {e}")

        try:
            self._result = self.engine.run(
                file_path=self._file_path,
                broker=self._broker,
                settings=self._settings,
                snapshot=snapshot,
            )
        except Exception as e:
            logger.exception(f"Engine failed: {e}")
            QMessageBox.critical(self, "خطا",
                                 f"خطا در ایمپورت:\n{e}")
            return

        if not self._result.trades:
            error_msg = "هیچ معامله‌ای در فایل یافت نشد."
            if self._result.errors:
                error_msg += "\n\nخطاها:\n" + "\n".join(
                    f"  • {e}" for e in self._result.errors)
            if self._result.warnings:
                error_msg += "\n\nهشدارها:\n" + "\n".join(
                    f"  • {w}" for w in self._result.warnings)
            QMessageBox.warning(self, "خطا", error_msg)
            return

        # ─── ذخیره‌ی مرجع ───
        self._all_trades = list(self._result.trades)

        # ─── پاکسازی انتخاب‌ها ───
        for t in self._all_trades:
            t.is_selected = False
            t.auto_selected = False

        # ─── تفکیک بر اساس وضعیت ───
        self._raw_trades = []
        self._confirm_trades = []
        for t in self._all_trades:
            if t.is_incomplete:
                self._raw_trades.append(t)
            else:
                self._confirm_trades.append(t)

        # ─── پاکسازی گروه‌ها ───
        self._group_positions = []
        self._groups = []

        self._refresh_raw()
        self._refresh_confirm()
        self._refresh_group()

        self.tabs.setCurrentIndex(TAB_RAW)

    # ═══════════════════════════════════════════════
    # تب‌بندی
    # ═══════════════════════════════════════════════

    def _on_tab_changed(self, idx: int):
        if self._refreshing:
            return
        if idx == TAB_RAW:
            self._refresh_raw()
        elif idx == TAB_CONFIRM:
            self._refresh_confirm()
        elif idx == TAB_GROUP:
            self._refresh_group()

    # ═══════════════════════════════════════════════
    # تب ۱: Refresh
    # ═══════════════════════════════════════════════

    def _refresh_raw(self):
        self._refreshing = True
        try:
            self.tbl_raw.setSortingEnabled(False)
            self.tbl_raw.setRowCount(0)

            for t in self._raw_trades:
                row = self.tbl_raw.rowCount()
                self.tbl_raw.insertRow(row)
                self._fill_raw_row(row, t)
                self._install_raw_widgets(row, t)

            self.tbl_raw.setSortingEnabled(True)

            # ─── آمار ───
            n_raw = len(self._raw_trades)
            n_confirm = len(self._confirm_trades)
            n_group = len(self._group_positions)
            n_memory = get_symbol_memory_count()

            self.lbl_raw_info.setText(
                f"خام: {n_raw}  |  تأیید: {n_confirm}  |  "
                f"گروه: {n_group}  |  حافظه: {n_memory}")
        finally:
            self._refreshing = False

        self._update_raw_buttons()

    def _fill_raw_row(self, row: int, t: TradeRecord):
        # ✓ با trade_id
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if t.is_selected else Qt.Unchecked)
        chk.setData(Qt.UserRole, t.trade_id)
        self.tbl_raw.setItem(row, 0, chk)

        # تاریخ / ساعت
        self.tbl_raw.setItem(row, 1,
            SortableItem(t.raw_date or "—", t.raw_date or ""))
        self.tbl_raw.setItem(row, 2,
            SortableItem(t.raw_time or "—", t.raw_time or ""))

        # سمت
        side_item = SortableItem(
            t.side.label_fa, 0 if t.is_buy else 1)
        side_item.setTextAlignment(Qt.AlignCenter)
        side_item.setForeground(
            QColor(Theme.PROFIT if t.is_buy else Theme.LOSS))
        self.tbl_raw.setItem(row, 3, side_item)

        # نماد
        sym_item = SortableItem(t.symbol, t.symbol)
        if has_symbol(t.symbol):
            sym_item.setToolTip(f"{t.symbol}\n✅ در حافظه موجود")
        self.tbl_raw.setItem(row, 4, sym_item)

        # نوع
        kind_text, kind_order = "—", 99
        if t.is_option:
            if t.is_call:
                kind_text, kind_order = "CALL", 1
            else:
                kind_text, kind_order = "PUT", 2
        elif t.is_stock:
            kind_text, kind_order = "سهم", 3
        elif t.is_unknown:
            kind_text, kind_order = "❓", 4
        self.tbl_raw.setItem(row, 5,
            SortableItem(kind_text, kind_order))

        # تعداد
        qty_item = SortableItem(fmt_int(t.quantity), t.quantity)
        qty_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_raw.setItem(row, 6, qty_item)

        # قیمت
        pr_item = SortableItem(fmt_money(t.price), t.price)
        pr_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_raw.setItem(row, 7, pr_item)

        # ستون ۸ و ۹ در _install_raw_widgets
        # ستون ۱۰: وضعیت
        self._set_raw_status(row, t)

    def _set_raw_status(self, row: int, t: TradeRecord):
        try:
            is_ready = t.is_complete
            text = "✅ آماده" if is_ready else "⚠️ ناقص"
            item = SortableItem(text, 0 if is_ready else 1)
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(
                QColor(Theme.PROFIT if is_ready else Theme.WARN))
            self.tbl_raw.setItem(row, RAW_COL_STATUS, item)
        except Exception as e:
            logger.debug(f"set_raw_status failed: {e}")

    def _install_raw_widgets(self, row: int, t: TradeRecord,
                             force: bool = True):
        """افزودن ویجت‌های inline (strike + expiry)"""
        # ─── strike ───
        spin_strike = QSpinBox()
        spin_strike.setRange(0, 1_000_000_000)
        spin_strike.setSingleStep(50)
        spin_strike.setGroupSeparatorShown(True)
        spin_strike.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_strike.setValue(int(t.strike_price or 0))
        spin_strike.valueChanged.connect(
            lambda _, tr=t, r=row:
                self._on_raw_edit(tr, r, "strike"))
        self.tbl_raw.setCellWidget(row, RAW_COL_STRIKE, spin_strike)

        # ─── expiry ───
        line_expiry = QLineEdit(t.expiry_date or "")
        line_expiry.setPlaceholderText("1405/05/25")
        validator = QRegularExpressionValidator(
            QRegularExpression(r'^\d{0,4}(/\d{0,2}(/\d{0,2})?)?$'))
        line_expiry.setValidator(validator)
        line_expiry.textChanged.connect(
            lambda _, tr=t, r=row:
                self._on_raw_edit(tr, r, "expiry"))
        self.tbl_raw.setCellWidget(row, RAW_COL_EXPIRY, line_expiry)

        t._inline_widgets = {
            "strike": spin_strike,
            "expiry": line_expiry,
        }

    # ═══════════════════════════════════════════════
    # تب ۱: ویرایش
    # ═══════════════════════════════════════════════

    def _on_raw_edit(self, t: TradeRecord, row: int, field: str):
        if self._refreshing or self._syncing:
            return

        widgets = getattr(t, "_inline_widgets", None)
        if not widgets:
            return

        if field == "strike":
            value = float(widgets["strike"].value())
            t.strike_price = value if value > 0 else None
        elif field == "expiry":
            value = widgets["expiry"].text().strip()
            t.expiry_date = value

        t.user_edited = True
        t.needs_review = not t.is_complete

        # ─── همگام‌سازی ───
        if self.chk_raw_sync.isChecked():
            self._sync_raw_field(t, field, value)

        # ─── ذخیره در حافظه ───
        if t.strike_price and t.expiry_date:
            try:
                save_from_trade(t)
            except Exception as e:
                logger.debug(f"save_from_trade failed: {e}")

        # ─── به‌روزرسانی وضعیت با تأخیر ───
        delay = (300 if len(self._raw_trades) > SYNC_BULK_THRESHOLD
                 else 150)
        QTimer.singleShot(delay, self._refresh_raw_statuses)

    def _sync_raw_field(self, source_t: TradeRecord,
                         field: str, value):
        """همگام‌سازی یک فیلد با ردیف‌های هم‌نام"""
        self._syncing = True
        try:
            for row in range(self.tbl_raw.rowCount()):
                t = self._find_raw_trade_for_row(row)
                if t is None or t is source_t:
                    continue
                if t.symbol != source_t.symbol:
                    continue

                widgets = getattr(t, "_inline_widgets", None)
                if not widgets:
                    continue
                target = widgets.get(field)
                if target is None:
                    continue

                target.blockSignals(True)
                try:
                    if field == "strike":
                        target.setValue(int(value or 0))
                        t.strike_price = (
                            float(value) if value else None)
                    elif field == "expiry":
                        target.setText(str(value or ""))
                        t.expiry_date = str(value) if value else ""

                    t.user_edited = True
                    t.needs_review = not t.is_complete
                finally:
                    target.blockSignals(False)
        finally:
            self._syncing = False

    def _refresh_raw_statuses(self):
        """به‌روزرسانی ستون وضعیت همه‌ی ردیف‌های تب ۱"""
        try:
            if self._refreshing:
                return
            was = self.tbl_raw.isSortingEnabled()
            self.tbl_raw.setSortingEnabled(False)

            for row in range(self.tbl_raw.rowCount()):
                t = self._find_raw_trade_for_row(row)
                if t is not None:
                    self._set_raw_status(row, t)
                    # ─── تیک خودکار ───
                    if t.is_complete and not t.auto_selected:
                        chk = self.tbl_raw.item(row, 0)
                        if chk and chk.checkState() != Qt.Checked:
                            self._refreshing = True
                            try:
                                chk.setCheckState(Qt.Checked)
                                t.is_selected = True
                                t.auto_selected = True
                            finally:
                                self._refreshing = False

            self.tbl_raw.setSortingEnabled(was)
            self._update_raw_buttons()
        except Exception as e:
            logger.debug(f"refresh_raw_statuses failed: {e}")

    # ═══════════════════════════════════════════════
    # تب ۱: پیدا کردن trade
    # ═══════════════════════════════════════════════

    def _find_raw_trade_for_row(self, row: int) -> Optional[TradeRecord]:
        if row < 0 or row >= self.tbl_raw.rowCount():
            return None

        chk = self.tbl_raw.item(row, 0)
        if chk is None:
            return None
        trade_id = chk.data(Qt.UserRole)
        if trade_id:
            for t in self._raw_trades:
                if t.trade_id == trade_id:
                    return t

        strike_widget = self.tbl_raw.cellWidget(row, RAW_COL_STRIKE)
        if strike_widget is not None:
            for t in self._raw_trades:
                widgets = getattr(t, "_inline_widgets", None)
                if widgets and widgets.get("strike") is strike_widget:
                    return t
        return None

    # ═══════════════════════════════════════════════
    # تب ۱: کلیک چک‌باکس
    # ═══════════════════════════════════════════════

    def _on_raw_item_changed(self, item: QTableWidgetItem):
        """
        وقتی چک‌باکس تغییر کرد.

        ✅ رفتار هوشمند:
            - اگر چک‌باکس «هم‌نام» فعال و کاربر یک ردیف را تیک بزند:
              → فقط همان ردیف + هم‌نام‌هایش تیک می‌خورند
              → ردیف‌های هم‌نامِ نماد قبلی (اگر متفاوت باشد) از تیک خارج می‌شوند
            - اگر کاربر تیک را بردارد:
              → فقط همان ردیف از تیک خارج می‌شود
        """
        if self._refreshing:
            return
        if item.column() != 0:
            return

        trade_id = item.data(Qt.UserRole)
        if not trade_id:
            return

        trade = None
        for t in self._raw_trades:
            if t.trade_id == trade_id:
                trade = t
                break
        if trade is None:
            return

        is_now = (item.checkState() == Qt.Checked)
        trade.is_selected = is_now
        if trade.auto_selected and not is_now:
            trade.auto_selected = False

        if is_now and self.chk_raw_select_same.isChecked():
            # ۱. همه‌ی هم‌نام‌های این نماد را تیک بزن
            self._select_raw_same_symbol(trade.symbol, trade_id)
            # ۲. ردیف‌های هم‌نامِ نمادهای دیگر را از تیک خارج کن
            self._deselect_raw_other_symbols(trade.symbol)

        self._update_raw_buttons()

    def _select_raw_same_symbol(self, symbol: str, exclude_id: str):
        """انتخاب همه‌ی ردیف‌های هم‌نام"""
        self._refreshing = True
        try:
            for row in range(self.tbl_raw.rowCount()):
                chk = self.tbl_raw.item(row, 0)
                if chk is None:
                    continue
                tid = chk.data(Qt.UserRole)
                if tid == exclude_id:
                    continue

                t = None
                for tr in self._raw_trades:
                    if tr.trade_id == tid:
                        t = tr
                        break
                if t is None or t.symbol != symbol:
                    continue

                if chk.checkState() != Qt.Checked:
                    chk.setCheckState(Qt.Checked)
                    t.is_selected = True
        finally:
            self._refreshing = False

    def _deselect_raw_other_symbols(self, keep_symbol: str):
        """
        لغو انتخاب ردیف‌های نمادهای دیگر.

        وقتی کاربر یک نماد را انتخاب می‌کند، نمادهای قبلی
        از تیک خارج می‌شوند تا کاربر بدون سردرگمی کار کند.
        """
        self._refreshing = True
        try:
            for row in range(self.tbl_raw.rowCount()):
                chk = self.tbl_raw.item(row, 0)
                if chk is None:
                    continue
                tid = chk.data(Qt.UserRole)
                if not tid:
                    continue

                t = None
                for tr in self._raw_trades:
                    if tr.trade_id == tid:
                        t = tr
                        break
                if t is None:
                    continue

                if t.symbol != keep_symbol and \
                        chk.checkState() == Qt.Checked:
                    chk.setCheckState(Qt.Unchecked)
                    t.is_selected = False
                    t.auto_selected = False
        finally:
            self._refreshing = False

    # ═══════════════════════════════════════════════
    # تب ۱: انتخاب همه / لغو همه
    # ═══════════════════════════════════════════════

    def _toggle_all_raw(self, state: bool):
        """انتخاب یا لغو انتخاب همه‌ی ردیف‌های تب ۱"""
        if not self._raw_trades:
            return

        n = len(self._raw_trades)
        action = "انتخاب" if state else "لغو انتخاب"

        if state and n > 20:
            reply = QMessageBox.question(
                self, f"تأیید {action}",
                f"آیا از {action} همه‌ی {n} معامله مطمئن هستید؟",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self._refreshing = True
        try:
            for row in range(self.tbl_raw.rowCount()):
                chk = self.tbl_raw.item(row, 0)
                if chk is None:
                    continue
                chk.setCheckState(
                    Qt.Checked if state else Qt.Unchecked)

            for t in self._raw_trades:
                t.is_selected = state
                if not state:
                    t.auto_selected = False
        finally:
            self._refreshing = False

        self._update_raw_buttons()

    def _update_raw_buttons(self):
        n = 0
        for row in range(self.tbl_raw.rowCount()):
            chk = self.tbl_raw.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                n += 1

        self.btn_raw_delete.setEnabled(n > 0)
        self.btn_raw_move.setEnabled(n > 0)
        self.btn_bulk_fill.setEnabled(len(self._raw_trades) > 0)

        if n > 0:
            self.btn_raw_delete.setText(f"🗑 حذف ({n})")
            self.btn_raw_move.setText(f"➡️ انتقال به تأیید ({n})")
        else:
            self.btn_raw_delete.setText("🗑 حذف")
            self.btn_raw_move.setText("➡️ انتقال به تأیید")

    # ═══════════════════════════════════════════════
    # تب ۱: حذف
    # ═══════════════════════════════════════════════

    def _get_ticked_raw_trades(self) -> List[TradeRecord]:
        ticked = []
        seen = set()
        for row in range(self.tbl_raw.rowCount()):
            chk = self.tbl_raw.item(row, 0)
            if chk is None or chk.checkState() != Qt.Checked:
                continue
            tid = chk.data(Qt.UserRole)
            if not tid or tid in seen:
                continue
            seen.add(tid)
            for t in self._raw_trades:
                if t.trade_id == tid:
                    ticked.append(t)
                    break
        return ticked

    def _delete_raw_selected(self):
        ticked = self._get_ticked_raw_trades()
        if not ticked:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند ردیف را تیک بزنید.")
            return

        reply = QMessageBox.question(
            self, "تأیید حذف",
            f"⚠️ آیا از نادیده گرفتن {len(ticked)} معامله مطمئن "
            f"هستید؟\n\n"
            f"این معاملات از پنجره حذف می‌شوند و هرگز در برنامه "
            f"ذخیره نخواهند شد.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        ticked_ids = {t.trade_id for t in ticked}
        self._raw_trades = [
            t for t in self._raw_trades
            if t.trade_id not in ticked_ids]
        self._all_trades = [
            t for t in self._all_trades
            if t.trade_id not in ticked_ids]

        self._refresh_raw()
        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ticked)} معامله نادیده گرفته شد.")

    # ═══════════════════════════════════════════════
    # تب ۱: انتقال به تب ۲
    # ═══════════════════════════════════════════════

    def _move_raw_to_confirm(self):
        ticked = self._get_ticked_raw_trades()
        if not ticked:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند ردیف را تیک بزنید.")
            return

        ready = [t for t in ticked if t.is_complete]
        not_ready = [t for t in ticked if not t.is_complete]

        if not ready:
            QMessageBox.warning(
                self, "خطا",
                f"⚠️ هیچ‌کدام از {len(ticked)} ردیف اطلاعات کامل "
                f"ندارند.\n\n"
                f"لطفاً قیمت اعمال و سررسید را پر کنید.")
            return

        if not_ready:
            reply = QMessageBox.question(
                self, "هشدار",
                f"⚠️ از {len(ticked)} ردیف، {len(not_ready)} ناقص "
                f"هستند.\n\n"
                f"فقط {len(ready)} ردیف کامل منتقل شود؟",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        reply2 = QMessageBox.question(
            self, "تأیید انتقال",
            f"{len(ready)} معامله به تب «تأیید موقعیت‌ها» منتقل "
            f"می‌شود.\n\n"
            f"این معاملات از تب «معاملات خام» حذف می‌شوند.",
            QMessageBox.Yes | QMessageBox.No)
        if reply2 != QMessageBox.Yes:
            return

        ready_ids = {t.trade_id for t in ready}
        self._raw_trades = [
            t for t in self._raw_trades
            if t.trade_id not in ready_ids]

        for t in ready:
            t.is_selected = False
            t.auto_selected = False
            self._confirm_trades.append(t)

        self._refresh_raw()
        self._refresh_confirm()

        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ready)} معامله به تب «تأیید موقعیت‌ها» منتقل شد.")

    # ═══════════════════════════════════════════════
    # تب ۲: Refresh
    # ═══════════════════════════════════════════════

    def _refresh_confirm(self):
        self._refreshing = True
        try:
            self.tbl_confirm.setSortingEnabled(False)
            self.tbl_confirm.setRowCount(0)

            for t in self._confirm_trades:
                row = self.tbl_confirm.rowCount()
                self.tbl_confirm.insertRow(row)
                self._fill_confirm_row(row, t)

            self.tbl_confirm.setSortingEnabled(True)

            n = len(self._confirm_trades)
            self.lbl_confirm_info.setText(
                f"✅ تأیید موقعیت‌ها ({n} معامله)")
        finally:
            self._refreshing = False

        self._update_confirm_buttons()

    def _fill_confirm_row(self, row: int, t: TradeRecord):
        # ✓
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if t.is_selected else Qt.Unchecked)
        chk.setData(Qt.UserRole, t.trade_id)
        self.tbl_confirm.setItem(row, 0, chk)

        # تاریخ / ساعت
        self.tbl_confirm.setItem(row, 1,
            SortableItem(t.raw_date or "—", t.raw_date or ""))
        self.tbl_confirm.setItem(row, 2,
            SortableItem(t.raw_time or "—", t.raw_time or ""))

        # سمت
        side_item = SortableItem(
            t.side.label_fa, 0 if t.is_buy else 1)
        side_item.setTextAlignment(Qt.AlignCenter)
        side_item.setForeground(
            QColor(Theme.PROFIT if t.is_buy else Theme.LOSS))
        self.tbl_confirm.setItem(row, 3, side_item)

        # نماد
        self.tbl_confirm.setItem(row, 4,
            SortableItem(t.symbol, t.symbol))

        # نوع
        kind_text, kind_order = "—", 99
        if t.is_option:
            if t.is_call:
                kind_text, kind_order = "CALL", 1
            else:
                kind_text, kind_order = "PUT", 2
        elif t.is_stock:
            kind_text, kind_order = "سهم", 3
        self.tbl_confirm.setItem(row, 5,
            SortableItem(kind_text, kind_order))

        # تعداد
        qty_item = SortableItem(fmt_int(t.quantity), t.quantity)
        qty_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_confirm.setItem(row, 6, qty_item)

        # قیمت
        pr_item = SortableItem(fmt_money(t.price), t.price)
        pr_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_confirm.setItem(row, 7, pr_item)

        # strike
        sp_val = t.strike_price or 0
        sp_item = SortableItem(
            fmt_money(sp_val) if t.strike_price else "—", sp_val)
        sp_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_confirm.setItem(row, 8, sp_item)

        # سررسید
        exp_item = SortableItem(
            t.expiry_date or "—", t.expiry_date or "")
        exp_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_confirm.setItem(row, 9, exp_item)

        # ComboBox نوع بستن
        self._install_confirm_close_combo(row, t)

    def _install_confirm_close_combo(self, row: int, t: TradeRecord):
        """ComboBox نوع بستن"""
        combo = QComboBox()
        combo.addItem("— انتخاب کنید —", "")
        for code, label in CLOSE_OPTIONS:
            combo.addItem(label, code)

        idx = combo.findData(t.close_reason)
        if idx > 0:
            combo.setCurrentIndex(idx)

        combo.setProperty("trade_id", t.trade_id)
        combo.currentIndexChanged.connect(
            lambda _, c=combo, tr=t:
                self._on_confirm_close_changed(c, tr))
        self.tbl_confirm.setCellWidget(row, CONFIRM_COL_CLOSE, combo)

    def _on_confirm_close_changed(self, combo: QComboBox,
                                    t: TradeRecord):
        code = combo.currentData()
        if not code:
            return

        # ─── نادیده بگیر ───
        if code == "skip":
            reply = QMessageBox.question(
                self, "تأیید نادیده گرفتن",
                f"⚠️ آیا از نادیده گرفتن این معامله مطمئن هستید؟\n\n"
                f"{t.side.label_fa} {t.symbol} ({t.raw_date})",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                combo.blockSignals(True)
                idx = combo.findData(t.close_reason)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)
                return

            if t in self._confirm_trades:
                self._confirm_trades.remove(t)
            if t in self._all_trades:
                self._all_trades.remove(t)
            self._refresh_confirm()
            return

        t.close_reason = code
        t.user_chosen_reason = True

        self._update_confirm_buttons()

    def _on_confirm_item_changed(self, item: QTableWidgetItem):
        """
        وقتی چک‌باکس تغییر کرد.

        ✅ رفتار هوشمند:
            - اگر چک‌باکس «هم‌نام» فعال و کاربر یک ردیف را تیک بزند:
              → فقط همان ردیف + هم‌نام‌هایش تیک می‌خورند
              → ردیف‌های هم‌نامِ نماد قبلی (اگر متفاوت باشد) از تیک خارج می‌شوند
            - اگر کاربر تیک را بردارد:
              → فقط همان ردیف از تیک خارج می‌شود
        """
        if self._refreshing:
            return
        if item.column() != 0:
            return

        tid = item.data(Qt.UserRole)
        if not tid:
            return

        trade = None
        for t in self._confirm_trades:
            if t.trade_id == tid:
                trade = t
                break
        if trade is None:
            return

        is_now = (item.checkState() == Qt.Checked)
        trade.is_selected = is_now
        if trade.auto_selected and not is_now:
            trade.auto_selected = False

        if is_now and self.chk_confirm_select_same.isChecked():
            # ۱. همه‌ی هم‌نام‌های این نماد را تیک بزن
            self._select_confirm_same_symbol(trade.symbol, tid)
            # ۲. ردیف‌های هم‌نامِ نمادهای دیگر را از تیک خارج کن
            self._deselect_confirm_other_symbols(trade.symbol)

        self._update_confirm_buttons()

    def _select_confirm_same_symbol(self, symbol: str, exclude_id: str):
        """انتخاب همه‌ی ردیف‌های هم‌نام"""
        self._refreshing = True
        try:
            for row in range(self.tbl_confirm.rowCount()):
                chk = self.tbl_confirm.item(row, 0)
                if chk is None:
                    continue
                tid = chk.data(Qt.UserRole)
                if tid == exclude_id:
                    continue

                trade = None
                for tr in self._confirm_trades:
                    if tr.trade_id == tid:
                        trade = tr
                        break
                if trade is None or trade.symbol != symbol:
                    continue

                if chk.checkState() != Qt.Checked:
                    chk.setCheckState(Qt.Checked)
                    trade.is_selected = True
        finally:
            self._refreshing = False

    def _deselect_confirm_other_symbols(self, keep_symbol: str):
        """
        لغو انتخاب ردیف‌های نمادهای دیگر.

        وقتی کاربر یک نماد را انتخاب می‌کند، نمادهای قبلی
        از تیک خارج می‌شوند تا کاربر بدون سردرگمی کار کند.
        """
        self._refreshing = True
        try:
            for row in range(self.tbl_confirm.rowCount()):
                chk = self.tbl_confirm.item(row, 0)
                if chk is None:
                    continue
                tid = chk.data(Qt.UserRole)
                if not tid:
                    continue

                trade = None
                for tr in self._confirm_trades:
                    if tr.trade_id == tid:
                        trade = tr
                        break
                if trade is None:
                    continue

                if trade.symbol != keep_symbol and \
                        chk.checkState() == Qt.Checked:
                    chk.setCheckState(Qt.Unchecked)
                    trade.is_selected = False
                    trade.auto_selected = False
        finally:
            self._refreshing = False

    def _get_ticked_confirm_trades(self) -> List[TradeRecord]:
        ticked = []
        seen = set()
        for row in range(self.tbl_confirm.rowCount()):
            chk = self.tbl_confirm.item(row, 0)
            if chk is None or chk.checkState() != Qt.Checked:
                continue
            tid = chk.data(Qt.UserRole)
            if not tid or tid in seen:
                continue
            seen.add(tid)
            for t in self._confirm_trades:
                if t.trade_id == tid:
                    ticked.append(t)
                    break
        return ticked

    def _update_confirm_buttons(self):
        ticked = self._get_ticked_confirm_trades()
        n = len(ticked)
        self.btn_confirm_move.setEnabled(n > 0)
        self.btn_confirm_back.setEnabled(n > 0)

        if n > 0:
            self.btn_confirm_move.setText(
                f"➡️ انتقال به گروه‌بندی ({n})")
            self.btn_confirm_back.setText(f"↩️ بازگشت ({n})")
        else:
            self.btn_confirm_move.setText("➡️ انتقال به گروه‌بندی")
            self.btn_confirm_back.setText("↩️ بازگشت به معاملات خام")

    # ═══════════════════════════════════════════════
    # تب ۲: انتخاب همه / لغو همه
    # ═══════════════════════════════════════════════

    def _toggle_all_confirm(self, state: bool):
        """انتخاب یا لغو انتخاب همه‌ی ردیف‌های تب ۲"""
        if not self._confirm_trades:
            return

        n = len(self._confirm_trades)
        action = "انتخاب" if state else "لغو انتخاب"

        if state and n > 20:
            reply = QMessageBox.question(
                self, f"تأیید {action}",
                f"آیا از {action} همه‌ی {n} معامله مطمئن هستید؟",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self._refreshing = True
        try:
            for row in range(self.tbl_confirm.rowCount()):
                chk = self.tbl_confirm.item(row, 0)
                if chk is None:
                    continue
                chk.setCheckState(
                    Qt.Checked if state else Qt.Unchecked)

            for t in self._confirm_trades:
                t.is_selected = state
                if not state:
                    t.auto_selected = False
        finally:
            self._refreshing = False

        self._update_confirm_buttons()

    # ═══════════════════════════════════════════════
    # تب ۲: بازگشت
    # ═══════════════════════════════════════════════

    def _move_confirm_back_to_raw(self):
        ticked = self._get_ticked_confirm_trades()
        if not ticked:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند ردیف را تیک بزنید.")
            return

        reply = QMessageBox.question(
            self, "تأیید بازگشت",
            f"{len(ticked)} معامله به تب «معاملات خام» برگردانده "
            f"می‌شوند.\n\n"
            f"نوع بستن آن‌ها پاک می‌شود.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        ticked_ids = {t.trade_id for t in ticked}
        self._confirm_trades = [
            t for t in self._confirm_trades
            if t.trade_id not in ticked_ids]

        for t in ticked:
            t.is_selected = False
            t.auto_selected = False
            t.close_reason = ""
            t.user_chosen_reason = False
            self._raw_trades.append(t)

        self._refresh_raw()
        self._refresh_confirm()

        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ticked)} معامله به تب «معاملات خام» بازگشت.")

    # ═══════════════════════════════════════════════
    # تب ۲: انتقال به تب ۳
    # ═══════════════════════════════════════════════

    def _move_confirm_to_group(self):
        ticked = self._get_ticked_confirm_trades()
        if not ticked:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند ردیف را تیک بزنید.")
            return

        # ─── چک نوع بستن ───
        no_reason = [
            t for t in ticked
            if not t.close_reason or t.close_reason == ""
        ]
        if no_reason:
            names = "\n".join(
                f"  • {t.side.label_fa} {t.symbol} ({t.raw_date})"
                for t in no_reason[:10])
            if len(no_reason) > 10:
                names += f"\n  ... و {len(no_reason) - 10} مورد دیگر"

            QMessageBox.warning(
                self, "خطا",
                f"❌ {len(no_reason)} معامله نوع بستن مشخص ندارند.\n\n"
                f"لطفاً قبل از انتقال، نوع بستن همه‌ی ردیف‌های "
                f"تیک‌خورده را تعیین کنید:\n\n{names}")
            return

        reply = QMessageBox.question(
            self, "تأیید انتقال",
            f"{len(ticked)} معامله به تب «گروه‌بندی استراتژی‌ها» "
            f"منتقل می‌شود.\n\n"
            f"این معاملات از تب «تأیید موقعیت‌ها» حذف می‌شوند.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        ticked_ids = {t.trade_id for t in ticked}
        self._confirm_trades = [
            t for t in self._confirm_trades
            if t.trade_id not in ticked_ids]

        for t in ticked:
            t.is_selected = False
            t.auto_selected = False

            pos = self._trade_to_position(t)
            if pos:
                pos.group_id = ""
                self._group_positions.append(pos)

        self._refresh_confirm()
        self._refresh_group()

        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ticked)} موقعیت به تب «گروه‌بندی» منتقل شد.")

    # ═══════════════════════════════════════════════
    # تبدیل trade → StrategyPosition
    # ═══════════════════════════════════════════════

    def _trade_to_position(
        self, t: TradeRecord
    ) -> Optional[StrategyPosition]:
        leg = OptionLeg(
            symbol=t.symbol,
            is_option=t.is_option,
            option_kind=t.option_kind or OptionType.STOCK,
            leg_type=t.side,
            strike_price=t.strike_price or 0.0,
            contract_size=t.effective_contract_size,
            quantity=t.quantity,
            entry_price=t.price,
            current_price=t.price,
            expiry_date=t.expiry_date or "",
            ins_code=t.ins_code or "",
            ins_code_ua=t.ins_code_ua or "",
            open_date=t.raw_date,
            open_time=t.raw_time,
            trade_time=t.raw_time,
            source="excel_import",
            trade_ref=t.trade_id,
            needs_review=t.needs_review,
            close_reason=t.close_reason,
        )
        leg.entry_fee = PositionPnLCalculator.calculate_leg_entry_fee(leg)

        status = PositionStatus.OPEN
        if t.close_reason == CLOSE_REASON_OFFSET:
            leg.close_price = t.close_price or 0.0
            leg.close_fee = (
                PositionPnLCalculator.calculate_leg_close_fee(
                    leg, leg.close_price))
            leg.close_date = t.close_date
            status = PositionStatus.CLOSED
        elif t.close_reason == CLOSE_REASON_EXERCISE:
            leg.close_price = t.close_price or 0.0
            leg.close_fee = 0.0
            status = PositionStatus.EXERCISED
        elif t.close_reason == CLOSE_REASON_CASH_SETTLE:
            leg.close_price = t.close_price or 0.0
            leg.close_fee = 0.0
            status = PositionStatus.CASH_SETTLED
        elif t.close_reason == CLOSE_REASON_DEFAULTED:
            leg.close_price = t.close_price or 0.0
            status = PositionStatus.DEFAULTED
        elif t.close_reason == CLOSE_REASON_YOU_DEFAULTED:
            leg.close_price = t.close_price or 0.0
            status = PositionStatus.YOU_DEFAULTED
        elif t.close_reason == CLOSE_REASON_OPEN:
            status = PositionStatus.OPEN

        from position_saver.importer.suggest import (
            suggest_strategy_name)
        sname = suggest_strategy_name([t]) or ""

        usym = t.underlying_symbol or t.symbol
        if t.is_option and not t.underlying_symbol:
            usym = infer_underlying_symbol(t.symbol)

        pos = StrategyPosition(
            strategy_name=sname,
            strategy_type="",
            broker_name=self._broker,
            underlying_symbol=usym,
            execution_date=t.raw_date,
            expiry_date=t.expiry_date or "",
            status=status,
            legs=[leg],
            alert_target_roi=self._settings.default_alert_roi,
            source="excel_import",
            needs_review=t.needs_review,
            close_reason=t.close_reason,
        )

        if status != PositionStatus.OPEN:
            pos.close_date = t.close_date or t.raw_date

        return pos

    # ═══════════════════════════════════════════════
    # تب ۳: Refresh
    # ═══════════════════════════════════════════════

    def _refresh_group(self):
        self._refreshing = True
        try:
            # پاکسازی layout
            while self.groups_layout.count() > 1:
                item = self.groups_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            # ─── گروه‌های تشکیل‌شده ───
            for group in self._groups:
                card = self._build_group_card(group)
                self.groups_layout.insertWidget(
                    self.groups_layout.count() - 1, card)

            # ─── بدون گروه ───
            ungrouped = [
                p for p in self._group_positions
                if not p.group_id
            ]
            if ungrouped:
                card = self._build_ungrouped_card(ungrouped)
                self.groups_layout.insertWidget(
                    self.groups_layout.count() - 1, card)

            # ─── آمار ───
            n_pos = len(self._group_positions)
            n_groups = len(self._groups)
            n_ungrouped = len(ungrouped)

            self.lbl_group_info.setText(
                f"📁 موقعیت‌ها: {n_pos}  |  گروه‌ها: {n_groups}  |  "
                f"بدون گروه: {n_ungrouped}")
        finally:
            self._refreshing = False

        self._update_group_buttons()

    def _build_ungrouped_card(
        self, positions: List[StrategyPosition]
    ) -> QWidget:
        """کارت «بدون استراتژی»"""
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card {{ background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; "
            f"border-radius: 6px; }}")

        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        title = QLabel(
            f"📁 بدون استراتژی ({len(positions)} موقعیت)")
        set_tone(title, "warn", big=True)
        lay.addWidget(title)

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels([
            "✓", "نماد", "لگ", "تعداد", "ورود", "وضعیت"])
        h = table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        table.setColumnWidth(0, 36)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 160)
        table.setColumnWidth(3, 60)
        table.setColumnWidth(4, 90)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(26)
        table.verticalHeader().setVisible(False)

        for pos in positions:
            row = table.rowCount()
            table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, pos.position_id)
            table.setItem(row, 0, chk)

            table.setItem(row, 1, QTableWidgetItem(
                pos.underlying_symbol or "—"))

            leg_text = "—"
            if pos.legs:
                leg = pos.legs[0]
                leg_text = f"{leg.leg_type.label_fa} {leg.symbol}"
            table.setItem(row, 2, QTableWidgetItem(leg_text))

            qty = pos.legs[0].quantity if pos.legs else 0
            table.setItem(row, 3, QTableWidgetItem(fmt_int(qty)))

            entry = pos.legs[0].entry_price if pos.legs else 0
            table.setItem(row, 4, QTableWidgetItem(fmt_money(entry)))

            status_item = QTableWidgetItem(pos.status.label_fa)
            status_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 5, status_item)

        h_table = min(180, 26 * len(positions) + 30)
        table.setFixedHeight(h_table)
        lay.addWidget(table)

        return card

    def _build_group_card(self, group: StrategyGroup) -> QWidget:
        """کارت یک گروه"""
        positions = [
            p for p in self._group_positions
            if p.position_id in group.position_ids
        ]

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card {{ background-color: {Theme.CARD}; "
            f"border: 2px solid {Theme.PROFIT}; "
            f"border-radius: 6px; }}")

        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        title = QLabel(
            f"📁 {group.label_fa} ({len(positions)} موقعیت)")
        set_tone(title, "profit", big=True)
        header.addWidget(title)

        type_label = QLabel(f"نوع: {group.strategy_type or 'سفارشی'}")
        set_tone(type_label, "muted")
        header.addWidget(type_label)
        header.addStretch()

        total_pnl = group.total_live_pnl(self._group_positions)
        pnl_label = QLabel(
            f"💰 PnL: {fmt_money(total_pnl)} {CURRENCY}")
        if total_pnl > 0:
            set_tone(pnl_label, "profit", big=True)
        elif total_pnl < 0:
            set_tone(pnl_label, "loss", big=True)
        else:
            set_tone(pnl_label, "muted", big=True)
        header.addWidget(pnl_label)

        lay.addLayout(header)

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels([
            "✓", "نماد", "لگ", "تعداد", "ورود", "وضعیت"])
        h = table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        table.setColumnWidth(0, 36)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 160)
        table.setColumnWidth(3, 60)
        table.setColumnWidth(4, 90)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(26)
        table.verticalHeader().setVisible(False)

        for pos in positions:
            row = table.rowCount()
            table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, pos.position_id)
            table.setItem(row, 0, chk)

            table.setItem(row, 1, QTableWidgetItem(
                pos.underlying_symbol or "—"))

            leg_text = "—"
            if pos.legs:
                leg = pos.legs[0]
                leg_text = f"{leg.leg_type.label_fa} {leg.symbol}"
            table.setItem(row, 2, QTableWidgetItem(leg_text))

            qty = pos.legs[0].quantity if pos.legs else 0
            table.setItem(row, 3, QTableWidgetItem(fmt_int(qty)))

            entry = pos.legs[0].entry_price if pos.legs else 0
            table.setItem(row, 4, QTableWidgetItem(fmt_money(entry)))

            status_item = QTableWidgetItem(pos.status.label_fa)
            status_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 5, status_item)

        h_table = min(180, 26 * len(positions) + 30)
        table.setFixedHeight(h_table)
        lay.addWidget(table)

        return card

    def _update_group_buttons(self):
        n_pos = len(self._group_positions)
        n_ungrouped = sum(
            1 for p in self._group_positions if not p.group_id)

        self.btn_group_new.setEnabled(n_ungrouped > 0)

        all_grouped = (n_pos > 0 and n_ungrouped == 0)
        self.btn_commit.setEnabled(all_grouped)

        if n_pos == 0:
            self.btn_commit.setText("✅ ارسال (بدون موقعیت)")
        elif not all_grouped:
            self.btn_commit.setText(
                f"✅ ارسال ({n_ungrouped} بدون گروه)")
        else:
            self.btn_commit.setText("✅ ارسال به برنامه و ذخیره")

    # ═══════════════════════════════════════════════
    # تب ۳: تعریف استراتژی
    # ═══════════════════════════════════════════════

    def _create_new_strategy(self):
        """تعریف استراتژی جدید"""
        selected = self._get_ticked_group_positions()
        if not selected:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند موقعیت بدون گروه را تیک بزنید.")
            return

        pseudo_trades = [self._position_to_pseudo_trade(p)
                         for p in selected]

        try:
            dlg = StrategyDialog(self, trades=pseudo_trades)
        except Exception as e:
            logger.exception(f"StrategyDialog failed: {e}")
            QMessageBox.critical(self, "خطا",
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

            group = StrategyGroup(
                strategy_type=strategy_type,
                display_name=display_name,
                position_ids=[p.position_id for p in selected],
                created_at=today_jalali(),
                alert_target_roi=self._settings.default_alert_roi,
            )
            self._groups.append(group)

            for p in selected:
                p.group_id = group.group_id
                p.strategy_type = strategy_type
                p.strategy_name = display_name
                if self._settings.default_alert_roi > 0:
                    p.alert_target_roi = self._settings.default_alert_roi

            self._refresh_group()

            QMessageBox.information(
                self, "✅ موفق",
                f"استراتژی «{display_name}» برای "
                f"{len(selected)} موقعیت تشکیل شد.")
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
            p.side = LegType.BUY
            p.quantity = 0
            p.price = 0
            p.option_kind = OptionType.STOCK
            p.strike_price = 0
            p.expiry_date = pos.expiry_date
            p.is_option = False
            p.is_call = False
            p.is_put = False
            p.is_stock = True
            p.effective_contract_size = 1
            p.close_reason = pos.close_reason

        return p

    def _get_ticked_group_positions(self) -> List[StrategyPosition]:
        """پیدا کردن موقعیت‌های تیک‌خورده در تب ۳"""
        ticked_ids = set()
        for table in self.groups_container.findChildren(QTableWidget):
            for row in range(table.rowCount()):
                chk = table.item(row, 0)
                if chk and chk.checkState() == Qt.Checked:
                    pid = chk.data(Qt.UserRole)
                    if pid:
                        ticked_ids.add(pid)

        return [p for p in self._group_positions
                if p.position_id in ticked_ids and not p.group_id]

    # ═══════════════════════════════════════════════
    # تب ۳: عملیات
    # ═══════════════════════════════════════════════

    def _get_ticked_group_ids(self) -> List[str]:
        """پیدا کردن group_id های تیک‌خورده در تب ۳"""
        ticked_group_ids = set()
        for table in self.groups_container.findChildren(QTableWidget):
            for row in range(table.rowCount()):
                chk = table.item(row, 0)
                if chk and chk.checkState() == Qt.Checked:
                    pid = chk.data(Qt.UserRole)
                    if pid:
                        for g in self._groups:
                            if pid in g.position_ids:
                                ticked_group_ids.add(g.group_id)
                                break
        return list(ticked_group_ids)

    def _get_ticked_group_positions_all(self) -> List[StrategyPosition]:
        """پیدا کردن همه‌ی position های تیک‌خورده (گروه‌بندی‌شده یا بدون گروه)"""
        ticked_ids = set()
        for table in self.groups_container.findChildren(QTableWidget):
            for row in range(table.rowCount()):
                chk = table.item(row, 0)
                if chk and chk.checkState() == Qt.Checked:
                    pid = chk.data(Qt.UserRole)
                    if pid:
                        ticked_ids.add(pid)

        return [p for p in self._group_positions
                if p.position_id in ticked_ids]

    def _ungroup_selected(self):
        """جدا کردن position های تیک‌خورده از گروه‌ها"""
        ticked_ids = set()
        for table in self.groups_container.findChildren(QTableWidget):
            for row in range(table.rowCount()):
                chk = table.item(row, 0)
                if chk and chk.checkState() == Qt.Checked:
                    pid = chk.data(Qt.UserRole)
                    if pid:
                        ticked_ids.add(pid)

        if not ticked_ids:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند موقعیت را تیک بزنید.")
            return

        # جدا کردن
        affected_groups = set()
        for pos in self._group_positions:
            if pos.position_id in ticked_ids and pos.group_id:
                affected_groups.add(pos.group_id)
                pos.group_id = ""
                pos.strategy_type = ""

        # حذف گروه‌های خالی
        self._groups = [
            g for g in self._groups if g.position_ids
        ]
        # به‌روزرسانی position_ids در گروه‌ها
        for g in self._groups:
            g.position_ids = [
                pid for pid in g.position_ids
                if pid not in ticked_ids
            ]

        # حذف گروه‌های خالی بعد از به‌روزرسانی
        self._groups = [
            g for g in self._groups if g.position_ids
        ]

        self._refresh_group()
        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ticked_ids)} موقعیت از گروه جدا شد.")

    def _delete_group(self):
        """حذف گروه‌های انتخاب‌شده (position ها حفظ می‌شوند)"""
        ticked_group_ids = self._get_ticked_group_ids()

        if not ticked_group_ids:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند گروه را تیک بزنید.")
            return

        reply = QMessageBox.question(
            self, "تأیید حذف گروه",
            f"آیا از حذف {len(ticked_group_ids)} گروه مطمئن "
            f"هستید؟\n\n"
            f"⚠️ موقعیت‌ها حذف نمی‌شوند، فقط به «بدون استراتژی» "
            f"برمی‌گردند.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # حذف گروه‌ها
        for gid in ticked_group_ids:
            # پاک کردن group_id از position ها
            for pos in self._group_positions:
                if pos.group_id == gid:
                    pos.group_id = ""
                    pos.strategy_type = ""

        # حذف گروه‌ها از لیست
        self._groups = [
            g for g in self._groups
            if g.group_id not in ticked_group_ids
        ]

        self._refresh_group()
        QMessageBox.information(
            self, "✅ موفق",
            f"{len(ticked_group_ids)} گروه حذف شد.")

    def _split_selected_position(self):
        """شکستن موقعیت انتخاب‌شده به قطعات"""
        selected = self._get_ticked_group_positions_all()

        if len(selected) != 1:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً فقط یک موقعیت را برای شکستن انتخاب کنید.")
            return

        pos = selected[0]

        # بررسی: تک‌لگی
        if len(pos.legs) != 1:
            QMessageBox.warning(
                self, "خطا",
                "فقط موقعیت‌های تک‌لگی قابل شکستن هستند.")
            return

        # بررسی: qty > 1
        if pos.legs[0].quantity <= 1:
            QMessageBox.warning(
                self, "خطا",
                "موقعیت باید حداقل 2 عدد داشته باشد.")
            return

        # باز کردن دیالوگ
        from position_saver.ui.split_position_dialog import (
            SplitPositionDialog)
        dlg = SplitPositionDialog(self, position=pos)
        try:
            if not dlg.exec():
                return

            quantities = dlg.get_quantities()
            reasons = dlg.get_reasons()

            # انجام split
            try:
                pieces = pos.split_position(quantities)
            except ValueError as e:
                QMessageBox.critical(self, "خطا", str(e))
                return

            # اضافه کردن strategy_type به هر قطعه
            for piece, reason in zip(pieces, reasons):
                if reason:
                    piece.strategy_type = reason

            # حذف position اصلی
            if pos in self._group_positions:
                self._group_positions.remove(pos)

            # اگر در گروه بود، از گروه حذف کن
            for g in self._groups:
                if pos.position_id in g.position_ids:
                    g.position_ids.remove(pos.position_id)
                    break

            # حذف گروه‌های خالی
            self._groups = [
                g for g in self._groups if g.position_ids
            ]

            # اضافه کردن قطعات
            for p in pieces:
                self._group_positions.append(p)

            self._refresh_group()
            QMessageBox.information(
                self, "✅ موفق",
                f"موقعیت به {len(pieces)} قطعه شکسته شد.")
        finally:
            dlg.deleteLater()

    def _merge_selected_positions(self):
        """ادغام موقعیت‌های انتخاب‌شده"""
        selected = self._get_ticked_group_positions_all()

        if len(selected) < 2:
            QMessageBox.information(
                self, "اطلاع",
                "حداقل دو موقعیت برای ادغام لازم است.")
            return

        reply = QMessageBox.question(
            self, "تأیید ادغام",
            f"آیا از ادغام {len(selected)} موقعیت مطمئن هستید؟\n\n"
            f"⚠️ همه باید همان نماد، strike، expiry، "
            f"entry_price و جهت باشند.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # انجام merge
        try:
            merged = StrategyPosition.merge_positions(selected)
        except ValueError as e:
            QMessageBox.critical(self, "خطا", str(e))
            return

        # حذف position های قدیمی
        for p in selected:
            if p in self._group_positions:
                self._group_positions.remove(p)
            # از گروه‌ها هم حذف کن
            for g in self._groups:
                if p.position_id in g.position_ids:
                    g.position_ids.remove(p.position_id)

        # حذف گروه‌های خالی
        self._groups = [
            g for g in self._groups if g.position_ids
        ]

        # اضافه کردن merged
        self._group_positions.append(merged)

        self._refresh_group()
        QMessageBox.information(
            self, "✅ موفق",
            f"{len(selected)} موقعیت ادغام شد.")


    def _get_ticked_group_cards(self) -> List[StrategyGroup]:
        """پیدا کردن گروه‌های تیک‌خورده از میان کارت‌ها"""
        ticked_group_ids = set()
        for table in self.groups_container.findChildren(QTableWidget):
            for row in range(table.rowCount()):
                chk = table.item(row, 0)
                if chk and chk.checkState() == Qt.Checked:
                    # پیدا کردن group از روی position_id
                    pid = chk.data(Qt.UserRole)
                    if pid:
                        for g in self._groups:
                            if pid in g.position_ids:
                                ticked_group_ids.add(g.group_id)
                                break
        return [g for g in self._groups
                if g.group_id in ticked_group_ids]

    # ═══════════════════════════════════════════════
    # تب ۳: بازگشت
    # ═══════════════════════════════════════════════

    def _move_group_back_to_confirm(self):
        QMessageBox.information(
            self, "اطلاع",
            "برای بازگشت، باید همه‌ی گروه‌ها را حذف کنید.")

    # ═══════════════════════════════════════════════
    # Net Position Dialog
    # ═══════════════════════════════════════════════

    def _open_net_position_dialog(self, from_tab: str = "raw"):
        """باز کردن دیالوگ تحلیل ترتیب زمانی"""
        if not self._all_trades:
            QMessageBox.information(
                self, "اطلاع",
                "هیچ معامله‌ای بارگذاری نشده است.")
            return

        symbol = None

        if from_tab == "raw":
            ticked = self._get_ticked_raw_trades()
        elif from_tab == "confirm":
            ticked = self._get_ticked_confirm_trades()
        else:
            ticked = []

        if ticked:
            symbols = list({t.symbol for t in ticked})
            if len(symbols) > 1:
                QMessageBox.warning(
                    self, "خطا",
                    f"شما {len(symbols)} نماد مختلف انتخاب کرده‌اید.\n"
                    f"لطفاً فقط یک نماد انتخاب کنید.")
                return
            symbol = symbols[0]
        else:
            if from_tab == "raw" and self._raw_trades:
                symbol = self._raw_trades[0].symbol
            elif from_tab == "confirm" and self._confirm_trades:
                symbol = self._confirm_trades[0].symbol

        if not symbol:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک ردیف را تیک بزنید.")
            return

        symbol_trades = [
            t for t in self._all_trades if t.symbol == symbol
        ]

        if not symbol_trades:
            return

        dlg = NetPositionDialog(
            self, trades=symbol_trades, symbol=symbol)
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    # ═══════════════════════════════════════════════
    # Bulk Fill
    # ═══════════════════════════════════════════════

    def _open_bulk_fill_dialog(self):
        if not self._raw_trades:
            return

        by_symbol: Dict[str, List[TradeRecord]] = {}
        for t in self._raw_trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        if not by_symbol:
            QMessageBox.information(self, "اطلاع",
                "هیچ ردیفی وجود ندارد.")
            return

        symbols = sorted(by_symbol.keys())
        if len(symbols) == 1:
            chosen = symbols[0]
        else:
            items = [f"{s} ({len(by_symbol[s])} ردیف)"
                     for s in symbols]
            choice, ok = QInputDialog.getItem(
                self, "انتخاب نماد",
                f"کدام نماد را می‌خواهید پر کنید؟ ({len(symbols)} نماد)",
                items, 0, False)
            if not ok:
                return
            chosen = symbols[items.index(choice)]

        symbol_trades = by_symbol[chosen]
        initial_info = get_symbol_info(chosen) or {}

        from position_saver.ui.symbol_fill_dialog import (
            SymbolFillDialog)
        dlg = SymbolFillDialog(
            self, symbol=chosen,
            trades=symbol_trades, initial_info=initial_info)

        try:
            if not dlg.exec():
                return
            result = dlg.get_result()
            if not result:
                return

            save_symbol_info(
                symbol=chosen,
                strike_price=result["strike_price"],
                expiry_date=result["expiry_date"],
                contract_size=result["contract_size"],
                underlying_symbol=result["underlying_symbol"],
            )

            applied = 0
            self._syncing = True
            try:
                for t in symbol_trades:
                    if not t.strike_price:
                        t.strike_price = result["strike_price"]
                    if not t.expiry_date:
                        t.expiry_date = result["expiry_date"]
                    if t.contract_size <= 0:
                        t.contract_size = result["contract_size"]
                    if not t.underlying_symbol:
                        t.underlying_symbol = result["underlying_symbol"]

                    t.user_edited = True
                    t.needs_review = not t.is_complete
                    applied += 1
            finally:
                self._syncing = False

            self._refresh_raw()
            QMessageBox.information(
                self, "✅ موفق",
                f"اطلاعات به {applied} ردیف نماد «{chosen}» "
                f"اعمال شد.")
        finally:
            dlg.deleteLater()

    def _show_symbol_memory(self):
        from position_saver.importer.symbol_memory import (
            get_all, clear_all)
        memory = get_all()

        if not memory:
            QMessageBox.information(
                self, "حافظه‌ی نماد",
                "حافظه خالی است.")
            return

        lines = [f"📋 {len(memory)} نماد ذخیره‌شده:\n"]
        for symbol, info in sorted(memory.items()):
            strike = info.get("strike_price", "—")
            expiry = info.get("expiry_date", "—")
            if isinstance(strike, (int, float)):
                strike = f"{int(strike):,}"
            lines.append(
                f"  • {symbol}  →  strike={strike}  expiry={expiry}")

        text = "\n".join(lines[:50])
        if len(memory) > 50:
            text += f"\n\n... و {len(memory) - 50} نماد دیگر"

        reply = QMessageBox.question(
            self, "حافظه‌ی نماد",
            text + "\n\nآیا می‌خواهید حافظه را پاک کنید؟",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            reply2 = QMessageBox.warning(
                self, "تأیید حذف",
                f"آیا از پاک کردن همه‌ی {len(memory)} نماد "
                f"اطمینان دارید؟",
                QMessageBox.Yes | QMessageBox.No)
            if reply2 == QMessageBox.Yes:
                clear_all()
                self._refresh_raw()
                QMessageBox.information(self, "موفق", "حافظه پاک شد.")

    # ═══════════════════════════════════════════════
    # Commit نهایی
    # ═══════════════════════════════════════════════

    def _commit_import(self):
        if not self._group_positions:
            QMessageBox.warning(self, "اطلاع",
                "هیچ موقعیتی برای ذخیره وجود ندارد.")
            return

        ungrouped = [
            p for p in self._group_positions if not p.group_id
        ]
        if ungrouped:
            QMessageBox.warning(
                self, "خطا",
                f"❌ {len(ungrouped)} موقعیت هنوز گروه‌بندی "
                f"نشده‌اند.\n\n"
                f"برای ذخیره، همه‌ی موقعیت‌ها باید گروه‌بندی "
                f"شوند.")
            return

        reply = QMessageBox.question(
            self, "تأیید ذخیره",
            f"{len(self._group_positions)} موقعیت در "
            f"{len(self._groups)} گروه ذخیره می‌شود.\n\n"
            f"آیا مطمئن هستید؟",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        try:
            existing_positions = self.storage.load_positions()
        except Exception as e:
            logger.exception(f"Load failed: {e}")
            QMessageBox.critical(self, "خطا",
                f"بارگذاری ناموفق:\n{e}")
            return

        all_pos = existing_positions + self._group_positions

        try:
            if not self.storage.save_positions(all_pos):
                QMessageBox.critical(self, "خطا",
                    "ذخیره‌سازی موقعیت‌ها ناموفق بود.")
                return
        except Exception as e:
            logger.exception(f"Save failed: {e}")
            QMessageBox.critical(self, "خطا",
                f"خطا در ذخیره‌سازی:\n{e}")
            return

        try:
            existing_groups = self.storage.load_groups()
            all_groups = existing_groups + self._groups
            if not self.storage.save_groups(all_groups):
                logger.warning("Save groups failed")
        except Exception as e:
            logger.warning(f"Save groups failed: {e}")

        try:
            batch = ImportBatch(
                broker=self._broker,
                source_file=self._file_path,
                n_trades=len(self._all_trades),
                n_positions_open=sum(
                    1 for p in self._group_positions
                    if p.is_open),
                n_positions_closed=sum(
                    1 for p in self._group_positions
                    if p.is_closed),
                n_needs_review=0,
                n_duplicates=0,
                position_ids=[
                    p.position_id for p in self._group_positions],
            )
            self.storage.save_import_batch(batch.to_dict())
        except Exception as e:
            logger.warning(f"Save batch failed: {e}")

        for p in self._group_positions:
            for leg in p.legs:
                if leg.strike_price and leg.expiry_date:
                    try:
                        save_symbol_info(
                            symbol=leg.symbol,
                            strike_price=leg.strike_price,
                            expiry_date=leg.expiry_date,
                            contract_size=leg.contract_size,
                            option_kind=leg.option_kind,
                            underlying_symbol=leg.ins_code_ua,
                            ins_code=leg.ins_code,
                        )
                    except Exception:
                        pass

        QMessageBox.information(
            self, "✅ موفق",
            f"ایمپورت با موفقیت انجام شد.\n\n"
            f"موقعیت‌های ذخیره‌شده: {len(self._group_positions)}\n"
            f"گروه‌ها: {len(self._groups)}\n"
            f"نمادها در حافظه: {get_symbol_memory_count()}")

        self.accept()

    # ═══════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════

    def get_result(self) -> Optional[ImportResult]:
        return self._result


__all__ = ["ImportWizardDialog", "SortableItem"]