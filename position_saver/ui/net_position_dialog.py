# position_saver/ui/net_position_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ نمایش ترتیب زمانی معاملات یک نماد + موقعیت خالص.
"""

import logging
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QRadioButton, QDialogButtonBox, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from position_saver.theme import (
    Theme, fmt_money, fmt_int, set_kind, set_tone,
)
from position_saver.importer.net_position import (
    compute_net_position, NetPositionResult,
)


logger = logging.getLogger("PositionSaver.UI.NetPosition")


class NetPositionDialog(QDialog):
    """
    دیالوگ تحلیل معاملات یک نماد.

    استفاده:
        dlg = NetPositionDialog(parent, trades=[...], symbol="ضفزر505")
        dlg.exec()
    """

    def __init__(self, parent=None, trades: Optional[List] = None,
                 symbol: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"📊 تحلیل معاملات — {symbol}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(900, 650)

        self.trades = trades or []
        self.symbol = symbol
        self._result: Optional[NetPositionResult] = None

        self._build_ui()
        self._recompute()

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(
            f"📊 تحلیل معاملات نماد «{self.symbol}» "
            f"({len(self.trades)} معامله)")
        set_tone(header, "primary", big=True)
        layout.addWidget(header)

        # ─── جدول ───
        table_group = QGroupBox("ترتیب زمانی معاملات")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "#", "تاریخ", "ساعت", "سمت",
            "تعداد", "قیمت", "جفت‌شده با", "وضعیت",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 120)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)

        table_layout.addWidget(self.table)
        layout.addWidget(table_group, 1)

        # ─── انتخاب روش ───
        method_group = QGroupBox("روش جفت‌یابی")
        method_layout = QHBoxLayout(method_group)

        self.radio_fifo = QRadioButton("FIFO (اول-ورود، اول-خروج)")
        self.radio_lifo = QRadioButton("LIFO (آخر-ورود، اول-خروج)")
        self.radio_fifo.setChecked(True)

        self.radio_fifo.toggled.connect(self._on_method_changed)
        self.radio_lifo.toggled.connect(self._on_method_changed)

        method_layout.addWidget(self.radio_fifo)
        method_layout.addWidget(self.radio_lifo)
        method_layout.addStretch()
        layout.addWidget(method_group)

        # ─── خلاصه ───
        self.lbl_summary = QLabel("—")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet(
            f"padding: 10px; background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; "
            f"border-radius: 6px; font-size: 13px;")
        layout.addWidget(self.lbl_summary)

        # ─── دکمه ───
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Close).setText("بستن")
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ═══════════════════════════════════════════════
    # محاسبه
    # ═══════════════════════════════════════════════

    def _on_method_changed(self):
        self._recompute()

    def _recompute(self):
        method = "fifo" if self.radio_fifo.isChecked() else "lifo"
        self._result = compute_net_position(self.trades, method=method)
        self._refresh_table()
        self._refresh_summary()

    def _refresh_table(self):
        if not self._result:
            return

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for i, match in enumerate(self._result.matches, 1):
            t = match.trade
            row = self.table.rowCount()
            self.table.insertRow(row)

            item = QTableWidgetItem(str(i))
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item)

            self.table.setItem(row, 1,
                QTableWidgetItem(t.raw_date or "—"))
            self.table.setItem(row, 2,
                QTableWidgetItem(t.raw_time or "—"))

            # ✅ FIX: برچسب واضح‌تر
            side_item = QTableWidgetItem(t.side.label_fa)
            side_item.setTextAlignment(Qt.AlignCenter)
            side_item.setForeground(
                QColor(Theme.PROFIT if t.is_buy else Theme.LOSS))
            self.table.setItem(row, 3, side_item)

            qty_item = QTableWidgetItem(fmt_int(t.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, qty_item)

            pr_item = QTableWidgetItem(fmt_money(t.price))
            pr_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, pr_item)

            if match.matched_with:
                match_text = ", ".join(match.matched_with[:3])
                if len(match.matched_with) > 3:
                    match_text += f" +{len(match.matched_with) - 3}"
            else:
                match_text = "—"
            match_item = QTableWidgetItem(match_text)
            match_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, match_item)

            status_text, status_color = self._get_status_label(match)
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(status_color))
            self.table.setItem(row, 7, status_item)

        self.table.setSortingEnabled(True)

    def _get_status_label(self, match) -> tuple:
        """برچسب و رنگ وضعیت"""
        status = match.status

        # ✅ FIX: برچسب‌های واضح‌تر
        if status in ("matched_buy", "matched_sell"):
            return (f"🟢 جفت‌شده ({match.matched_quantity})",
                    Theme.PROFIT)
        elif status == "open_buy":
            return (f"🟡 BUY باز ({match.remaining_quantity})",
                    Theme.WARN)
        elif status == "orphan_sell":
            return (f"🔴 SELL بدون BUY ({match.remaining_quantity})",
                    Theme.LOSS)
        else:
            return "⚪ نامشخص", Theme.MUTED

    def _refresh_summary(self):
        if not self._result:
            return

        r = self._result
        text_parts = []
        text_parts.append("📊 <b>خلاصه‌ی موقعیت</b>")
        text_parts.append("")
        text_parts.append(f"• معاملات کل: <b>{r.total_trades}</b>")
        text_parts.append(f"• جفت‌شده: <b>{r.matched_trades}</b>")

        if r.open_buys > 0:
            text_parts.append(
                f"• BUY باز (Long): <b>{r.open_buys}</b>")
        if r.open_sells > 0:
            text_parts.append(
                f"• SELL بدون BUY (Short/Orphan): "
                f"<b>{r.open_sells}</b>")

        text_parts.append("")

        if (r.net_position == 0
                and r.open_buys == 0 and r.open_sells == 0):
            text_parts.append(
                "🎯 <b>موقعیت فعلی: کاملاً بسته</b>")
        elif r.net_position > 0:
            text_parts.append(
                f"🎯 <b>موقعیت فعلی: {r.net_position} باز "
                f"(Long)</b>")
        elif r.net_position < 0:
            text_parts.append(
                f"🎯 <b>موقعیت فعلی: {abs(r.net_position)} باز "
                f"(Short)</b>")
        else:
            text_parts.append("⚠️ <b>موقعیت فعلی: ناهمگون</b>")

        self.lbl_summary.setText("<br>".join(text_parts))


__all__ = ["NetPositionDialog"]