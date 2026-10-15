# position_saver/ui/report_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ گزارش‌گیری دوره‌ای.

ویژگی‌ها:
    - فیلتر تاریخ (از/تا)
    - فیلتر نوع استراتژی
    - فیلتر نماد پایه
    - فیلتر وضعیت
    - فیلتر کارگزاری
    - فیلتر منبع
    - خروجی اکسل
    - معماری قابل توسعه (قابل افزودن PDF در آینده)
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import jdatetime
import pandas as pd

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QMessageBox,
    QHeaderView, QGroupBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QDialogButtonBox, QFileDialog,
    QListWidget, QListWidgetItem, QAbstractItemView as QAI,
    QCheckBox, QWidget, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator

from position_saver.models import (
    StrategyPosition, PositionStatus,
)
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.shared_analytics import SharedAnalytics
from position_saver.theme import (
    Theme, CURRENCY,
    fmt_money, fmt_pct, fmt_int,
    pnl_tone, set_kind, set_tone,
)


logger = logging.getLogger("PositionSaver.UI.Report")


# ═══════════════════════════════════════════════════
# معماری Report (قابل توسعه)
# ═══════════════════════════════════════════════════

class ReportFilter:
    """فیلتر گزارش."""

    def __init__(
        self,
        date_from: str = "",
        date_to: str = "",
        strategy_types: Optional[List[str]] = None,
        underlying_symbols: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        brokers: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
    ):
        self.date_from = date_from
        self.date_to = date_to
        self.strategy_types = strategy_types or []
        self.underlying_symbols = underlying_symbols or []
        self.statuses = statuses or []
        self.brokers = brokers or []
        self.sources = sources or []


class ReportRow:
    """یک ردیف گزارش."""

    def __init__(
        self,
        position_id: str,
        strategy_name: str,
        underlying_symbol: str,
        execution_date: str,
        expiry_date: str,
        status: str,
        broker: str,
        source: str,
        pnl: float,
        roi: float,
        is_live: bool,
        days_elapsed: int = 0,
        days_total: int = 0,
        target_monthly: float = 0.0,
        threshold: float = 0.0,
        pace: float = 0.0,
        num_legs: int = 0,
        notes: str = "",
    ):
        self.position_id = position_id
        self.strategy_name = strategy_name
        self.underlying_symbol = underlying_symbol
        self.execution_date = execution_date
        self.expiry_date = expiry_date
        self.status = status
        self.broker = broker
        self.source = source
        self.pnl = pnl
        self.roi = roi
        self.is_live = is_live
        self.days_elapsed = days_elapsed
        self.days_total = days_total
        self.target_monthly = target_monthly
        self.threshold = threshold
        self.pace = pace
        self.num_legs = num_legs
        self.notes = notes


class ReportResult:
    """نتیجه‌ی گزارش."""

    def __init__(self):
        self.rows: List[ReportRow] = []
        self.total_pnl = 0.0
        self.total_realized = 0.0
        self.total_live = 0.0
        self.count = 0

    def add_row(self, row: ReportRow):
        self.rows.append(row)
        self.count += 1
        if row.is_live:
            self.total_live += row.pnl
        else:
            self.total_realized += row.pnl

    @property
    def total(self) -> float:
        return self.total_live + self.total_realized


class BaseReportExporter(ABC):
    """کلاس پایه‌ی صادرکننده‌ی گزارش."""

    @abstractmethod
    def export(self, result: ReportResult, filepath: str) -> bool:
        pass

    @abstractmethod
    def extension(self) -> str:
        pass

    @abstractmethod
    def display_name(self) -> str:
        pass


class ExcelReportExporter(BaseReportExporter):
    """صادرکننده‌ی اکسل."""

    def export(self, result: ReportResult, filepath: str) -> bool:
        try:
            rows = []
            for r in result.rows:
                rows.append({
                    "Position_ID": r.position_id,
                    "Strategy_Name": r.strategy_name,
                    "Underlying": r.underlying_symbol,
                    "Execution_Date": r.execution_date,
                    "Expiry_Date": r.expiry_date,
                    "Days_Elapsed": r.days_elapsed,
                    "Days_Total": r.days_total,
                    "Status": r.status,
                    "Broker": r.broker,
                    "Source": r.source,
                    "PnL": int(r.pnl),
                    "PnL_ROI_Pct": round(r.roi, 2),
                    "Is_Live": r.is_live,
                    "Target_Monthly_Pct": r.target_monthly,
                    "Threshold_Pct": r.threshold,
                    "Pace": round(r.pace, 2),
                    "Num_Legs": r.num_legs,
                    "Notes": r.notes,
                })

            df = pd.DataFrame(rows)

            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="Report", index=False)

                # خلاصه
                summary = pd.DataFrame([{
                    "Total_Positions": result.count,
                    "Total_PnL": int(result.total),
                    "Total_Live": int(result.total_live),
                    "Total_Realized": int(result.total_realized),
                }])
                summary.to_excel(
                    writer, sheet_name="Summary", index=False)

            return True
        except Exception as e:
            logger.exception(f"Excel export failed: {e}")
            return False

    def extension(self) -> str:
        return "xlsx"

    def display_name(self) -> str:
        return "Excel (*.xlsx)"


# (در آینده)
# class PdfReportExporter(BaseReportExporter):
#     ...


# ═══════════════════════════════════════════════════
# ReportDialog
# ═══════════════════════════════════════════════════

class ReportDialog(QDialog):
    """دیالوگ گزارش‌گیری."""

    # ستون‌ها
    COL_ID = 0
    COL_STRATEGY = 1
    COL_UNDERLYING = 2
    COL_EXEC = 3
    COL_EXPIRY = 4
    COL_DAYS = 5
    COL_STATUS = 6
    COL_BROKER = 7
    COL_PNL = 8
    COL_ROI = 9
    COL_TARGET = 10
    COL_THRESHOLD = 11
    COL_PACE = 12
    N_COLS = 13

    def __init__(
        self,
        parent=None,
        positions: Optional[List[StrategyPosition]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("📊 گزارش‌گیری")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(1200, 750)

        self.all_positions = positions or []
        self._result: Optional[ReportResult] = None

        self._build_ui()
        self._load_filter_options()
        self._apply_default_dates()
        self._on_apply_filters()  # نمایش اولیه

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── فیلترها ───
        filter_group = QGroupBox("🔍 فیلترها")
        filter_layout = QVBoxLayout(filter_group)

        # ردیف اول: تاریخ
        date_row = QHBoxLayout()

        date_row.addWidget(QLabel("از تاریخ:"))
        self.txt_date_from = QLineEdit()
        self.txt_date_from.setPlaceholderText("1404/01/01")
        self.txt_date_from.setValidator(self._make_date_validator())
        self.txt_date_from.setMaximumWidth(140)
        date_row.addWidget(self.txt_date_from)

        date_row.addSpacing(20)

        date_row.addWidget(QLabel("تا تاریخ:"))
        self.txt_date_to = QLineEdit()
        self.txt_date_to.setPlaceholderText("1404/12/29")
        self.txt_date_to.setValidator(self._make_date_validator())
        self.txt_date_to.setMaximumWidth(140)
        date_row.addWidget(self.txt_date_to)

        date_row.addSpacing(20)

        btn_today = QPushButton("امروز")
        btn_today.setFixedWidth(80)
        btn_today.clicked.connect(self._set_today)
        date_row.addWidget(btn_today)

        btn_this_month = QPushButton("این ماه")
        btn_this_month.setFixedWidth(80)
        btn_this_month.clicked.connect(self._set_this_month)
        date_row.addWidget(btn_this_month)

        btn_this_year = QPushButton("امسال")
        btn_this_year.setFixedWidth(80)
        btn_this_year.clicked.connect(self._set_this_year)
        date_row.addWidget(btn_this_year)

        date_row.addStretch()
        filter_layout.addLayout(date_row)

        # ردیف دوم: فیلترهای چند-انتخابی
        multi_row = QHBoxLayout()
        multi_row.setSpacing(10)

        # استراتژی
        self.list_strategy = self._make_multi_list(
            "نوع استراتژی", 200)
        multi_row.addWidget(self.list_strategy)

        # نماد
        self.list_underlying = self._make_multi_list(
            "نماد پایه", 150)
        multi_row.addWidget(self.list_underlying)

        # وضعیت
        self.list_status = self._make_multi_list(
            "وضعیت", 150)
        multi_row.addWidget(self.list_status)

        # کارگزاری
        self.list_broker = self._make_multi_list(
            "کارگزاری", 130)
        multi_row.addWidget(self.list_broker)

        # منبع
        self.list_source = self._make_multi_list(
            "منبع", 130)
        multi_row.addWidget(self.list_source)

        multi_row.addStretch()
        filter_layout.addLayout(multi_row)

        # ردیف سوم: دکمه‌ها
        btn_row = QHBoxLayout()

        btn_apply = QPushButton("🔄 اعمال فیلتر")
        btn_apply.clicked.connect(self._on_apply_filters)
        set_kind(btn_apply, "primary")
        btn_row.addWidget(btn_apply)

        btn_clear = QPushButton("✗ پاک کردن فیلترها")
        btn_clear.clicked.connect(self._on_clear_filters)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        # خروجی
        btn_export = QPushButton("📤 خروجی اکسل")
        btn_export.clicked.connect(self._on_export_excel)
        set_kind(btn_export, "primary")
        btn_row.addWidget(btn_export)

        filter_layout.addLayout(btn_row)
        layout.addWidget(filter_group)

        # ─── خلاصه ───
        self.lbl_summary = QLabel("—")
        self.lbl_summary.setStyleSheet(
            f"padding: 12px; background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; "
            f"border-radius: 6px; font-size: 13px; "
            f"font-weight: bold;")
        layout.addWidget(self.lbl_summary)

        # ─── جدول ───
        self.table = QTableWidget(0, self.N_COLS)
        self.table.setHorizontalHeaderLabels([
            "شناسه", "استراتژی", "نماد", "تاریخ اجرا", "سررسید",
            "روزها (سپری/کل)", "وضعیت", "کارگزاری",
            "PnL", "ROI", "تارگت ماهانه", "آستانه امروز", "Pace",
        ])

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        h.setDefaultAlignment(Qt.AlignCenter)

        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setColumnHidden(self.COL_ID, True)

        self.table.setColumnWidth(self.COL_STRATEGY, 130)
        self.table.setColumnWidth(self.COL_UNDERLYING, 90)
        self.table.setColumnWidth(self.COL_EXEC, 90)
        self.table.setColumnWidth(self.COL_EXPIRY, 90)
        self.table.setColumnWidth(self.COL_DAYS, 110)
        self.table.setColumnWidth(self.COL_STATUS, 100)
        self.table.setColumnWidth(self.COL_BROKER, 100)
        self.table.setColumnWidth(self.COL_PNL, 120)
        self.table.setColumnWidth(self.COL_ROI, 85)
        self.table.setColumnWidth(self.COL_TARGET, 90)
        self.table.setColumnWidth(self.COL_THRESHOLD, 90)
        self.table.setColumnWidth(self.COL_PACE, 70)

        layout.addWidget(self.table, 1)

        # ─── دکمه بستن ───
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("بستن")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_multi_list(
        self, title: str, width: int
    ) -> QWidget:
        """ساخت لیست چند-انتخابی."""
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)

        label = QLabel(title)
        label.setStyleSheet(
            f"font-size: 11px; color: {Theme.MUTED}; "
            f"font-weight: bold;")
        vbox.addWidget(label)

        lst = QListWidget()
        lst.setMaximumWidth(width)
        lst.setMaximumHeight(90)
        lst.setSelectionMode(QAI.MultiSelection)
        vbox.addWidget(lst)

        return container

    @staticmethod
    def _make_date_validator() -> QRegularExpressionValidator:
        pattern = QRegularExpression(
            r'^\d{0,4}(/\d{0,2}(/\d{0,2})?)?$')
        return QRegularExpressionValidator(pattern)

    # ═══════════════════════════════════════════════
    # بارگذاری فیلترها
    # ═══════════════════════════════════════════════

    def _load_filter_options(self):
        """پر کردن گزینه‌های فیلتر از positions."""
        strategies = set()
        underlyings = set()
        statuses = set()
        brokers = set()
        sources = set()

        for pos in self.all_positions:
            if pos.strategy_name:
                strategies.add(pos.strategy_name)
            if pos.underlying_symbol:
                underlyings.add(pos.underlying_symbol)
            if pos.status:
                statuses.add(pos.status.value)
            if pos.broker_name:
                brokers.add(pos.broker_name)
            if pos.source:
                sources.add(pos.source)

        self._fill_list(self.list_strategy, sorted(strategies))
        self._fill_list(self.list_underlying, sorted(underlyings))
        self._fill_list(
            self.list_status,
            sorted(statuses),
            display_map={
                "open": "🟢 باز",
                "closed": "🔒 بسته",
                "exercised": "🏦 اعمال",
                "cash_settled": "💵 تسویه",
                "defaulted": "⚖️ نکول",
                "you_defaulted": "❌ نکول خودم",
            },
        )
        self._fill_list(self.list_broker, sorted(brokers))
        self._fill_list(
            self.list_source,
            sorted(sources),
            display_map={
                "manual": "✏️ دستی",
                "excel_import": "📥 ایمپورت",
            },
        )

    def _fill_list(
        self,
        list_widget: QListWidget,
        items: List[str],
        display_map: Optional[Dict[str, str]] = None,
    ):
        list_widget.clear()
        for item in items:
            display = display_map.get(item, item) \
                if display_map else item
            it = QListWidgetItem(display)
            it.setData(Qt.UserRole, item)
            list_widget.addItem(it)

    # ═══════════════════════════════════════════════
    # تاریخ پیش‌فرض
    # ═══════════════════════════════════════════════

    def _apply_default_dates(self):
        """از اول ماه جاری تا امروز."""
        today = jdatetime.date.today()
        first_of_month = jdatetime.date(today.year, today.month, 1)
        self.txt_date_from.setText(
            first_of_month.strftime("%Y/%m/%d"))
        self.txt_date_to.setText(today.strftime("%Y/%m/%d"))

    def _set_today(self):
        today = jdatetime.date.today().strftime("%Y/%m/%d")
        self.txt_date_from.setText(today)
        self.txt_date_to.setText(today)

    def _set_this_month(self):
        self._apply_default_dates()

    def _set_this_year(self):
        today = jdatetime.date.today()
        first_of_year = jdatetime.date(today.year, 1, 1)
        self.txt_date_from.setText(
            first_of_year.strftime("%Y/%m/%d"))
        self.txt_date_to.setText(today.strftime("%Y/%m/%d"))

    # ═══════════════════════════════════════════════
    # اعمال فیلترها
    # ═══════════════════════════════════════════════

    def _get_selected_values(
        self, list_widget: QListWidget
    ) -> List[str]:
        """گرفتن مقادیر انتخاب‌شده."""
        values = []
        for item in list_widget.selectedItems():
            val = item.data(Qt.UserRole)
            if val:
                values.append(val)
        return values

    def _build_filter(self) -> ReportFilter:
        """ساخت فیلتر از UI."""
        return ReportFilter(
            date_from=self.txt_date_from.text().strip(),
            date_to=self.txt_date_to.text().strip(),
            strategy_types=self._get_selected_values(
                self.list_strategy),
            underlying_symbols=self._get_selected_values(
                self.list_underlying),
            statuses=self._get_selected_values(self.list_status),
            brokers=self._get_selected_values(self.list_broker),
            sources=self._get_selected_values(self.list_source),
        )

    def _on_apply_filters(self):
        """اعمال فیلتر و نمایش."""
        f = self._build_filter()

        filtered = self._filter_positions(f)
        self._result = self._build_report_result(filtered)
        self._populate_table()
        self._update_summary()

    def _on_clear_filters(self):
        """پاک کردن فیلترها."""
        self.list_strategy.clearSelection()
        self.list_underlying.clearSelection()
        self.list_status.clearSelection()
        self.list_broker.clearSelection()
        self.list_source.clearSelection()
        self._apply_default_dates()
        self._on_apply_filters()

    def _filter_positions(
        self, f: ReportFilter
    ) -> List[StrategyPosition]:
        """فیلتر کردن positions."""
        result = []

        for pos in self.all_positions:
            # تاریخ
            if f.date_from:
                if pos.execution_date < f.date_from:
                    continue
            if f.date_to:
                if pos.execution_date > f.date_to:
                    continue

            # استراتژی
            if f.strategy_types:
                if pos.strategy_name not in f.strategy_types:
                    continue

            # نماد
            if f.underlying_symbols:
                if pos.underlying_symbol not in f.underlying_symbols:
                    continue

            # وضعیت
            if f.statuses:
                if pos.status.value not in f.statuses:
                    continue

            # کارگزاری
            if f.brokers:
                if pos.broker_name not in f.brokers:
                    continue

            # منبع
            if f.sources:
                if pos.source not in f.sources:
                    continue

            result.append(pos)

        return result

    def _build_report_result(
        self, positions: List[StrategyPosition]
    ) -> ReportResult:
        """ساخت نتیجه‌ی گزارش."""
        result = ReportResult()

        for pos in positions:
            # PnL
            if pos.status == PositionStatus.OPEN:
                pnl, roi = \
                    PositionPnLCalculator.calculate_live_pnl(pos)
                is_live = True
            else:
                pnl, roi = \
                    PositionPnLCalculator.calculate_realized_pnl(pos)
                is_live = False

            d_elapsed = pos.days_elapsed()
            d_total = pos.total_days()
            threshold = SharedAnalytics.calculate_dynamic_threshold(
                pos.target_roi_maturity, d_elapsed)
            pace = 0.0
            if threshold > 0 and is_live:
                pace = roi / threshold

            row = ReportRow(
                position_id=pos.position_id,
                strategy_name=pos.strategy_name,
                underlying_symbol=pos.underlying_symbol,
                execution_date=pos.execution_date,
                expiry_date=pos.expiry_date,
                status=pos.status.value,
                broker=pos.broker_name or "—",
                source=pos.source,
                pnl=pnl,
                roi=roi,
                is_live=is_live,
                days_elapsed=d_elapsed,
                days_total=d_total,
                target_monthly=pos.target_roi_maturity,
                threshold=threshold,
                pace=pace,
                num_legs=len(pos.legs),
                notes=pos.notes or "",
            )
            result.add_row(row)

        return result

    # ═══════════════════════════════════════════════
    # جدول
    # ═══════════════════════════════════════════════

    def _populate_table(self):
        if self._result is None:
            return

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for r in self._result.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # ID
            id_item = QTableWidgetItem(r.position_id)
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_ID, id_item)

            # استراتژی
            self.table.setItem(row, self.COL_STRATEGY,
                QTableWidgetItem(r.strategy_name))

            # نماد
            self.table.setItem(row, self.COL_UNDERLYING,
                QTableWidgetItem(r.underlying_symbol))

            # تاریخ‌ها
            self.table.setItem(row, self.COL_EXEC,
                QTableWidgetItem(r.execution_date))
            self.table.setItem(row, self.COL_EXPIRY,
                QTableWidgetItem(r.expiry_date))

            # روزها
            days_text = f"{r.days_elapsed} / {r.days_total}"
            days_item = QTableWidgetItem(days_text)
            days_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_DAYS, days_item)

            # وضعیت
            status_map = {
                "open": "🟢 باز",
                "closed": "🔒 بسته",
                "exercised": "🏦 اعمال",
                "cash_settled": "💵 تسویه",
                "defaulted": "⚖️ نکول",
                "you_defaulted": "❌ نکول خودم",
            }
            status_item = QTableWidgetItem(
                status_map.get(r.status, r.status))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_STATUS, status_item)

            # کارگزاری
            self.table.setItem(row, self.COL_BROKER,
                QTableWidgetItem(r.broker))

            # PnL
            pnl_item = QTableWidgetItem(fmt_money(r.pnl))
            pnl_item.setTextAlignment(Qt.AlignCenter)
            pnl_item.setForeground(
                QColor(self._tone_color(pnl_tone(r.pnl))))
            self.table.setItem(row, self.COL_PNL, pnl_item)

            # ROI
            roi_item = QTableWidgetItem(fmt_pct(r.roi, digits=2))
            roi_item.setTextAlignment(Qt.AlignCenter)
            roi_item.setForeground(
                QColor(self._tone_color(pnl_tone(r.roi))))
            self.table.setItem(row, self.COL_ROI, roi_item)

            # Target
            target_item = QTableWidgetItem(
                fmt_pct(r.target_monthly, digits=1, signed=False)
                if r.target_monthly > 0 else "—")
            target_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_TARGET, target_item)

            # Threshold
            threshold_item = QTableWidgetItem(
                fmt_pct(r.threshold, digits=2, signed=False)
                if r.threshold > 0 else "—")
            threshold_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_THRESHOLD, threshold_item)

            # Pace
            if r.pace != 0:
                pace_item = QTableWidgetItem(f"{r.pace:.2f}x")
                if r.pace >= 1.0:
                    pace_item.setForeground(QColor(Theme.PROFIT))
                elif r.pace >= 0.8:
                    pace_item.setForeground(QColor(Theme.WARN))
                else:
                    pace_item.setForeground(QColor(Theme.INFO))
            else:
                pace_item = QTableWidgetItem("—")
                pace_item.setForeground(QColor(Theme.MUTED))
            pace_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_PACE, pace_item)

        self.table.setSortingEnabled(True)

    def _update_summary(self):
        if self._result is None:
            return

        r = self._result
        total = r.total

        text = (
            f"📊 <b>خلاصه‌ی گزارش</b>  |  "
            f"تعداد موقعیت‌ها: <b>{r.count}</b>  |  "
            f"سود/زیان کل: <b style='color: "
            f"{self._tone_color(pnl_tone(total))};'>"
            f"{fmt_money(total)} {CURRENCY}</b>  |  "
            f"<span style='color: {Theme.MUTED};'>"
            f"(لایو: {fmt_money(r.total_live)} | "
            f"محقق: {fmt_money(r.total_realized)})</span>"
        )
        self.lbl_summary.setText(text)

    @staticmethod
    def _tone_color(tone: str) -> str:
        return {
            "profit": Theme.PROFIT, "loss": Theme.LOSS,
            "warn": Theme.WARN, "muted": Theme.MUTED,
            "primary": Theme.PRIMARY, "neutral": Theme.TEXT,
        }.get(tone, Theme.TEXT)

    # ═══════════════════════════════════════════════
    # خروجی
    # ═══════════════════════════════════════════════

    def _on_export_excel(self):
        if self._result is None or not self._result.rows:
            QMessageBox.information(
                self, "اطلاع",
                "هیچ داده‌ای برای خروجی وجود ندارد.")
            return

        default_name = (
            f"report_"
            f"{jdatetime.date.today().strftime('%Y%m%d_%H%M%S')}.xlsx")

        file_path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره گزارش اکسل", default_name,
            "Excel Files (*.xlsx)")

        if not file_path:
            return

        exporter = ExcelReportExporter()
        success = exporter.export(self._result, file_path)

        if success:
            QMessageBox.information(
                self, "✅ موفق",
                f"گزارش با موفقیت ذخیره شد:\n{file_path}")
        else:
            QMessageBox.critical(
                self, "خطا",
                "خطا در ذخیره‌سازی گزارش.")


__all__ = [
    "ReportDialog",
    "ReportFilter",
    "ReportRow",
    "ReportResult",
    "BaseReportExporter",
    "ExcelReportExporter",
]