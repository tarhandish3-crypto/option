# position_saver/ui/split_position_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ شکستن موقعیت (Position Split).

کاربرد:
    کاربر یک موقعیت با qty>1 را به چند قطعه می‌شکند
    تا بتواند هر قطعه را در گروه جداگانه‌ای قرار دهد.

مثال:
    3 عدد ضفزر505 خرید → یکی آفست، یکی آفست، یکی Bull Call Spread
"""

from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QPushButton, QLabel, QMessageBox,
    QDialogButtonBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QAbstractSpinBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from position_saver.theme import (
    Theme, fmt_money, fmt_int, set_kind, set_tone,
)
from position_saver.models import StrategyPosition


# ═══════════════════════════════════════════════════
# استاندارد استراتژی‌های split
# ═══════════════════════════════════════════════════

SPLIT_REASONS = [
    ("", "— (بدون تعیین)"),
    ("Long Offset", "آفست لانگ"),
    ("Short Offset", "آفست شورت"),
    ("Single Trade", "معامله‌ی تک"),
    ("Bull Call Spread", "بول کال اسپرد"),
    ("Bear Put Spread", "بیر پوت اسپرد"),
    ("Custom", "سفارشی"),
]


# ═══════════════════════════════════════════════════
# SplitPositionDialog
# ═══════════════════════════════════════════════════

class SplitPositionDialog(QDialog):
    """
    دیالوگ شکستن موقعیت.

    استفاده:
        dlg = SplitPositionDialog(parent, position=pos)
        if dlg.exec():
            quantities = dlg.get_quantities()
            reasons = dlg.get_reasons()
    """

    def __init__(self, parent=None,
                 position: Optional[StrategyPosition] = None):
        super().__init__(parent)
        self.setWindowTitle("🔨 شکستن موقعیت")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(680, 520)

        self.position = position
        self._quantities: List[int] = []
        self._reasons: List[str] = []

        self._build_ui()
        self._load_default()

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── اطلاعات موقعیت ───
        info_group = QGroupBox("📋 موقعیت اصلی")
        info_layout = QFormLayout(info_group)

        total_qty = (
            self.position.legs[0].quantity
            if self.position and self.position.legs else 0
        )

        info_layout.addRow(
            "شناسه:",
            QLabel(self.position.position_id
                   if self.position else "—"))
        info_layout.addRow(
            "نماد:",
            QLabel(self.position.underlying_symbol
                   if self.position else "—"))
        info_layout.addRow(
            "سمت:",
            QLabel(self.position.legs[0].leg_type.label_fa
                   if self.position and self.position.legs
                   else "—"))
        info_layout.addRow(
            "تعداد کل:",
            QLabel(fmt_int(total_qty)))
        info_layout.addRow(
            "قیمت ورود:",
            QLabel(fmt_money(
                self.position.legs[0].entry_price
                if self.position and self.position.legs else 0)))

        layout.addWidget(info_group)

        # ─── جدول قطعات ───
        parts_group = QGroupBox("🔨 قطعات")
        parts_layout = QVBoxLayout(parts_group)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "#", "تعداد", "استراتژی (اختیاری)", "اقدام",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 260)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().setVisible(False)
        self.table.setVisible(False)
        parts_layout.addWidget(self.table)

        # ─── نوار ابزار قطعات ───
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_add = QPushButton("➕ افزودن قطعه")
        self.btn_add.clicked.connect(self._add_piece)
        bar.addWidget(self.btn_add)

        self.btn_auto_split = QPushButton("⚡ تقسیم مساوی")
        self.btn_auto_split.clicked.connect(self._auto_split)
        bar.addWidget(self.btn_auto_split)

        bar.addStretch()

        self.lbl_sum = QLabel("—")
        set_tone(self.lbl_sum, "muted")
        bar.addWidget(self.lbl_sum)

        parts_layout.addLayout(bar)
        layout.addWidget(parts_group, 1)

        # ─── راهنما ───
        hint = QLabel(
            "💡 مجموع قطعات باید برابر تعداد کل باشد.\n"
            "پس از Split، هر قطعه یک Position مستقل می‌شود "
            "و می‌توانید هر کدام را در گروه جداگانه قرار دهید.")
        set_tone(hint, "muted")
        layout.addWidget(hint)

        # ─── دکمه‌ها ───
        self.btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.button(QDialogButtonBox.Ok).setText("✅ تأیید Split")
        self.btns.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        set_kind(self.btns.button(QDialogButtonBox.Ok), "primary")
        self.btns.accepted.connect(self._on_accept)
        self.btns.rejected.connect(self.reject)
        layout.addWidget(self.btns)

    # ═══════════════════════════════════════════════
    # Load Default
    # ═══════════════════════════════════════════════

    def _load_default(self):
        """بارگذاری پیش‌فرض: ۲ قطعه مساوی"""
        if not self.position or not self.position.legs:
            return

        total = self.position.legs[0].quantity
        if total <= 1:
            return

        half = total // 2
        self._quantities = [half, total - half]
        self._reasons = ["", ""]
        self._refresh_table()

    # ═══════════════════════════════════════════════
    # مدیریت قطعات
    # ═══════════════════════════════════════════════

    def _add_piece(self, qty: int = 1, reason: str = ""):
        """افزودن قطعه جدید"""
        total = (
            self.position.legs[0].quantity
            if self.position and self.position.legs else 0
        )

        current_sum = sum(self._quantities)
        remaining = total - current_sum

        if remaining <= 0:
            QMessageBox.warning(
                self, "خطا",
                "مجموع قطعات به تعداد کل رسیده است.")
            return

        if qty > remaining:
            qty = remaining

        self._quantities.append(qty)
        self._reasons.append(reason)
        self._refresh_table()

    def _remove_piece(self, idx: int):
        """حذف قطعه"""
        if 0 <= idx < len(self._quantities):
            self._quantities.pop(idx)
            self._reasons.pop(idx)
            self._refresh_table()

    def _auto_split(self):
        """تقسیم مساوی به تعداد فعلی قطعات"""
        if not self.position or not self.position.legs:
            return

        n = len(self._quantities)
        if n < 2:
            return

        total = self.position.legs[0].quantity
        base = total // n
        remainder = total % n

        new_qtys = [base] * n
        for i in range(remainder):
            new_qtys[i] += 1

        self._quantities = new_qtys
        self._refresh_table()

    def _refresh_table(self):
        """به‌روزرسانی جدول قطعات"""
        self.table.setRowCount(0)
        self.table.setVisible(len(self._quantities) > 0)

        for i in range(len(self._quantities)):
            qty = self._quantities[i]
            reason = self._reasons[i]

            row = self.table.rowCount()
            self.table.insertRow(row)

            # #
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, num_item)

            # qty
            spin = QSpinBox()
            spin.setRange(1, 1_000_000)
            spin.setGroupSeparatorShown(True)
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setValue(qty)
            spin.valueChanged.connect(
                lambda val, r=i: self._on_qty_changed(r, val))
            self.table.setCellWidget(row, 1, spin)

            # reason
            cmb = QComboBox()
            for code, label in SPLIT_REASONS:
                cmb.addItem(label, code)
            idx = cmb.findData(reason)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
            cmb.currentIndexChanged.connect(
                lambda _, c=cmb, r=i:
                    self._on_reason_changed(r, c.currentData()))
            self.table.setCellWidget(row, 2, cmb)

            # remove
            btn = QPushButton("🗑")
            btn.setFixedWidth(40)
            set_kind(btn, "danger")
            btn.clicked.connect(
                lambda _, r=i: self._remove_piece(r))
            self.table.setCellWidget(row, 3, btn)

        # خلاصه
        total = (
            self.position.legs[0].quantity
            if self.position and self.position.legs else 0
        )
        current = sum(self._quantities)
        diff = total - current

        if diff == 0:
            text = f"✅ مجموع: {current} از {total}"
            set_tone(self.lbl_sum, "profit")
        elif diff > 0:
            text = f"⚠️ مجموع: {current} از {total} ({diff} باقی‌مانده)"
            set_tone(self.lbl_sum, "warn")
        else:
            text = f"❌ مجموع: {current} بیش از {total}"
            set_tone(self.lbl_sum, "loss")

        self.lbl_sum.setText(text)

        ok_btn = self.btns.button(QDialogButtonBox.Ok)
        ok_btn.setEnabled(
            diff == 0
            and len(self._quantities) >= 2
            and all(q > 0 for q in self._quantities)
        )

    def _on_qty_changed(self, idx: int, value: int):
        if 0 <= idx < len(self._quantities):
            self._quantities[idx] = value
            # برای جلوگیری از حلقه، فقط خلاصه را به‌روز کن
            total = (
                self.position.legs[0].quantity
                if self.position and self.position.legs else 0
            )
            current = sum(self._quantities)
            diff = total - current

            if diff == 0:
                self.lbl_sum.setText(
                    f"✅ مجموع: {current} از {total}")
                set_tone(self.lbl_sum, "profit")
            elif diff > 0:
                self.lbl_sum.setText(
                    f"⚠️ مجموع: {current} از {total} "
                    f"({diff} باقی‌مانده)")
                set_tone(self.lbl_sum, "warn")
            else:
                self.lbl_sum.setText(
                    f"❌ مجموع: {current} بیش از {total}")
                set_tone(self.lbl_sum, "loss")

            self.btns.button(QDialogButtonBox.Ok).setEnabled(
                diff == 0 and len(self._quantities) >= 2)

    def _on_reason_changed(self, idx: int, reason: str):
        if 0 <= idx < len(self._reasons):
            self._reasons[idx] = reason

    # ═══════════════════════════════════════════════
    # تأیید
    # ═══════════════════════════════════════════════

    def _on_accept(self):
        if not self.position or not self.position.legs:
            return

        total = self.position.legs[0].quantity
        if sum(self._quantities) != total:
            QMessageBox.warning(
                self, "خطا",
                f"مجموع قطعات ({sum(self._quantities)}) باید "
                f"برابر تعداد کل ({total}) باشد.")
            return

        if any(q <= 0 for q in self._quantities):
            QMessageBox.warning(
                self, "خطا",
                "تعداد هر قطعه باید حداقل 1 باشد.")
            return

        if len(self._quantities) < 2:
            QMessageBox.warning(
                self, "خطا",
                "حداقل 2 قطعه برای Split لازم است.")
            return

        self.accept()

    # ═══════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════

    def get_quantities(self) -> List[int]:
        return list(self._quantities)

    def get_reasons(self) -> List[str]:
        return list(self._reasons)


__all__ = ["SplitPositionDialog", "SPLIT_REASONS"]