# position_saver/ui/strategy_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ تعریف استراتژی جدید — فاز ۱.

ویژگی‌ها:
    ✅ ComboBox نوع استراتژی (استاندارد، فقط انگلیسی)
    ✅ نام نمایشی سفارشی
    ✅ اعتبارسنجی لحظه‌ای (Real-time)
    ✅ Leg-level validation
    ✅ تشخیص خودکار آفست (Long Offset / Short Offset)
    ✅ تشخیص Single Trade برای تک‌لگ
    ✅ پیشنهاد استراتژی از PositionPnLCalculator

استراتژی‌های پشتیبانی‌شده:
    - Long Call / Long Put           (تک‌لگ)
    - Bull Call Spread / Bear Put Spread
    - Covered Call
    - Long Box / Long Straddle / Long Strangle
    - Long Offset / Short Offset     (آفست - جدید)
    - Single Trade                   (تک‌معامله - جدید)
    - Custom                         (سفارشی)

قابلیت‌هایی که در فاز ۲ اضافه می‌شوند:
    ❌ Payoff Diagram
    ❌ Greeks
    ❌ Suggested Alternatives
"""

import logging
from typing import List, Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QLabel, QMessageBox,
    QDialogButtonBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QWidget, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from position_saver.theme import (
    Theme, fmt_money, fmt_int, set_kind, set_tone,
)
from position_saver.models import OptionLeg, LegType
from position_saver.pnl_calculator import PositionPnLCalculator
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.UI.StrategyDialog")


# ═══════════════════════════════════════════════════
# لیست استراتژی‌های استاندارد (فقط انگلیسی)
# ═══════════════════════════════════════════════════

STANDARD_STRATEGIES = [
    # ─── تک‌لگ ───
    ("Long Call", "Long Call"),
    ("Long Put", "Long Put"),

    # ─── اسپرد ───
    ("Bull Call Spread", "Bull Call Spread"),
    ("Bear Put Spread", "Bear Put Spread"),
    ("Covered Call", "Covered Call"),

    # ─── پیچیده ───
    ("Long Box", "Long Box"),
    ("Long Straddle", "Long Straddle"),
    ("Long Strangle", "Long Strangle"),

    # ─── آفست ───
    ("Long Offset", "Long Offset"),
    ("Short Offset", "Short Offset"),

    # ─── تک‌معامله ───
    ("Single Trade", "Single Trade"),

    # ─── سفارشی ───
    ("", "Custom"),
]


# ═══════════════════════════════════════════════════
# StrategyDialog
# ═══════════════════════════════════════════════════

class StrategyDialog(QDialog):
    """
    دیالوگ تعریف استراتژی جدید از لگ‌های انتخاب‌شده.

    استفاده:
        dlg = StrategyDialog(parent, trades=[...])
        if dlg.exec():
            result = dlg.get_result()
            # result = {
            #     "strategy_type": "Bull Call Spread",
            #     "display_name": "ضفزر اردیبهشت",
            # }
    """

    def __init__(self, parent=None, trades: Optional[List] = None):
        super().__init__(parent)
        self.setWindowTitle("➕ تعریف استراتژی جدید")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(850, 700)

        self.trades = trades or []
        self._result: Optional[dict] = None

        self._build_ui()
        self._auto_suggest()
        self._validate_and_update()

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── لگ‌های انتخابی ───
        legs_group = QGroupBox(
            f"📋 لگ‌های انتخابی ({len(self.trades)} مورد)")
        legs_layout = QVBoxLayout(legs_group)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "#", "تاریخ", "سمت", "نماد", "نوع", "strike", "سررسید"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 100)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.verticalHeader().setVisible(False)

        self._populate_legs()
        self.table.setFixedHeight(
            min(220, 28 * len(self.trades) + 40))
        legs_layout.addWidget(self.table)
        layout.addWidget(legs_group)

        # ─── انتخاب استراتژی ───
        strategy_group = QGroupBox("نوع استراتژی")
        strategy_layout = QFormLayout(strategy_group)

        self.cmb_strategy = QComboBox()
        for code, display in STANDARD_STRATEGIES:
            if code:
                self.cmb_strategy.addItem(display, code)
            else:
                self.cmb_strategy.addItem(display, "")
        self.cmb_strategy.currentIndexChanged.connect(
            self._on_strategy_changed)
        strategy_layout.addRow("نوع:", self.cmb_strategy)

        self.txt_display_name = QLineEdit()
        self.txt_display_name.setPlaceholderText(
            "مثلاً: ضفزر اردیبهشت ۱۴۰۵")
        strategy_layout.addRow("نام نمایشی (اختیاری):",
                                self.txt_display_name)

        layout.addWidget(strategy_group)

        # ─── پیشنهاد ───
        self.lbl_suggestion = QLabel("")
        self.lbl_suggestion.setWordWrap(True)
        set_tone(self.lbl_suggestion, "primary")
        layout.addWidget(self.lbl_suggestion)

        # ─── وضعیت اعتبارسنجی ───
        self.validation_group = QGroupBox("📊 بررسی لگ‌ها")
        validation_layout = QVBoxLayout(self.validation_group)

        self.lbl_validation = QLabel("—")
        self.lbl_validation.setWordWrap(True)
        validation_layout.addWidget(self.lbl_validation)

        layout.addWidget(self.validation_group)

        # ─── دکمه‌ها ───
        self.btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.button(QDialogButtonBox.Ok).setText("✅ تأیید")
        self.btns.button(QDialogButtonBox.Cancel).setText("❌ انصراف")
        set_kind(self.btns.button(QDialogButtonBox.Ok), "primary")
        self.btns.accepted.connect(self._on_accept)
        self.btns.rejected.connect(self.reject)
        layout.addWidget(self.btns)

    def _populate_legs(self):
        """پر کردن جدول لگ‌ها"""
        self.table.setRowCount(0)

        for i, t in enumerate(self.trades, 1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            # #
            item = QTableWidgetItem(str(i))
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item)

            # تاریخ
            self.table.setItem(row, 1, QTableWidgetItem(
                getattr(t, "raw_date", "—")))

            # سمت
            side_label = "—"
            if hasattr(t, "side") and t.side:
                side_label = t.side.label_fa
            side_item = QTableWidgetItem(side_label)
            side_item.setTextAlignment(Qt.AlignCenter)
            side_item.setForeground(
                QColor(Theme.PROFIT if side_label == "خرید"
                       else Theme.LOSS))
            self.table.setItem(row, 2, side_item)

            # نماد
            self.table.setItem(row, 3, QTableWidgetItem(
                getattr(t, "symbol", "—")))

            # نوع
            kind = "—"
            if getattr(t, "is_call", False):
                kind = "CALL"
            elif getattr(t, "is_put", False):
                kind = "PUT"
            elif getattr(t, "is_stock", False):
                kind = "سهم"
            kind_item = QTableWidgetItem(kind)
            kind_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, kind_item)

            # strike
            strike = getattr(t, "strike_price", None)
            strike_text = f"{int(strike):,}" if strike else "—"
            strike_item = QTableWidgetItem(strike_text)
            strike_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, strike_item)

            # سررسید
            self.table.setItem(row, 6, QTableWidgetItem(
                getattr(t, "expiry_date", "—") or "—"))

    # ═══════════════════════════════════════════════
    # تبدیل trades به legs
    # ═══════════════════════════════════════════════

    def _trades_to_legs(self) -> List[OptionLeg]:
        """تبدیل TradeRecord ها به OptionLeg برای اعتبارسنجی"""
        legs = []
        for t in self.trades:
            try:
                opt_kind = getattr(t, "option_kind", None)
                if opt_kind is None:
                    continue

                leg = OptionLeg(
                    symbol=getattr(t, "symbol", ""),
                    is_option=getattr(t, "is_option", True),
                    option_kind=opt_kind,
                    leg_type=getattr(t, "side", LegType.BUY),
                    strike_price=float(
                        getattr(t, "strike_price", 0) or 0),
                    contract_size=int(
                        getattr(t, "effective_contract_size", 1000)),
                    quantity=int(getattr(t, "quantity", 0)),
                    entry_price=float(getattr(t, "price", 0)),
                    expiry_date=getattr(t, "expiry_date", "") or "",
                    open_date=getattr(t, "raw_date", "") or "",
                )
                legs.append(leg)
            except Exception as e:
                logger.debug(f"trade_to_leg failed: {e}")
        return legs

    # ═══════════════════════════════════════════════
    # پیشنهاد خودکار
    # ═══════════════════════════════════════════════

    def _auto_suggest(self):
        """پیشنهاد استراتژی بر اساس ترکیب لگ‌ها"""
        try:
            legs = self._trades_to_legs()
            if not legs:
                return

            # ✅ اول: تشخیص آفست
            offset_type = self._detect_offset(legs)
            if offset_type:
                idx = self.cmb_strategy.findData(offset_type)
                if idx >= 0:
                    self.cmb_strategy.setCurrentIndex(idx)
                self.lbl_suggestion.setText(
                    f"💡 تشخیص: ترکیب آفست ({offset_type})")
                set_tone(self.lbl_suggestion, "primary")
                return

            # ✅ دوم: اگر یک لگ تنهاست
            if len(legs) == 1:
                idx = self.cmb_strategy.findData("Single Trade")
                if idx >= 0:
                    self.cmb_strategy.setCurrentIndex(idx)
                self.lbl_suggestion.setText(
                    "💡 یک لگ تنها — Single Trade")
                set_tone(self.lbl_suggestion, "primary")
                return

            # ✅ سوم: پیشنهاد عمومی از PnLCalculator
            suggestion = PositionPnLCalculator.suggest_strategy_name(legs)
            if suggestion:
                idx = self.cmb_strategy.findData(suggestion)
                if idx >= 0:
                    self.cmb_strategy.setCurrentIndex(idx)
                self.lbl_suggestion.setText(
                    f"💡 پیشنهاد سیستم: {suggestion}")
                set_tone(self.lbl_suggestion, "primary")
            else:
                self.lbl_suggestion.setText(
                    "💡 پیشنهادی نیست — خودتان انتخاب کنید")
                set_tone(self.lbl_suggestion, "muted")
        except Exception as e:
            logger.debug(f"auto_suggest failed: {e}")

    def _detect_offset(self, legs: List[OptionLeg]) -> str:
        """
        تشخیص آفست از ترکیب لگ‌ها.

        شرط‌های آفست:
            - دقیقاً ۲ لگ
            - همان نماد
            - همان strike
            - همان expiry
            - یکی BUY و یکی SELL

        Returns:
            "Long Offset" یا "Short Offset" یا ""
        """
        if len(legs) != 2:
            return ""

        # بررسی همان نماد
        if legs[0].symbol != legs[1].symbol:
            return ""

        # بررسی همان strike
        if legs[0].strike_price != legs[1].strike_price:
            return ""

        # بررسی همان expiry
        if legs[0].expiry_date != legs[1].expiry_date:
            return ""

        # بررسی جهت
        buy_count = sum(1 for l in legs
                        if l.leg_type == LegType.BUY)
        sell_count = sum(1 for l in legs
                         if l.leg_type == LegType.SELL)

        if buy_count != 1 or sell_count != 1:
            return ""

        # کدام اول BUY بود؟ → Long Offset
        # کدام اول SELL بود؟ → Short Offset
        try:
            first_leg = min(
                legs,
                key=lambda l: l.open_date or "9999/99/99"
            )
            if first_leg.leg_type == LegType.BUY:
                return "Long Offset"
            return "Short Offset"
        except Exception:
            # اگر open_date موجود نبود، از موقعیت در لیست استفاده کن
            if legs[0].leg_type == LegType.BUY:
                return "Long Offset"
            return "Short Offset"

    # ═══════════════════════════════════════════════
    # اعتبارسنجی لحظه‌ای
    # ═══════════════════════════════════════════════

    def _on_strategy_changed(self):
        self._validate_and_update()

    def _validate_and_update(self):
        """اعتبارسنجی لحظه‌ای + به‌روزرسانی UI"""
        strategy = self.cmb_strategy.currentData()
        legs = self._trades_to_legs()

        # سفارشی — همیشه معتبر (اگر ≥ ۱ لگ باشد)
        if not strategy:
            if not legs:
                self._show_validation_error(
                    "❌ حداقل یک لگ لازم است")
                return
            self._show_validation_ok(
                "✅ استراتژی سفارشی — بدون قانون خاص")
            return

        # اعتبارسنجی از PnLCalculator
        try:
            result = PositionPnLCalculator.validate_strategy(
                strategy, legs)
        except Exception as e:
            logger.exception(f"validate_strategy failed: {e}")
            self._show_validation_error(
                f"خطا در اعتبارسنجی: {e}")
            return

        if result["valid"]:
            text = "✅ <b>استراتژی معتبر است</b>"
            if result.get("warnings"):
                text += "<br><br>⚠️ هشدار:<br>"
                text += "<br>".join(
                    f"  • {w}" for w in result["warnings"])
            self._show_validation_ok(text)
        else:
            text = "❌ <b>خطاها:</b><br>"
            text += "<br>".join(
                f"  • {e}" for e in result["errors"])
            if result.get("warnings"):
                text += "<br><br>⚠️ هشدار:<br>"
                text += "<br>".join(
                    f"  • {w}" for w in result["warnings"])
            self._show_validation_error(text)

    def _show_validation_ok(self, html_text: str):
        self.lbl_validation.setText(html_text)
        set_tone(self.lbl_validation, "profit")
        self.btns.button(QDialogButtonBox.Ok).setEnabled(True)

    def _show_validation_error(self, html_text: str):
        self.lbl_validation.setText(html_text)
        set_tone(self.lbl_validation, "loss")
        self.btns.button(QDialogButtonBox.Ok).setEnabled(False)

    # ═══════════════════════════════════════════════
    # تأیید
    # ═══════════════════════════════════════════════

    def _on_accept(self):
        strategy = self.cmb_strategy.currentData()
        display_name = self.txt_display_name.text().strip()

        legs = self._trades_to_legs()

        if not legs:
            QMessageBox.warning(
                self, "خطا",
                "هیچ لگ معتبری وجود ندارد.")
            return

        # چک نهایی
        if strategy:
            result = PositionPnLCalculator.validate_strategy(
                strategy, legs)
            if not result["valid"]:
                QMessageBox.warning(
                    self, "خطا",
                    "استراتژی معتبر نیست. لطفاً خطاها را رفع کنید.")
                return

        # نام نمایشی پیش‌فرض
        if not display_name:
            if self.trades:
                symbol = getattr(self.trades[0], "symbol", "")
                if strategy:
                    display_name = f"{strategy} - {symbol}"
                else:
                    display_name = f"Custom - {symbol}"
            else:
                display_name = strategy or "Custom"

        self._result = {
            "strategy_type": strategy or "",
            "display_name": display_name,
        }
        self.accept()

    # ═══════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════

    def get_result(self) -> Optional[dict]:
        return self._result


__all__ = ["StrategyDialog", "STANDARD_STRATEGIES"]