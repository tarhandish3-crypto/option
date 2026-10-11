# position_saver/ui/import_wizard_dialog.py
# -*- coding: utf-8 -*-

"""
جادوگر ایمپورت اکسل کارگزاری — چند مرحله‌ای.

مراحل:
    ۱. انتخاب فایل و کارگزاری
    ۲. پیش‌نمایش معاملات خام (با فیلتر)
    ۳. بازبینی با زیرتب‌ها:
        - ⚠️ ناقص (Exception Queue)
        - ✅ کامل
        - 📜 بسته‌شده
    ۴. تأیید و ثبت
"""

import logging
import os
from typing import List, Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QMessageBox,
    QHeaderView, QGroupBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QDialogButtonBox, QCheckBox, QSpinBox,
    QFileDialog, QStackedWidget, QWidget, QTabWidget,
    QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QBrush, QFont

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,
)
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.storage import (
    PositionStorage, normalize_symbol,
    infer_underlying_symbol, today_jalali,
)
from position_saver.main import get_market_snapshot
from position_saver.theme import (
    Theme, CURRENCY,
    fmt_money, fmt_pct, fmt_int,
    set_kind, set_tone,
)
from position_saver.importer import (
    ImportEngine, ImportSettings, ImportResult, ImportBatch,
    TradeRecord, MatchedLot,
    get_template_for_broker, list_broker_names,
)
from position_saver.ui.dialogs import BROKER_NAMES


logger = logging.getLogger("PositionSaver.UI.ImportWizard")


# =====================================================
# ثابت‌ها
# =====================================================

STEP_FILE = 0
STEP_PREVIEW = 1
STEP_REVIEW = 2
STEP_CONFIRM = 3

TAB_INCOMPLETE = 0
TAB_COMPLETE = 1
TAB_CLOSED = 2


# =====================================================
# ImportWizardDialog
# =====================================================

class ImportWizardDialog(QDialog):
    """
    جادوگر ایمپورت اکسل.

    استفاده:
        dlg = ImportWizardDialog(parent=self, storage=self.storage)
        if dlg.exec():
            result = dlg.get_result()
    """

    def __init__(self, parent=None, storage: Optional[PositionStorage] = None):
        super().__init__(parent)
        self.setWindowTitle("📥 ایمپورت اکسل کارگزاری")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(1200, 720)

        self.storage = storage or PositionStorage()
        self.engine = ImportEngine(storage=self.storage)

        # state
        self._file_path: str = ""
        self._broker: str = BROKER_NAMES[0] if BROKER_NAMES else "مفید"
        self._settings = ImportSettings()
        self._import_result: Optional[ImportResult] = None

        # ویجت‌های inline editing در تب «ناقص»
        self._incomplete_rows: Dict[int, TradeRecord] = {}
        self._incomplete_widgets: Dict[int, dict] = {}

        self._build_ui()
        self._update_navigation()

    # =====================================================
    # ساخت UI
    # =====================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ─── هدر (نوار بالا: کارگزاری + فایل) ───
        root.addWidget(self._build_header())

        # ─── نوار مراحل ───
        root.addWidget(self._build_step_indicator())

        # ─── بدنه (QStackedWidget) ───
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step_file())
        self.stack.addWidget(self._build_step_preview())
        self.stack.addWidget(self._build_step_review())
        self.stack.addWidget(self._build_step_confirm())
        root.addWidget(self.stack, 1)

        # ─── نوار پایین ───
        root.addLayout(self._build_navigation())

    # -----------------------------------------------------
    # هدر — کارگزاری و فایل
    # -----------------------------------------------------

    def _build_header(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("🏦 کارگزاری:"))

        self.cmb_broker = QComboBox()
        self.cmb_broker.addItems(BROKER_NAMES)
        self.cmb_broker.setCurrentText(self._broker)
        self.cmb_broker.setMinimumWidth(180)
        self.cmb_broker.currentTextChanged.connect(self._on_broker_changed)
        layout.addWidget(self.cmb_broker)

        layout.addSpacing(20)
        layout.addWidget(QLabel("📄 فایل:"))
        self.lbl_file = QLabel("— هیچ فایلی انتخاب نشده —")
        set_tone(self.lbl_file, "muted")
        self.lbl_file.setMinimumWidth(400)
        layout.addWidget(self.lbl_file, 1)

        return widget

    def _on_broker_changed(self, broker: str):
        self._broker = broker

    # -----------------------------------------------------
    # نوار مراحل
    # -----------------------------------------------------

    def _build_step_indicator(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)

        self.lbl_step = QLabel("مرحله ۱: انتخاب فایل")
        set_tone(self.lbl_step, "primary", big=True)
        layout.addWidget(self.lbl_step)
        layout.addStretch()

        return widget

    def _update_step_label(self):
        texts = {
            STEP_FILE: "مرحله ۱: انتخاب فایل و تنظیمات",
            STEP_PREVIEW: "مرحله ۲: پیش‌نمایش معاملات خام",
            STEP_REVIEW: "مرحله ۳: بازبینی و گروه‌بندی",
            STEP_CONFIRM: "مرحله ۴: تأیید و ثبت نهایی",
        }
        self.lbl_step.setText(texts.get(self.stack.currentIndex(), ""))

    # -----------------------------------------------------
    # مرحله ۱ — فایل و تنظیمات
    # -----------------------------------------------------

    def _build_step_file(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ─── انتخاب فایل ───
        file_group = QGroupBox("۱. انتخاب فایل اکسل")
        file_layout = QHBoxLayout(file_group)
        self.txt_file = QLineEdit()
        self.txt_file.setPlaceholderText("مسیر فایل اکسل کارگزاری...")
        self.txt_file.setReadOnly(True)
        file_layout.addWidget(self.txt_file, 1)

        btn_pick = QPushButton("📂 انتخاب فایل...")
        btn_pick.clicked.connect(self._pick_file)
        set_kind(btn_pick, "primary")
        file_layout.addWidget(btn_pick)

        layout.addWidget(file_group)

        # ─── تنظیمات ───
        settings_group = QGroupBox("۲. تنظیمات ایمپورت")
        form = QFormLayout(settings_group)

        self.cmb_match_method = QComboBox()
        self.cmb_match_method.addItem("FIFO (اول-ورود، اول-خروج)", "fifo")
        self.cmb_match_method.addItem("LIFO (آخر-ورود، اول-خروج)", "lifo")
        form.addRow("روش تطبیق:", self.cmb_match_method)

        self.spin_time_window = QSpinBox()
        self.spin_time_window.setRange(5, 3600)
        self.spin_time_window.setValue(60)
        self.spin_time_window.setSuffix(" ثانیه")
        form.addRow("پنجره‌ی زمانی گروه‌بندی:", self.spin_time_window)

        self.chk_skip_duplicates = QCheckBox(
            "رد کردن معاملات تکراری در ایمپورت‌های قبلی")
        self.chk_skip_duplicates.setChecked(True)
        form.addRow("", self.chk_skip_duplicates)

        layout.addWidget(settings_group)
        layout.addStretch()
        return widget

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل اکسل",
            "", "Excel Files (*.xlsx *.xls)")
        if not path:
            return
        self._file_path = path
        self.txt_file.setText(path)
        self.lbl_file.setText(os.path.basename(path))
        set_tone(self.lbl_file, "neutral")

    # -----------------------------------------------------
    # مرحله ۲ — پیش‌نمایش معاملات خام
    # -----------------------------------------------------

    def _build_step_preview(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ─── نوار ابزار ───
        toolbar = QHBoxLayout()

        btn_select_all = QPushButton("✓ انتخاب همه")
        btn_select_all.clicked.connect(
            lambda: self._set_all_selected(True))
        toolbar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("✗ لغو انتخاب همه")
        btn_deselect_all.clicked.connect(
            lambda: self._set_all_selected(False))
        toolbar.addWidget(btn_deselect_all)

        toolbar.addStretch()

        self.lbl_preview_stats = QLabel("—")
        set_tone(self.lbl_preview_stats, "muted")
        toolbar.addWidget(self.lbl_preview_stats)

        layout.addLayout(toolbar)

        # ─── جدول ───
        self.table_preview = QTableWidget(0, 9)
        self.table_preview.setHorizontalHeaderLabels([
            "✓", "تاریخ", "ساعت", "سمت",
            "نماد", "تعداد", "قیمت", "وضعیت", "⚠️",
        ])
        self.table_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_preview.horizontalHeader().setStretchLastSection(True)
        self.table_preview.setColumnWidth(0, 40)
        self.table_preview.setColumnWidth(1, 100)
        self.table_preview.setColumnWidth(2, 90)
        self.table_preview.setColumnWidth(3, 70)
        self.table_preview.setColumnWidth(4, 140)
        self.table_preview.setColumnWidth(5, 70)
        self.table_preview.setColumnWidth(6, 100)
        self.table_preview.setColumnWidth(7, 100)
        self.table_preview.setSelectionBehavior(
            QTableWidget.SelectRows)
        self.table_preview.setEditTriggers(
            QTableWidget.NoEditTriggers)
        self.table_preview.setAlternatingRowColors(True)
        self.table_preview.verticalHeader().setDefaultSectionSize(28)

        layout.addWidget(self.table_preview, 1)
        return widget

    def _set_all_selected(self, selected: bool):
        if not self._import_result:
            return
        for t in self._import_result.trades:
            t.is_selected = selected
        self._refresh_preview_table()

    def _refresh_preview_table(self):
        trades = self._import_result.trades if self._import_result else []
        self.table_preview.setRowCount(0)

        for idx, t in enumerate(trades):
            row = self.table_preview.rowCount()
            self.table_preview.insertRow(row)

            # ─── ستون ۰: چک‌باکس ───
            chk_item = QTableWidgetItem()
            chk_item.setFlags(
                Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(
                Qt.Checked if t.is_selected else Qt.Unchecked)
            self.table_preview.setItem(row, 0, chk_item)

            # ستون ۱: تاریخ
            self.table_preview.setItem(row, 1, QTableWidgetItem(
                t.raw_date or "—"))
            # ستون ۲: ساعت
            self.table_preview.setItem(row, 2, QTableWidgetItem(
                t.raw_time or "—"))
            # ستون ۳: سمت
            side_item = QTableWidgetItem(t.side.label_fa)
            side_item.setForeground(
                QColor(Theme.PROFIT if t.is_buy else Theme.LOSS))
            self.table_preview.setItem(row, 3, side_item)
            # ستون ۴: نماد
            self.table_preview.setItem(row, 4, QTableWidgetItem(
                t.symbol))
            # ستون ۵: تعداد
            self.table_preview.setItem(row, 5, QTableWidgetItem(
                fmt_int(t.quantity)))
            # ستون ۶: قیمت
            self.table_preview.setItem(row, 6, QTableWidgetItem(
                fmt_money(t.price)))
            # ستون ۷: وضعیت
            self.table_preview.setItem(row, 7, QTableWidgetItem(
                t.raw_status or "—"))
            # ستون ۸: هشدار
            if t.warnings:
                warn_item = QTableWidgetItem("⚠️")
                warn_item.setToolTip("\n".join(t.warnings))
                warn_item.setForeground(QColor(Theme.WARN))
                self.table_preview.setItem(row, 8, warn_item)

        # آمار
        selected = sum(1 for t in trades if t.is_selected)
        total = len(trades)
        self.lbl_preview_stats.setText(
            f"نمایش {total} ردیف — انتخاب‌شده: {selected}")

    # -----------------------------------------------------
    # مرحله ۳ — بازبینی (تب‌ها)
    # -----------------------------------------------------

    def _build_step_review(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.tabs_review = QTabWidget()
        self.tabs_review.addTab(
            self._build_tab_incomplete(), "⚠️ ناقص")
        self.tabs_review.addTab(
            self._build_tab_complete(), "✅ کامل")
        self.tabs_review.addTab(
            self._build_tab_closed(), "📜 بسته‌شده")
        self.tabs_review.currentChanged.connect(
            self._on_review_tab_changed)

        layout.addWidget(self.tabs_review)
        return widget

    # --- زیرتب ناقص ---

    def _build_tab_incomplete(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # هدر
        header = QHBoxLayout()
        self.lbl_incomplete_info = QLabel("—")
        set_tone(self.lbl_incomplete_info, "warn", big=True)
        header.addWidget(self.lbl_incomplete_info)
        header.addStretch()
        layout.addLayout(header)

        hint = QLabel(
            "💡 لطفاً برای هر ردیف، قیمت اعمال و تاریخ سررسید را وارد کنید. "
            "به محض پر شدن همه‌ی فیلدها، دکمه ✓ فعال می‌شود."
        )
        set_tone(hint, "muted")
        layout.addWidget(hint)

        # جدول با ویرایش inline
        self.table_incomplete = QTableWidget(0, 7)
        self.table_incomplete.setHorizontalHeaderLabels([
            "نماد", "سمت", "تعداد", "قیمت",
            "قیمت اعمال", "تاریخ سررسید", "✓",
        ])
        self.table_incomplete.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_incomplete.horizontalHeader().setStretchLastSection(False)
        self.table_incomplete.setColumnWidth(0, 140)
        self.table_incomplete.setColumnWidth(1, 70)
        self.table_incomplete.setColumnWidth(2, 70)
        self.table_incomplete.setColumnWidth(3, 110)
        self.table_incomplete.setColumnWidth(4, 140)
        self.table_incomplete.setColumnWidth(5, 140)
        self.table_incomplete.setColumnWidth(6, 60)
        self.table_incomplete.verticalHeader().setDefaultSectionSize(34)
        self.table_incomplete.setAlternatingRowColors(True)
        self.table_incomplete.setSelectionBehavior(
            QTableWidget.SelectRows)
        layout.addWidget(self.table_incomplete, 1)

        return widget

    def _refresh_incomplete_table(self):
        self.table_incomplete.setRowCount(0)
        self._incomplete_rows.clear()
        self._incomplete_widgets.clear()

        if not self._import_result:
            return

        incomplete = self._import_result.incomplete_trades

        if not incomplete:
            self.lbl_incomplete_info.setText(
                "✅ همه‌ی ردیف‌ها تکمیل شدند")
            set_tone(self.lbl_incomplete_info, "profit")
            return

        self.lbl_incomplete_info.setText(
            f"⚠️ {len(incomplete)} ردیف نیازمند تکمیل دستی")
        set_tone(self.lbl_incomplete_info, "warn")

        for idx, trade in enumerate(incomplete):
            row = self.table_incomplete.rowCount()
            self.table_incomplete.insertRow(row)
            self._incomplete_rows[row] = trade
            self._build_incomplete_row(row, trade)

    def _build_incomplete_row(self, row: int, trade: TradeRecord):
        """ساخت یک ردیف ناقص با ویجت‌های inline"""
        from PySide6.QtWidgets import QSpinBox, QLineEdit, QAbstractSpinBox

        # ─── ستون ۰: نماد (خواندنی) ───
        sym_item = QTableWidgetItem(trade.symbol)
        sym_item.setFlags(Qt.ItemIsEnabled)
        self.table_incomplete.setItem(row, 0, sym_item)

        # ─── ستون ۱: سمت ───
        side_item = QTableWidgetItem(trade.side.label_fa)
        side_item.setTextAlignment(Qt.AlignCenter)
        side_item.setFlags(Qt.ItemIsEnabled)
        side_item.setForeground(
            QColor(Theme.PROFIT if trade.is_buy else Theme.LOSS))
        self.table_incomplete.setItem(row, 1, side_item)

        # ─── ستون ۲: تعداد (خواندنی) ───
        qty_item = QTableWidgetItem(fmt_int(trade.quantity))
        qty_item.setTextAlignment(Qt.AlignCenter)
        qty_item.setFlags(Qt.ItemIsEnabled)
        self.table_incomplete.setItem(row, 2, qty_item)

        # ─── ستون ۳: قیمت (خواندنی) ───
        price_item = QTableWidgetItem(fmt_money(trade.price))
        price_item.setTextAlignment(Qt.AlignCenter)
        price_item.setFlags(Qt.ItemIsEnabled)
        self.table_incomplete.setItem(row, 3, price_item)

        # ─── ستون ۴: قیمت اعمال (editable) ───
        spin_strike = QSpinBox()
        spin_strike.setRange(0, 1_000_000_000)
        spin_strike.setSingleStep(50)
        spin_strike.setGroupSeparatorShown(True)
        spin_strike.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_strike.setValue(int(trade.strike_price or 0))
        spin_strike.valueChanged.connect(
            lambda _, r=row: self._on_strike_changed(r))
        self.table_incomplete.setCellWidget(row, 4, spin_strike)

        # ─── ستون ۵: تاریخ سررسید (editable) ───
        line_expiry = QLineEdit(trade.expiry_date or "")
        line_expiry.setPlaceholderText("1405/07/26")
        line_expiry.textChanged.connect(
            lambda _, r=row: self._on_expiry_changed(r))
        self.table_incomplete.setCellWidget(row, 5, line_expiry)

        # ─── ستون ۶: دکمه تأیید ───
        btn_confirm = QPushButton("✓")
        btn_confirm.setFixedWidth(45)
        btn_confirm.setEnabled(trade.is_complete)
        if trade.is_complete:
            set_kind(btn_confirm, "primary")
        btn_confirm.clicked.connect(
            lambda _, r=row: self._on_confirm_row(r))
        self.table_incomplete.setCellWidget(row, 6, btn_confirm)

        # ذخیره‌ی ویجت‌ها
        self._incomplete_widgets[row] = {
            "strike": spin_strike,
            "expiry": line_expiry,
            "confirm": btn_confirm,
        }

    def _on_strike_changed(self, row: int):
        widgets = self._incomplete_widgets.get(row)
        trade = self._incomplete_rows.get(row)
        if not widgets or not trade:
            return
        trade.strike_price = float(widgets["strike"].value())
        trade.user_edited = True
        self._update_confirm_button_state(row)

    def _on_expiry_changed(self, row: int):
        widgets = self._incomplete_widgets.get(row)
        trade = self._incomplete_rows.get(row)
        if not widgets or not trade:
            return
        trade.expiry_date = widgets["expiry"].text().strip()
        trade.user_edited = True
        self._update_confirm_button_state(row)

    def _update_confirm_button_state(self, row: int):
        widgets = self._incomplete_widgets.get(row)
        trade = self._incomplete_rows.get(row)
        if not widgets or not trade:
            return

        # بررسی کامل بودن
        if trade.is_complete:
            widgets["confirm"].setEnabled(True)
            set_kind(widgets["confirm"], "primary")
        else:
            widgets["confirm"].setEnabled(False)
            set_kind(widgets["confirm"], "")

    def _on_confirm_row(self, row: int):
        """تأیید یک ردیف ناقص — انتقال به تب کامل"""
        trade = self._incomplete_rows.get(row)
        if not trade or not trade.is_complete:
            return

        trade.needs_review = False
        trade.warnings = []

        # انتقال به لیست کامل
        if trade in self._import_result.incomplete_trades:
            self._import_result.incomplete_trades.remove(trade)
        if trade not in self._import_result.complete_trades:
            self._import_result.complete_trades.append(trade)

        # refresh
        self._refresh_incomplete_table()
        self._refresh_complete_table()
        self._update_tab_badges()
        self._update_navigation()

    # --- زیرتب کامل ---

    def _build_tab_complete(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QHBoxLayout()
        self.lbl_complete_info = QLabel("—")
        set_tone(self.lbl_complete_info, "profit", big=True)
        header.addWidget(self.lbl_complete_info)
        header.addStretch()
        layout.addLayout(header)

        hint = QLabel(
            "💡 برای گروه‌بندی، چند ردیف را انتخاب کنید و روی "
            "«➕ استراتژی جدید» کلیک کنید."
        )
        set_tone(hint, "muted")
        layout.addWidget(hint)

        # نوار ابزار گروه‌بندی
        group_bar = QHBoxLayout()
        btn_new_strategy = QPushButton("➕ استراتژی جدید از انتخاب")
        btn_new_strategy.clicked.connect(self._create_strategy_from_selection)
        set_kind(btn_new_strategy, "primary")
        group_bar.addWidget(btn_new_strategy)
        group_bar.addStretch()
        layout.addLayout(group_bar)

        # جدول
        self.table_complete = QTableWidget(0, 8)
        self.table_complete.setHorizontalHeaderLabels([
            "نماد", "نوع", "سمت", "تعداد", "قیمت",
            "قیمت اعمال", "سررسید", "گروه",
        ])
        self.table_complete.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_complete.horizontalHeader().setStretchLastSection(True)
        self.table_complete.setColumnWidth(0, 140)
        self.table_complete.setColumnWidth(1, 70)
        self.table_complete.setColumnWidth(2, 70)
        self.table_complete.setColumnWidth(3, 70)
        self.table_complete.setColumnWidth(4, 110)
        self.table_complete.setColumnWidth(5, 120)
        self.table_complete.setColumnWidth(6, 100)
        self.table_complete.setSelectionBehavior(
            QTableWidget.SelectRows)
        self.table_complete.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        self.table_complete.setEditTriggers(
            QTableWidget.NoEditTriggers)
        self.table_complete.setAlternatingRowColors(True)
        self.table_complete.verticalHeader().setDefaultSectionSize(28)

        layout.addWidget(self.table_complete, 1)
        return widget

    def _refresh_complete_table(self):
        self.table_complete.setRowCount(0)
        if not self._import_result:
            return

        complete = self._import_result.complete_trades
        if not complete:
            self.lbl_complete_info.setText("هیچ ردیف کاملی وجود ندارد")
            set_tone(self.lbl_complete_info, "muted")
            return

        self.lbl_complete_info.setText(
            f"✅ {len(complete)} ردیف آماده برای گروه‌بندی")

        for trade in complete:
            row = self.table_complete.rowCount()
            self.table_complete.insertRow(row)

            self.table_complete.setItem(row, 0, QTableWidgetItem(
                trade.symbol))
            kind_text = "—"
            if trade.option_kind:
                kind_text = trade.option_kind.name
            self.table_complete.setItem(row, 1, QTableWidgetItem(
                kind_text))
            side_item = QTableWidgetItem(trade.side.label_fa)
            side_item.setForeground(
                QColor(Theme.PROFIT if trade.is_buy else Theme.LOSS))
            self.table_complete.setItem(row, 2, side_item)
            self.table_complete.setItem(row, 3, QTableWidgetItem(
                fmt_int(trade.quantity)))
            self.table_complete.setItem(row, 4, QTableWidgetItem(
                fmt_money(trade.price)))
            self.table_complete.setItem(row, 5, QTableWidgetItem(
                fmt_money(trade.strike_price or 0)))
            self.table_complete.setItem(row, 6, QTableWidgetItem(
                trade.expiry_date or "—"))
            # گروه — فعلاً خالی
            self.table_complete.setItem(row, 7, QTableWidgetItem(""))

        self._update_tab_badges()

    # --- زیرتب بسته ---

    def _build_tab_closed(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.lbl_closed_info = QLabel("—")
        set_tone(self.lbl_closed_info, "muted", big=True)
        layout.addWidget(self.lbl_closed_info)

        hint = QLabel(
            "💡 این معاملات در همان بازه‌ی ایمپورت باز و بسته شده‌اند "
            "(آفست). به تب «تاریخچه» منتقل می‌شوند."
        )
        set_tone(hint, "muted")
        layout.addWidget(hint)

        self.table_closed = QTableWidget(0, 7)
        self.table_closed.setHorizontalHeaderLabels([
            "#", "نماد", "نوع", "ورود", "خروج",
            "تعداد", "سود/زیان",
        ])
        self.table_closed.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table_closed.horizontalHeader().setStretchLastSection(True)
        self.table_closed.setColumnWidth(0, 40)
        self.table_closed.setColumnWidth(1, 140)
        self.table_closed.setColumnWidth(2, 100)
        self.table_closed.setColumnWidth(3, 110)
        self.table_closed.setColumnWidth(4, 110)
        self.table_closed.setColumnWidth(5, 70)
        self.table_closed.setAlternatingRowColors(True)
        self.table_closed.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_closed.verticalHeader().setDefaultSectionSize(28)

        layout.addWidget(self.table_closed, 1)
        return widget

    def _refresh_closed_table(self):
        self.table_closed.setRowCount(0)
        if not self._import_result:
            return

        closed = self._import_result.closed_lots
        self.lbl_closed_info.setText(
            f"📜 {len(closed)} معامله‌ی آفست‌شده")

        for idx, lot in enumerate(closed, 1):
            row = self.table_closed.rowCount()
            self.table_closed.insertRow(row)

            self.table_closed.setItem(row, 0, QTableWidgetItem(
                str(idx)))
            self.table_closed.setItem(row, 1, QTableWidgetItem(
                lot.symbol))
            kind_text = "—"
            if lot.option_kind:
                kind_text = lot.option_kind.name
            self.table_closed.setItem(row, 2, QTableWidgetItem(
                kind_text))
            self.table_closed.setItem(row, 3, QTableWidgetItem(
                fmt_money(lot.entry_price)))
            self.table_closed.setItem(row, 4, QTableWidgetItem(
                fmt_money(lot.close_price or 0)))
            self.table_closed.setItem(row, 5, QTableWidgetItem(
                fmt_int(lot.quantity)))

            pnl = lot.gross_pnl() or 0.0
            pnl_item = QTableWidgetItem(fmt_money(pnl))
            pnl_item.setForeground(
                QColor(Theme.PROFIT if pnl > 0
                       else (Theme.LOSS if pnl < 0 else Theme.MUTED)))
            self.table_closed.setItem(row, 6, pnl_item)

    def _on_review_tab_changed(self, index: int):
        pass

    def _update_tab_badges(self):
        if not self._import_result:
            return
        n_incomplete = len(self._import_result.incomplete_trades)
        n_complete = len(self._import_result.complete_trades)
        n_closed = len(self._import_result.closed_lots)

        self.tabs_review.setTabText(0, f"⚠️ ناقص ({n_incomplete})")
        self.tabs_review.setTabText(1, f"✅ کامل ({n_complete})")
        self.tabs_review.setTabText(2, f"📜 بسته‌شده ({n_closed})")

    # -----------------------------------------------------
    # گروه‌بندی — اختصاص نام استراتژی
    # -----------------------------------------------------

    def _create_strategy_from_selection(self):
        rows = sorted(set(
            idx.row() for idx in
            self.table_complete.selectedIndexes()))
        if not rows:
            QMessageBox.information(
                self, "اطلاع",
                "لطفاً ابتدا یک یا چند ردیف را انتخاب کنید.")
            return

        # جمع‌آوری trade ها
        selected_trades: List[TradeRecord] = []
        for r in rows:
            if 0 <= r < len(self._import_result.complete_trades):
                selected_trades.append(
                    self._import_result.complete_trades[r])

        if not selected_trades:
            return

        # پیشنهاد نام
        from position_saver.importer.suggest import suggest_strategy_name
        suggestion = suggest_strategy_name(selected_trades)

        # دیالوگ نام
        from PySide6.QtWidgets import QInputDialog
        items = [
            "Long Call", "Long Put",
            "Bull Call Spread", "Bear Put Spread",
            "Covered Call", "Long Box",
        ]
        if suggestion and suggestion not in items:
            items.insert(0, suggestion)

        default_index = 0
        if suggestion in items:
            default_index = items.index(suggestion)

        name, ok = QInputDialog.getItem(
            self, "نام استراتژی",
            f"نام استراتژی برای {len(selected_trades)} لگ:",
            items, default_index, True)
        if not ok or not name.strip():
            return

        # ذخیره در ستون «گروه»
        for r in rows:
            item = self.table_complete.item(r, 7)
            if item:
                item.setText(name.strip())

        QMessageBox.information(
            self, "✅ موفق",
            f"استراتژی «{name.strip()}» برای "
            f"{len(selected_trades)} لگ ثبت شد.")

    # -----------------------------------------------------
    # مرحله ۴ — تأیید
    # -----------------------------------------------------

    def _build_step_confirm(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel("📋 خلاصه‌ی ایمپورت")
        set_tone(info, "primary", big=True)
        layout.addWidget(info)

        self.lbl_confirm_summary = QLabel("—")
        self.lbl_confirm_summary.setWordWrap(True)
        layout.addWidget(self.lbl_confirm_summary)

        layout.addStretch()
        return widget

    def _refresh_confirm_summary(self):
        if not self._import_result:
            return
        r = self._import_result
        text = (
            f"📊 معاملات: {r.n_trades}\n"
            f"✅ کامل: {r.n_complete}\n"
            f"⚠️ ناقص: {r.n_incomplete}\n"
            f"📜 بسته‌شده: {r.n_closed_lots}\n"
            f"📌 باز: {r.n_open_lots}\n\n"
            f"🏦 کارگزاری: {self._broker}\n"
            f"📄 فایل: {os.path.basename(self._file_path)}"
        )
        self.lbl_confirm_summary.setText(text)

    # -----------------------------------------------------
    # ناوبری (دکمه‌های پایین)
    # -----------------------------------------------------

    def _build_navigation(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.btn_back = QPushButton("← قبلی")
        self.btn_back.clicked.connect(self._on_back)
        layout.addWidget(self.btn_back)

        layout.addStretch()

        self.btn_cancel = QPushButton("❌ انصراف")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

        self.btn_next = QPushButton("بعدی →")
        self.btn_next.clicked.connect(self._on_next)
        set_kind(self.btn_next, "primary")
        layout.addWidget(self.btn_next)

        return layout

    def _update_navigation(self):
        idx = self.stack.currentIndex()
        self._update_step_label()

        self.btn_back.setEnabled(idx > STEP_FILE)

        if idx == STEP_CONFIRM:
            self.btn_next.setText("✅ ایمپورت و ثبت")
        else:
            self.btn_next.setText("بعدی →")

    def _on_back(self):
        idx = self.stack.currentIndex()
        if idx > STEP_FILE:
            self.stack.setCurrentIndex(idx - 1)
            self._update_navigation()

    def _on_next(self):
        idx = self.stack.currentIndex()

        if idx == STEP_FILE:
            if not self._file_path:
                QMessageBox.warning(
                    self, "خطا", "لطفاً ابتدا فایل اکسل را انتخاب کنید.")
                return
            self._run_parse_and_move()

        elif idx == STEP_PREVIEW:
            # رفتن به بازبینی
            self._refresh_incomplete_table()
            self._refresh_complete_table()
            self._refresh_closed_table()
            self._update_tab_badges()
            self.stack.setCurrentIndex(STEP_REVIEW)
            self._update_navigation()

        elif idx == STEP_REVIEW:
            # رفتن به تأیید
            if not self._import_result:
                return
            if self._import_result.has_incomplete:
                reply = QMessageBox.question(
                    self, "هشدار",
                    f"⚠️ {self._import_result.n_incomplete} ردیف ناقص "
                    f"وجود دارد.\n\n"
                    f"آیا بدون تکمیل آن‌ها ادامه می‌دهید؟\n"
                    f"(این ردیف‌ها در پنل اصلی با علامت ⚠️ نمایش "
                    f"داده می‌شوند)",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    self.tabs_review.setCurrentIndex(0)
                    return

            self._refresh_confirm_summary()
            self.stack.setCurrentIndex(STEP_CONFIRM)
            self._update_navigation()

        elif idx == STEP_CONFIRM:
            self._commit_import()

    # -----------------------------------------------------
    # اجرای پارس
    # -----------------------------------------------------

    def _run_parse_and_move(self):
        """پارس فایل و رفتن به مرحله ۲"""
        # ساخت settings از UI
        self._settings = ImportSettings(
            match_method=self.cmb_match_method.currentData() or "fifo",
            time_window_seconds=self.spin_time_window.value(),
            skip_duplicates=self.chk_skip_duplicates.isChecked(),
        )

        # Snapshot
        snapshot = None
        try:
            snapshot = get_market_snapshot(
                use_cache=True, force_refresh=False)
        except Exception as e:
            logger.warning(f"Snapshot load failed: {e}")

        # اجرا
        try:
            self._import_result = self.engine.run(
                file_path=self._file_path,
                broker=self._broker,
                settings=self._settings,
                snapshot=snapshot,
            )
        except Exception as e:
            logger.exception(f"Engine run failed: {e}")
            QMessageBox.critical(
                self, "خطا", f"خطا در ایمپورت:\n{e}")
            return

        if not self._import_result.trades:
            QMessageBox.warning(
                self, "خطا",
                "هیچ معامله‌ای در فایل یافت نشد.\n"
                "لطفاً ساختار فایل و کارگزاری انتخابی را بررسی کنید.")
            return

        # پر کردن جدول پیش‌نمایش
        self._refresh_preview_table()

        self.stack.setCurrentIndex(STEP_PREVIEW)
        self._update_navigation()

    # -----------------------------------------------------
    # اجرای Commit نهایی
    # -----------------------------------------------------

    def _commit_import(self):
        """ثبت نهایی در positions_data.json"""
        if not self._import_result:
            return

        try:
            positions = self._build_positions()
        except Exception as e:
            logger.exception(f"Build positions failed: {e}")
            QMessageBox.critical(
                self, "خطا", f"خطا در ساخت موقعیت‌ها:\n{e}")
            return

        if not positions and not self._import_result.closed_lots:
            QMessageBox.warning(
                self, "اطلاع",
                "هیچ موقعیتی برای ثبت وجود ندارد.")
            return

        # ذخیره در storage
        try:
            existing = self.storage.load_positions()
            all_positions = existing + positions
            ok = self.storage.save_positions(all_positions)
            if not ok:
                QMessageBox.critical(
                    self, "خطا", "ذخیره‌سازی ناموفق بود.")
                return
        except Exception as e:
            logger.exception(f"Save positions failed: {e}")
            QMessageBox.critical(
                self, "خطا", f"خطا در ذخیره‌سازی:\n{e}")
            return

        # ذخیره‌ی batch
        try:
            batch = ImportBatch(
                broker=self._broker,
                source_file=self._file_path,
                n_trades=self._import_result.n_trades,
                n_positions_open=len(positions),
                n_positions_closed=self._import_result.n_closed_lots,
                n_needs_review=len(
                    self._import_result.incomplete_trades),
                position_ids=[p.position_id for p in positions],
            )
            self.storage.save_import_batch(batch.to_dict())
        except Exception as e:
            logger.warning(f"Save batch failed: {e}")

        QMessageBox.information(
            self, "✅ موفق",
            f"ایمپورت با موفقیت انجام شد.\n\n"
            f"موقعیت‌های ثبت‌شده: {len(positions)}\n"
            f"معاملات بسته‌شده: {self._import_result.n_closed_lots}")

        self.accept()

    def _build_positions(self) -> List[StrategyPosition]:
        """
        ساخت StrategyPosition از ImportResult.

        منطق:
            - هر lot باز = یک موقعیت OPEN
            - هر lot بسته = یک موقعیت CLOSED
        """
        positions: List[StrategyPosition] = []
        today = today_jalali()

        # پردازش lot های باز
        for lot in self._import_result.open_lots:
            pos = self._build_position_from_lot(
                lot, status=PositionStatus.OPEN)
            if pos:
                positions.append(pos)

        # پردازش lot های بسته
        for lot in self._import_result.closed_lots:
            pos = self._build_position_from_lot(
                lot, status=PositionStatus.CLOSED)
            if pos:
                positions.append(pos)

        return positions

    def _build_position_from_lot(
        self, lot: MatchedLot, status: PositionStatus
    ) -> Optional[StrategyPosition]:
        """ساخت یک موقعیت از یک lot"""
        if not lot.open_trade:
            return None

        open_t = lot.open_trade
        close_t = lot.close_trade

        # ساخت Leg ورود
        entry_leg = OptionLeg(
            symbol=open_t.symbol,
            is_option=open_t.is_option,
            option_kind=open_t.option_kind,
            leg_type=open_t.side,
            strike_price=open_t.strike_price or 0.0,
            contract_size=open_t.effective_contract_size,
            quantity=open_t.quantity,
            entry_price=open_t.price,
            current_price=open_t.price,
            expiry_date=open_t.expiry_date or "",
            ins_code=open_t.ins_code or "",
            open_date=open_t.raw_date,
            open_time=open_t.raw_time,
            trade_time=open_t.raw_time,
            source="excel_import",
            trade_ref=open_t.trade_id,
            needs_review=open_t.needs_review,
        )
        entry_leg.entry_fee = \
            PositionPnLCalculator.calculate_leg_entry_fee(entry_leg)

        # اگر lot بسته شده، leg خروج بساز
        if close_t is not None:
            # close_price روی همان leg ورود ست می‌شود
            entry_leg.close_price = close_t.price
            entry_leg.close_fee = \
                PositionPnLCalculator.calculate_leg_close_fee(
                    entry_leg, close_t.price)
            entry_leg.close_date = close_t.raw_date
            entry_leg.close_time = close_t.raw_time
            entry_leg.close_trade_ref = close_t.trade_id

            # محاسبه‌ی PnL محقق‌شده
            try:
                temp_pos = StrategyPosition(
                    strategy_name="temp",
                    broker_name=self._broker,
                    underlying_symbol=open_t.underlying_symbol,
                    execution_date=open_t.raw_date,
                    expiry_date=open_t.expiry_date or "",
                    status=PositionStatus.CLOSED,
                    legs=[entry_leg],
                )
                rpnl, _ = PositionPnLCalculator.calculate_realized_pnl(
                    temp_pos)
                entry_leg.realized_pnl = rpnl
            except Exception:
                pass

        # نام استراتژی
        strategy_name = self._suggest_for_leg(entry_leg)

        # expiry موقعیت
        position_expiry = open_t.expiry_date or ""

        pos = StrategyPosition(
            strategy_name=strategy_name,
            broker_name=self._broker,
            underlying_symbol=open_t.underlying_symbol,
            execution_date=open_t.raw_date,
            expiry_date=position_expiry,
            status=status,
            legs=[entry_leg],
            alert_target_roi=self._settings.default_alert_roi,
            source="excel_import",
            needs_review=open_t.needs_review,
        )

        if close_t is not None:
            pos.close_date = close_t.raw_date
            if open_t.option_kind and open_t.is_option:
                # قیمت پایانی سهم پایه در لحظه بستن
                pos.underlying_price_at_close = 0.0

        return pos

    def _suggest_for_leg(self, leg: OptionLeg) -> str:
        """پیشنهاد نام استراتژی برای یک لگ"""
        from position_saver.importer.suggest import suggest_strategy_name
        from position_saver.importer.schemas import TradeRecord
        t = TradeRecord(
            symbol=leg.symbol,
            side=leg.leg_type,
            quantity=leg.quantity,
            price=leg.entry_price,
            option_kind=leg.option_kind,
            strike_price=leg.strike_price,
            contract_size=leg.contract_size,
        )
        s = suggest_strategy_name([t])
        if s:
            return s
        # fallback
        if leg.is_call and leg.leg_type == LegType.BUY:
            return "Long Call"
        if leg.is_put and leg.leg_type == LegType.BUY:
            return "Long Put"
        return "Imported"

    # =====================================================
    # API عمومی
    # =====================================================

    def get_result(self) -> Optional[ImportResult]:
        """نتیجه‌ی ایمپورت (برای استفاده‌ی خارجی)"""
        return self._import_result


__all__ = ["ImportWizardDialog"]