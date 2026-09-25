# position_saver/ui/main_widget.py
# -*- coding: utf-8 -*-

import re
from datetime import datetime
from typing import List, Optional, Any

import jdatetime
import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QHeaderView, QMessageBox, QFileDialog, QFrame,
    QCheckBox, QSpinBox, QInputDialog, QAbstractItemView,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QBrush

from position_saver.models import (
    StrategyPosition, PositionStatus, LegType,
)
from position_saver.storage import PositionStorage
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.live_monitor import (
    LivePositionMonitorThread, is_expired_date,
)
from position_saver.ui.dialogs import (
    PositionEditDialog, DefaultSettlementDialog,
)


# =====================================================
# رنگ‌ها
# =====================================================

ROW_COLOR_ALT = QColor(247, 249, 252)
ROW_COLOR_NORMAL = QColor(255, 255, 255)

COLOR_PROFIT = "color: #2E7D32; font-weight: bold;"
COLOR_LOSS = "color: #C62828; font-weight: bold;"
COLOR_NEUTRAL = "color: #333333; font-weight: bold;"


# =====================================================
# آیتم جدول با پشتیبانی از سورت عددی
# =====================================================

class SortableItem(QTableWidgetItem):
    """آیتم جدول با قابلیت سورت بر اساس مقدار سفارشی"""

    def __init__(self, display_text: str, sort_value: Any = None):
        super().__init__(str(display_text))
        self._sort_value = sort_value if sort_value is not None else display_text
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


# =====================================================
# ویجت اصلی
# =====================================================

class PositionSaverWidget(QWidget):
    """ویجت اصلی مدیریت موقعیت‌های استراتژی آپشن"""

    COL_ID = 0
    COL_STRATEGY = 1
    COL_BROKER = 2
    COL_UNDERLYING = 3
    COL_EXEC_DATE = 4
    COL_EXPIRY_DATE = 5
    COL_LEGS = 6
    COL_NET_COST = 7
    COL_TARGET_ROI = 8
    COL_LIVE_PNL = 9
    COL_STATUS = 10
    N_COLS = 11

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        storage: Optional[PositionStorage] = None,
        auto_start_monitor: bool = True,
    ):
        super().__init__(parent)

        self.storage = storage if storage is not None else PositionStorage()
        self.positions: List[StrategyPosition] = []
        self._monitor_started = False
        self._expired_alerted = set()
        self._last_success_time: Optional[datetime] = None
        self._market_snapshot = None

        # ترد پس‌زمینه
        self.monitor_thread = LivePositionMonitorThread(
            self.storage, check_interval=10)
        self.monitor_thread.prices_updated.connect(self.on_prices_updated)
        self.monitor_thread.alerts_found.connect(self.on_alerts_found)
        self.monitor_thread.expired_found.connect(self.on_expired_found)
        self.monitor_thread.connection_status.connect(
            self.on_connection_status)

        self.init_ui()
        self.load_data()

        if auto_start_monitor:
            self.start_monitor()

    # =====================================================
    # چرخه حیات
    # =====================================================

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

    # =====================================================
    # ساخت UI
    # =====================================================

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ─── ۱. تولبار سراسری ───
        toolbar = QHBoxLayout()

        self.btn_add = QPushButton("➕ ثبت موقعیت جدید")
        self.btn_add.clicked.connect(self.add_position)

        self.btn_edit = QPushButton("✏️ ویرایش")
        self.btn_edit.clicked.connect(self.edit_position)

        self.btn_delete = QPushButton("🗑 حذف")
        self.btn_delete.clicked.connect(self.delete_position)

        self.btn_import = QPushButton("📥 خواندن از فایل اکسل")
        self.btn_import.clicked.connect(self.import_from_excel)

        # ✅ خروجی به اکسل
        self.btn_export = QPushButton("📤 خروجی به اکسل")
        self.btn_export.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_to_excel)

        # ✅ دکمه ارسال موقعیت به بله
        self.btn_send_bale = QPushButton("📨 ارسال موقعیت به بله")
        self.btn_send_bale.setStyleSheet(
            "background-color: #673AB7; color: white; font-weight: bold;")
        self.btn_send_bale.setToolTip(
            "ارسال موقعیت‌های انتخاب‌شده به بله\n"
            "با نگه‌داشتن Ctrl یا Shift می‌توانید چند موقعیت را انتخاب کنید")
        self.btn_send_bale.clicked.connect(self.send_positions_to_bale)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_export)
        toolbar.addWidget(self.btn_send_bale)

        # ✅ دکمه دریافت دستی
        self.btn_manual = QPushButton("⚡ دریافت دستی قیمت‌های لحظه‌ای")
        self.btn_manual.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_manual.clicked.connect(self.manual_refresh_data)
        toolbar.addWidget(self.btn_manual)

        self.chk_auto_refresh = QCheckBox("دریافت خودکار داده")
        self.chk_auto_refresh.setChecked(True)
        self.chk_auto_refresh.toggled.connect(self.toggle_auto_refresh)
        toolbar.addWidget(self.chk_auto_refresh)

        toolbar.addWidget(QLabel("تایمر (ثانیه):"))
        self.spin_timer = QSpinBox()
        self.spin_timer.setRange(1, 3600)
        self.spin_timer.setValue(10)
        self.spin_timer.valueChanged.connect(self.change_timer_interval)
        toolbar.addWidget(self.spin_timer)

        self.lbl_minutes = QLabel("(0.2 دقیقه)")
        self.lbl_minutes.setStyleSheet("color: #555; font-weight: bold;")
        toolbar.addWidget(self.lbl_minutes)

        toolbar.addStretch()

        # نشانگر وضعیت اتصال
        self.lbl_connection = QLabel("⚪ در انتظار...")
        self.lbl_connection.setStyleSheet(
            "color: gray; font-weight: bold; padding: 0 8px;")
        toolbar.addWidget(self.lbl_connection)

        main_layout.addLayout(toolbar)

        # ─── ۲. تولبار اقدام سریع ───
        action_bar = QHBoxLayout()

        self.btn_cash_settle = QPushButton("📌 ثبت تسویه نقدی")
        self.btn_cash_settle.setStyleSheet(
            "background-color: #FF9800; color: white; font-weight: bold;")
        self.btn_cash_settle.clicked.connect(self.settle_cash)
        action_bar.addWidget(self.btn_cash_settle)

        self.btn_exercise = QPushButton("🏦 ثبت اعمال فیزیکی")
        self.btn_exercise.setStyleSheet(
            "background-color: #673AB7; color: white; font-weight: bold;")
        self.btn_exercise.clicked.connect(self.settle_exercise)
        action_bar.addWidget(self.btn_exercise)

        self.btn_manual_close = QPushButton("✏️ بستن دستی")
        self.btn_manual_close.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_manual_close.clicked.connect(self.close_manually)
        action_bar.addWidget(self.btn_manual_close)

        # ✅ دکمه ثبت نکول CALL
        self.btn_default = QPushButton("⚖️ ثبت نکول CALL")
        self.btn_default.setStyleSheet(
            "background-color: #D32F2F; color: white; font-weight: bold;")
        self.btn_default.setToolTip(
            "ثبت نکول در روز سررسید (فقط برای CALL)\n"
            "طرف مقابل سهم پایه را تحویل نداده است")
        self.btn_default.clicked.connect(self.register_default)
        action_bar.addWidget(self.btn_default)

        action_bar.addStretch()
        main_layout.addLayout(action_bar)

        # ─── ۳. تب‌بندی سه‌گانه ───
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.tab_active = self._build_table_tab()
        self.tabs.addTab(self.tab_active, "🟢 فعال")

        self.tab_pending = self._build_table_tab()
        self.tabs.addTab(self.tab_pending, "⚠️ نیازمند تعیین تکلیف")

        self.tab_history = self._build_table_tab()
        self.tabs.addTab(self.tab_history, "📜 تاریخچه")

        main_layout.addWidget(self.tabs)

        # ─── ۴. پنل سرجمع ───
        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_layout = QHBoxLayout(summary_frame)

        self.lbl_open_pnl = QLabel("🟢 سود/زیان موقعیت‌های باز: 0 تومان")
        self.lbl_open_pnl.setStyleSheet(COLOR_NEUTRAL)

        self.lbl_realized_pnl = QLabel(
            "🔵 سود/زیان موقعیت‌های بسته‌شده: 0 تومان")
        self.lbl_realized_pnl.setStyleSheet(COLOR_NEUTRAL)

        self.lbl_total_pnl = QLabel("📈 مجموع کل سود/زیان: 0 تومان")
        self.lbl_total_pnl.setStyleSheet(COLOR_NEUTRAL)

        summary_layout.addWidget(self.lbl_open_pnl)
        summary_layout.addWidget(self.lbl_realized_pnl)
        summary_layout.addWidget(self.lbl_total_pnl)
        main_layout.addWidget(summary_frame)

        self.on_tab_changed(0)

    def _build_table_tab(self) -> QTableWidget:
        """ساخت جدول استاندارد برای تب‌ها"""
        table = QTableWidget(0, self.N_COLS)
        table.setHorizontalHeaderLabels([
            "شناسه",
            "نام استراتژی",
            "کارگزاری",
            "نماد پایه",
            "تاریخ اجرا",
            "تاریخ سررسید",
            "لنگه‌ها",
            "هزینه ورود (تومان)",
            "سود انتظاری",
            "سود/زیان لایو",
            "وضعیت",
        ])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)

        # ✅ فعال کردن سورت
        table.setSortingEnabled(True)

        # ✅ وسط‌چین کردن هدرها
        header.setDefaultAlignment(Qt.AlignCenter)

        # ─── تنظیم عرض ستون‌ها ───
        table.setColumnWidth(self.COL_ID, 75)
        table.setColumnWidth(self.COL_STRATEGY, 125)
        table.setColumnWidth(self.COL_BROKER, 105)
        table.setColumnWidth(self.COL_UNDERLYING, 80)
        table.setColumnWidth(self.COL_EXEC_DATE, 85)
        table.setColumnWidth(self.COL_EXPIRY_DATE, 85)
        table.setColumnWidth(self.COL_NET_COST, 125)
        table.setColumnWidth(self.COL_TARGET_ROI, 75)
        table.setColumnWidth(self.COL_LIVE_PNL, 140)
        table.setColumnWidth(self.COL_STATUS, 95)

        # ✅ ستون لنگه‌ها کشیده شود
        header.setSectionResizeMode(self.COL_LEGS, QHeaderView.Stretch)

        # ✅ فعال کردن انتخاب چندتایی (Ctrl / Shift)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setSelectionBehavior(QTableWidget.SelectRows)

        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setWordWrap(False)
        table.verticalHeader().setDefaultSectionSize(28)

        # ✅ مخفی کردن ستون شناسه
        table.setColumnHidden(self.COL_ID, True)

        return table

    # =====================================================
    # تب‌بندی
    # =====================================================

    def on_tab_changed(self, index: int):
        is_pending = (index == 1)
        self.btn_cash_settle.setEnabled(is_pending)
        self.btn_exercise.setEnabled(is_pending)
        self.btn_manual_close.setEnabled(is_pending)
        self.btn_default.setEnabled(is_pending)

    def _update_tab_badges(self):
        pending_count = len(self._get_pending_positions())
        tab_bar = self.tabs.tabBar()

        if pending_count > 0:
            self.tabs.setTabText(
                1, f"⚠️ نیازمند تعیین تکلیف ({pending_count})")
            tab_bar.setTabTextColor(1, QColor("red"))
        else:
            self.tabs.setTabText(1, "⚠️ نیازمند تعیین تکلیف")
            tab_bar.setTabTextColor(1, QColor("gray"))

    # =====================================================
    # فیلترها
    # =====================================================

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
        return [p for p in self.positions if self._is_pending_settlement(p)]

    def _get_history_positions(self) -> List[StrategyPosition]:
        return [
            p for p in self.positions
            if p.status != PositionStatus.OPEN
        ]

    # =====================================================
    # دریافت snapshot
    # =====================================================

    def _get_market_snapshot(self):
        try:
            from data.manager import get_market_snapshot
            if self._market_snapshot is not None:
                return self._market_snapshot
            self._market_snapshot = get_market_snapshot(
                use_cache=True, force_refresh=False)
            return self._market_snapshot
        except Exception as e:
            print(f"[PositionSaver] Snapshot failed: {e}")
            return None

    def _invalidate_snapshot(self):
        self._market_snapshot = None

    # =====================================================
    # اسلات‌های ترد
    # =====================================================

    def toggle_auto_refresh(self, checked: bool):
        self.monitor_thread.set_auto_refresh(checked)

    def change_timer_interval(self, value: int):
        self.lbl_minutes.setText(f"({value / 60.0:.1f} دقیقه)")
        self.monitor_thread.set_interval(value)

    def manual_refresh_data(self):
        self.monitor_thread.trigger_manual_refresh()

    @Slot(dict)
    def on_prices_updated(self, payload: dict):
        prices = payload.get("prices", {})
        contract_sizes = payload.get("contract_sizes", {})

        for pos in self.positions:
            if pos.status != PositionStatus.OPEN:
                continue
            for leg in pos.legs:
                if leg.symbol in prices:
                    leg.current_price = prices[leg.symbol]
                if leg.symbol in contract_sizes and leg.is_option:
                    leg.contract_size = contract_sizes[leg.symbol]
            if pos.underlying_symbol in prices:
                pos.underlying_price = prices[pos.underlying_symbol]

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()

    @Slot(list)
    def on_alerts_found(self, alerts: list):
        for alert in alerts:
            success = self.monitor_thread.send_bale_alert(alert)
            if success:
                for pos in self.positions:
                    if pos.position_id == alert["position_id"]:
                        pos.alert_sent = True
                        break
        if alerts:
            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()

    @Slot(list)
    def on_expired_found(self, position_ids: list):
        new_ids = [pid for pid in position_ids
                   if pid not in self._expired_alerted]
        if not new_ids:
            return

        self._expired_alerted.update(new_ids)

        msg = (
            f"⚠️ شما {len(new_ids)} موقعیت منقضی‌شده دارید:\n\n"
            + "\n".join(f"  • {pid}" for pid in new_ids)
            + "\n\nاین موقعیت‌ها دیگر قیمت لایو ندارند.\n"
            "برای ثبت تسویه به تب «نیازمند تعیین تکلیف» بروید."
        )
        QMessageBox.information(self, "موقعیت‌های منقضی", msg)
        self._update_tab_badges()

    @Slot(dict)
    def on_connection_status(self, status: dict):
        ok = status.get("ok", False)
        message = status.get("message", "")
        timestamp = status.get("timestamp")

        ts_str = timestamp.strftime("%H:%M:%S") if timestamp else "—"

        if ok:
            self._last_success_time = timestamp
            self.lbl_connection.setText(f"🟢 {ts_str} — {message}")
            self.lbl_connection.setStyleSheet(
                "color: #2E7D32; font-weight: bold; padding: 0 8px;")
        else:
            last_ok = self._last_success_time.strftime("%H:%M:%S") \
                if self._last_success_time else "—"
            self.lbl_connection.setText(
                f"🔴 {ts_str} — {message} (آخرین موفق: {last_ok})")
            self.lbl_connection.setStyleSheet(
                "color: #C62828; font-weight: bold; padding: 0 8px;")

    # =====================================================
    # بارگذاری و رفرش
    # =====================================================

    def load_data(self):
        self.positions = self.storage.load_positions()
        self.refresh_all_tabs()

    def refresh_all_tabs(self):
        self._populate_table(self.tab_active, self._get_active_positions())
        self._populate_table(self.tab_pending, self._get_pending_positions())
        self._populate_table(self.tab_history, self._get_history_positions())
        self._update_tab_badges()
        self._update_summary()

    # =====================================================
    # کمکی: ساخت آیتم‌ها
    # =====================================================

    @staticmethod
    def _make_text_item(text: str) -> SortableItem:
        item = SortableItem(str(text), str(text))
        item.setToolTip(str(text))
        return item

    @staticmethod
    def _make_number_item(display_text: str, value: float) -> SortableItem:
        item = SortableItem(display_text, float(value))
        item.setToolTip(display_text)
        return item

    def _populate_table(
        self, table: QTableWidget, positions: List[StrategyPosition]
    ):
        table.setSortingEnabled(False)

        selected_id = None
        curr_row = table.currentRow()
        if curr_row >= 0 and table.item(curr_row, self.COL_ID):
            selected_id = table.item(curr_row, self.COL_ID).text()

        table.setRowCount(0)

        for idx, pos in enumerate(positions):
            row = table.rowCount()
            table.insertRow(row)

            net_cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
            live_pnl, live_roi = PositionPnLCalculator.calculate_live_pnl(pos)
            realized_pnl, realized_roi = \
                PositionPnLCalculator.calculate_realized_pnl(pos)

            legs_str = " | ".join([
                f"{l.leg_type.label_fa}: {l.symbol}"
                for l in pos.legs
            ])

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
            table.setItem(row, self.COL_LEGS,
                          self._make_text_item(legs_str))
            table.setItem(row, self.COL_NET_COST,
                          self._make_number_item(
                              f"{int(net_cost):,}", net_cost))
            table.setItem(row, self.COL_TARGET_ROI,
                          self._make_number_item(
                              f"{pos.target_roi_maturity:.1f}%",
                              pos.target_roi_maturity))

            if pos.status == PositionStatus.OPEN:
                if self._is_pending_settlement(pos):
                    pnl_text = "⚠️ منقضی - لطفاً تسویه کنید"
                    pnl_item = SortableItem(pnl_text, -999999999.0)
                    pnl_item.setToolTip(pnl_text)
                    pnl_item.setForeground(QColor("#B85C00"))
                else:
                    pnl_text = f"{int(live_pnl):,} ({live_roi:+.1f}%)"
                    pnl_item = SortableItem(pnl_text, float(live_pnl))
                    pnl_item.setToolTip(pnl_text)
                    if live_pnl > 0:
                        pnl_item.setForeground(QColor("green"))
                    elif live_pnl < 0:
                        pnl_item.setForeground(QColor("red"))
            else:
                pnl_text = f"{int(realized_pnl):,} ({realized_roi:+.1f}%)"
                pnl_item = SortableItem(pnl_text, float(realized_pnl))
                pnl_item.setToolTip(pnl_text)
                if realized_pnl > 0:
                    pnl_item.setForeground(QColor("green"))
                elif realized_pnl < 0:
                    pnl_item.setForeground(QColor("red"))
            table.setItem(row, self.COL_LIVE_PNL, pnl_item)

            status_text = pos.status.label_fa
            if self._is_pending_settlement(pos):
                status_text = "⚠️ منقضی (تعیین تکلیف نشده)"
            table.setItem(row, self.COL_STATUS,
                          self._make_text_item(status_text))

            bg = self._get_row_background(pos, idx)
            if bg is not None:
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        item.setBackground(bg)

            if selected_id and str(pos.position_id) == selected_id:
                table.selectRow(row)

        table.setSortingEnabled(True)

    def _get_row_background(
        self, pos: StrategyPosition, idx: int
    ) -> Optional[QColor]:
        if pos.status == PositionStatus.OPEN:
            if self._is_pending_settlement(pos):
                return QColor(255, 235, 200)
        if pos.status == PositionStatus.CLOSED:
            return QColor(245, 245, 245)
        if pos.status == PositionStatus.EXERCISED:
            return QColor(220, 235, 255)
        if pos.status == PositionStatus.CASH_SETTLED:
            return QColor(225, 245, 225)

        # ✅ رنگ‌های نکول
        if pos.status == PositionStatus.DEFAULTED:
            # طرف مقابل نکول کرده — من ذی‌نفع
            return QColor(255, 220, 220)
        if pos.status == PositionStatus.YOU_DEFAULTED:
            # من نکول کرده‌ام — متضرر
            return QColor(255, 200, 200)

        if idx % 2 == 1:
            return ROW_COLOR_ALT
        return ROW_COLOR_NORMAL

    # =====================================================
    # پنل سرجمع
    # =====================================================

    def _set_summary_label(
        self, label: QLabel, prefix: str, value: float
    ):
        label.setText(f"{prefix}: {int(value):,} تومان")

        if value > 0:
            label.setStyleSheet(COLOR_PROFIT)
        elif value < 0:
            label.setStyleSheet(COLOR_LOSS)
        else:
            label.setStyleSheet(COLOR_NEUTRAL)

    def _update_summary(self):
        sum_open_pnl = 0.0
        sum_realized_pnl = 0.0

        for pos in self.positions:
            if pos.status == PositionStatus.OPEN:
                live_pnl, _ = PositionPnLCalculator.calculate_live_pnl(pos)
                sum_open_pnl += live_pnl
            else:
                realized_pnl, _ = \
                    PositionPnLCalculator.calculate_realized_pnl(pos)
                sum_realized_pnl += realized_pnl

        self._set_summary_label(
            self.lbl_open_pnl,
            "🟢 سود/زیان موقعیت‌های باز",
            sum_open_pnl)

        self._set_summary_label(
            self.lbl_realized_pnl,
            "🔵 سود/زیان موقعیت‌های بسته‌شده",
            sum_realized_pnl)

        self._set_summary_label(
            self.lbl_total_pnl,
            "📈 مجموع کل سود/زیان",
            sum_open_pnl + sum_realized_pnl)

    # =====================================================
    # عملیات CRUD
    # =====================================================

    def _current_table(self) -> QTableWidget:
        return self.tabs.currentWidget()

    def _current_positions(self) -> List[StrategyPosition]:
        idx = self.tabs.currentIndex()
        if idx == 0:
            return self._get_active_positions()
        if idx == 1:
            return self._get_pending_positions()
        return self._get_history_positions()

    def _get_selected_position(self) -> Optional[StrategyPosition]:
        """دریافت موقعیت انتخاب‌شده (اولین) بر اساس شناسه"""
        positions = self._get_selected_positions()
        return positions[0] if positions else None

    def _get_selected_positions(self) -> List[StrategyPosition]:
        """
        دریافت همه موقعیت‌های انتخاب‌شده (چندتایی).
        از شناسه استفاده می‌کند چون سورت ممکن است اندیس‌ها را جابجا کند.
        """
        table = self._current_table()

        # جمع‌آوری اندیس سطرهای انتخاب‌شده
        selected_rows = sorted(set(
            idx.row() for idx in table.selectedIndexes()
        ))

        positions = []
        seen_ids = set()
        for row in selected_rows:
            id_item = table.item(row, self.COL_ID)
            if id_item is None:
                continue
            pid = id_item.text()
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            for pos in self.positions:
                if pos.position_id == pid:
                    positions.append(pos)
                    break

        return positions

    def add_position(self):
        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(self, snapshot=snapshot)
        try:
            if dlg.exec():
                self.positions.append(dlg.position)
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
        finally:
            dlg.deleteLater()

    def edit_position(self):
        pos = self._get_selected_position()
        if pos is None:
            QMessageBox.warning(
                self, "خطا", "لطفا یک موقعیت را انتخاب کنید.")
            return

        snapshot = self._get_market_snapshot()
        dlg = PositionEditDialog(self, pos, snapshot=snapshot)
        try:
            if dlg.exec():
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
        finally:
            dlg.deleteLater()

    def delete_position(self):
        pos = self._get_selected_position()
        if pos is None:
            return
        if QMessageBox.question(
            self, "تایید",
            f"آیا از حذف موقعیت {pos.position_id} اطمینان دارید؟"
        ) == QMessageBox.Yes:
            self.positions = [
                p for p in self.positions if p.position_id != pos.position_id
            ]
            self.storage.save_positions(self.positions)
            self.refresh_all_tabs()

    def import_from_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل اکسل کارگزاری", "",
            "Excel Files (*.xlsx *.xls)")
        if file_path:
            imported = PositionStorage.parse_broker_excel(file_path)
            if imported:
                self.positions.extend(imported)
                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()
                QMessageBox.information(
                    self, "موفقیت",
                    f"تعداد {len(imported)} موقعیت با موفقیت بارگذاری شد.")

    # =====================================================
    # ارسال موقعیت‌ها به بله
    # =====================================================

    def send_positions_to_bale(self):
        """
        ارسال موقعیت‌های انتخاب‌شده به بله.
        هر موقعیت در یک پیام جداگانه ارسال می‌شود.
        """
        positions = self._get_selected_positions()

        if not positions:
            QMessageBox.warning(
                self, "خطا",
                "لطفاً حداقل یک موقعیت را از جدول انتخاب کنید.\n\n"
                "💡 با نگه‌داشتن کلید Ctrl یا Shift می‌توانید "
                "چند موقعیت را همزمان انتخاب کنید.")
            return

        # چک تنظیمات بله
        if not self.monitor_thread.notifier.is_configured:
            QMessageBox.warning(
                self, "خطا",
                "تنظیمات بله کامل نیست.\n\n"
                "لطفاً bot_token و chat_id را در user_settings.json "
                "بررسی کنید.")
            return

        # تأیید کاربر
        n = len(positions)
        if n == 1:
            confirm_msg = (
                f"آیا گزارش موقعیت زیر به بله ارسال شود؟\n\n"
                f"شناسه: {positions[0].position_id}\n"
                f"استراتژی: {positions[0].strategy_name}"
            )
        else:
            ids = "\n".join(f"  • {p.position_id} ({p.strategy_name})"
                            for p in positions[:10])
            if n > 10:
                ids += f"\n  ... و {n - 10} مورد دیگر"
            confirm_msg = (
                f"آیا گزارش {n} موقعیت زیر به بله ارسال شود؟\n\n"
                f"{ids}\n\n"
                f"⚠️ هر موقعیت در یک پیام جداگانه ارسال می‌شود."
            )

        reply = QMessageBox.question(
            self, "تأیید ارسال",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # ارسال به ترتیب
        success_count = 0
        failed_ids = []

        for pos in positions:
            try:
                ok = self.monitor_thread.send_position_report(pos)
                if ok:
                    success_count += 1
                else:
                    failed_ids.append(pos.position_id)
            except Exception as e:
                print(f"[Bale] Error sending {pos.position_id}: {e}")
                failed_ids.append(pos.position_id)

        # نمایش نتیجه
        if success_count == n:
            QMessageBox.information(
                self, "موفقیت",
                f"✅ همه {success_count} موقعیت با موفقیت به بله "
                f"ارسال شدند.")
        elif success_count > 0:
            QMessageBox.warning(
                self, "نتیجه ارسال",
                f"✅ {success_count} از {n} موقعیت با موفقیت ارسال شد.\n\n"
                f"❌ موارد ناموفق:\n"
                + "\n".join(f"  • {pid}" for pid in failed_ids))
        else:
            QMessageBox.critical(
                self, "خطا",
                f"❌ ارسال هیچ‌کدام از {n} موقعیت موفق نبود.\n\n"
                "لطفاً لاگ‌های برنامه را بررسی کنید.")

    # =====================================================
    # ثبت نکول CALL
    # =====================================================

    def register_default(self):
        """ثبت نکول CALL در روز سررسید"""
        pos = self._get_selected_position()
        if pos is None:
            QMessageBox.warning(
                self, "خطا", "لطفاً یک موقعیت را انتخاب کنید.")
            return

        # بررسی وضعیت
        if pos.status != PositionStatus.OPEN:
            QMessageBox.warning(
                self, "خطا",
                "فقط موقعیت‌های باز می‌توانند نکول ثبت کنند.")
            return

        # بررسی CALL
        call_legs = [l for l in pos.legs if l.is_call]
        if not call_legs:
            QMessageBox.warning(
                self, "خطا",
                "این موقعیت هیچ لگ CALL ندارد.\n"
                "نکول فقط برای اختیار خرید (CALL) معنا دارد.")
            return

        # بررسی تاریخ سررسید
        if not pos.expiry_date:
            QMessageBox.warning(
                self, "خطا", "این موقعیت تاریخ سررسید ندارد.")
            return

        s = str(pos.expiry_date).strip()
        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
        if not m:
            QMessageBox.warning(self, "خطا", "تاریخ سررسید نامعتبر است.")
            return

        try:
            expiry = jdatetime.date(
                int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception as e:
            QMessageBox.warning(self, "خطا", f"خطا در تاریخ: {e}")
            return

        today = jdatetime.date.today()
        if expiry != today:
            days_diff = (expiry - today).days
            if days_diff > 0:
                msg = f"⏳ {days_diff} روز تا سررسید باقی است."
            else:
                msg = f"⏰ {abs(days_diff)} روز از سررسید گذشته."
            QMessageBox.warning(
                self, "خطا",
                f"نکول فقط در روز سررسید قابل ثبت است.\n\n"
                f"تاریخ سررسید: {pos.expiry_date}\n"
                f"تاریخ امروز: {today.strftime('%Y/%m/%d')}\n\n{msg}")
            return

        # باز کردن دیالوگ
        dlg = DefaultSettlementDialog(self, pos)
        try:
            if dlg.exec():
                result = dlg.get_result()
                if not result:
                    return

                S_T = result["S_T"]
                exercise_rate = result.get("exercise_rate", 0.0005)

                has_buy = False
                has_sell = False

                for leg in pos.legs:
                    if not leg.is_call:
                        continue

                    r = PositionPnLCalculator.calculate_call_default(
                        leg, S_T, exercise_rate=exercise_rate)
                    if not r["valid"]:
                        continue

                    leg.is_defaulted = True
                    leg.default_penalty = r["penalty"]
                    leg.default_payment = r["payment"]
                    leg.settlement_price = S_T
                    leg.close_price = r["effective_price"]
                    # کارمزد اعمال (فقط برای Long Call)
                    leg.close_fee = r["exercise_fee"]

                    if leg.leg_type == LegType.BUY:
                        has_buy = True
                    else:
                        has_sell = True

                # تعیین وضعیت
                if has_buy and not has_sell:
                    pos.status = PositionStatus.DEFAULTED
                elif has_sell and not has_buy:
                    pos.status = PositionStatus.YOU_DEFAULTED
                else:
                    # ترکیبی — چون خریدار ذی‌نفع است
                    pos.status = PositionStatus.DEFAULTED

                pos.close_date = today.strftime("%Y/%m/%d")

                self.storage.save_positions(self.positions)
                self.refresh_all_tabs()

                QMessageBox.information(
                    self, "موفقیت",
                    f"نکول CALL برای موقعیت {pos.position_id} ثبت شد.\n\n"
                    f"S_T: {int(S_T):,} ریال\n"
                    f"خالص نهایی: {int(result['net']):,} ریال")
        finally:
            dlg.deleteLater()

    # =====================================================
    # خروجی به اکسل
    # =====================================================

    def _positions_to_dataframe(
        self, positions: List[StrategyPosition]
    ) -> pd.DataFrame:
        rows = []
        for pos in positions:
            net_cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
            live_pnl, live_roi = PositionPnLCalculator.calculate_live_pnl(pos)
            realized_pnl, realized_roi = \
                PositionPnLCalculator.calculate_realized_pnl(pos)

            legs_str = " | ".join([
                f"{l.leg_type.label_fa}: {l.symbol} "
                f"(تعداد: {l.quantity}, ورود: {int(l.entry_price):,})"
                for l in pos.legs
            ])

            if pos.status == PositionStatus.OPEN:
                pnl_value = live_pnl
                pnl_roi = live_roi
            else:
                pnl_value = realized_pnl
                pnl_roi = realized_roi

            rows.append({
                "Position_ID": pos.position_id,
                "Strategy": pos.strategy_name,
                "Broker": pos.broker_name or "—",
                "Underlying": pos.underlying_symbol,
                "Execution_Date": pos.execution_date,
                "Expiry_Date": pos.expiry_date,
                "Legs": legs_str,
                "Legs_Count": len(pos.legs),
                "Net_Entry_Cost": int(net_cost),
                "Target_ROI_Pct": pos.target_roi_maturity,
                "PnL": int(pnl_value),
                "PnL_ROI_Pct": round(pnl_roi, 2),
                "Alert_Target_ROI_Pct": pos.alert_target_roi,
                "Status": pos.status.value,
                "Close_Date": pos.close_date or "",
                "Notes": pos.notes or "",
            })

        return pd.DataFrame(rows)

    def export_to_excel(self):
        if not self.positions:
            QMessageBox.warning(
                self, "خطا", "هیچ موقعیتی برای خروجی وجود ندارد.")
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
            active_positions = (
                self._get_active_positions() + self._get_pending_positions()
            )
            history_positions = self._get_history_positions()

            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                if active_positions:
                    df_active = self._positions_to_dataframe(active_positions)
                    df_active.to_excel(
                        writer, sheet_name="Active_Positions", index=False)
                else:
                    pd.DataFrame(
                        columns=["پیام"]
                    ).to_excel(
                        writer, sheet_name="Active_Positions", index=False)

                if history_positions:
                    df_history = self._positions_to_dataframe(
                        history_positions)
                    df_history.to_excel(
                        writer, sheet_name="Closed_Positions", index=False)
                else:
                    pd.DataFrame(
                        columns=["پیام"]
                    ).to_excel(
                        writer, sheet_name="Closed_Positions", index=False)

            QMessageBox.information(
                self, "موفقیت",
                f"فایل اکسل با موفقیت ذخیره شد:\n{file_path}\n\n"
                f"• Active_Positions: {len(active_positions)} موقعیت\n"
                f"• Closed_Positions: {len(history_positions)} موقعیت")

        except ImportError as e:
            QMessageBox.critical(
                self, "خطا",
                f"کتابخانه openpyxl نصب نیست.\n\n"
                f"برای نصب: pip install openpyxl\n\n"
                f"جزئیات: {e}")
        except Exception as e:
            QMessageBox.critical(
                self, "خطا",
                f"خطا در ذخیره فایل اکسل:\n{e}")

    # =====================================================
    # اقدامات سریع
    # =====================================================

    def settle_cash(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            QMessageBox.warning(
                self, "خطا",
                "لطفاً یک موقعیت منقضی از تب «نیازمند تعیین تکلیف» انتخاب کنید.")
            return

        amount, ok = QInputDialog.getDouble(
            self, "تسویه نقدی",
            f"مبلغ خالص دریافتی/پرداختی (تومان):\n"
            f"(مثبت = دریافت، منفی = پرداخت)\n\n"
            f"موقعیت: {pos.position_id} — {pos.strategy_name}",
            value=0.0, min=-1e12, max=1e12, decimals=0,
        )
        if not ok:
            return

        target_leg = None
        for leg in pos.legs:
            if leg.quantity > 0 and leg.effective_contract_size > 0:
                target_leg = leg
                break

        if target_leg:
            denom = target_leg.quantity * target_leg.effective_contract_size
            target_leg.close_price = (amount / denom) if denom > 0 else 0.0
            target_leg.close_fee = 0.0

        pos.status = PositionStatus.CASH_SETTLED
        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        QMessageBox.information(
            self, "موفقیت",
            f"موقعیت {pos.position_id} به وضعیت «تسویه نقدی» تغییر کرد.")

    def settle_exercise(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            QMessageBox.warning(
                self, "خطا",
                "لطفاً یک موقعیت منقضی انتخاب کنید.")
            return

        reply = QMessageBox.question(
            self, "تأیید اعمال فیزیکی",
            f"آیا اعمال فیزیکی موقعیت {pos.position_id} را تأیید می‌کنید؟\n\n"
            f"برای آپشن‌های در سود (ITM)، قیمت خروج = قیمت اعمال.\n"
            f"برای آپشن‌های خارج از سود (OTM)، قیمت خروج = 0.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for leg in pos.legs:
            if not leg.is_option:
                continue
            S = pos.underlying_price or 0.0
            K = leg.strike_price or 0.0
            if leg.is_call:
                is_itm = S > K
            else:
                is_itm = S < K
            leg.close_price = float(K) if is_itm else 0.0
            leg.close_fee = 0.0

        pos.status = PositionStatus.EXERCISED
        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        QMessageBox.information(
            self, "موفقیت",
            f"موقعیت {pos.position_id} به وضعیت «اعمال‌شده» تغییر کرد.")

    def close_manually(self):
        pos = self._get_selected_position()
        if pos is None or not self._is_pending_settlement(pos):
            QMessageBox.warning(
                self, "خطا",
                "لطفاً یک موقعیت منقضی انتخاب کنید.")
            return

        for leg in pos.legs:
            default_price = leg.current_price or leg.entry_price
            price, ok = QInputDialog.getDouble(
                self, "قیمت خروج",
                f"قیمت خروج برای {leg.symbol} "
                f"({leg.leg_type.label_fa}):",
                value=default_price,
                min=0.0, max=1e12, decimals=0,
            )
            if not ok:
                return
            leg.close_price = price
            leg.close_fee = PositionPnLCalculator.calculate_leg_close_fee(
                leg, price)

        pos.status = PositionStatus.CLOSED
        pos.close_date = jdatetime.date.today().strftime("%Y/%m/%d")

        self.storage.save_positions(self.positions)
        self.refresh_all_tabs()
        QMessageBox.information(
            self, "موفقیت",
            f"موقعیت {pos.position_id} به وضعیت «بسته‌شده» تغییر کرد.")