# position_saver/ui/strategy_check_dialog.py
# -*- coding: utf-8 -*-

"""
پنجره‌ی چک استراتژی جدید.

هدف:
    بررسی تداخل لگ‌های استراتژی جدید با موقعیت‌های باز موجود.

استاندارد:
    - کاربر فقط نماد + سمت وارد می‌کند
    - مابقی از Snapshot زنده گرفته می‌شود
    - اگر Snapshot در دسترس نبود، پیغام «دستی پر کنید»
    - **بدون ذخیره** — فقط بررسی
"""

import logging
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QMessageBox,
    QHeaderView, QGroupBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QAbstractSpinBox, QSpinBox,
    QDialogButtonBox, QTextEdit, QWidget,
)
from PySide6.QtCore import Qt, QEvent, QPoint, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,
)
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.theme import (
    Theme, CURRENCY,
    fmt_money, fmt_int, fmt_pct,
    set_kind, set_tone,
)
from position_saver.ui.dialogs import (
    SymbolCompleter, find_conflicts,
    normalize_symbol, sanitize_symbol_input,
    _make_date_validator,
)
from position_saver.providers import get_market_snapshot
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.UI.StrategyCheck")


# ═══════════════════════════════════════════════════
# ستون‌ها
# ═══════════════════════════════════════════════════

COL_SYMBOL = 0
COL_SIDE = 1
COL_STRIKE = 2
COL_EXPIRY = 3
COL_STATUS = 4
N_COLS = 5


class StrategyCheckDialog(QDialog):
    """
    پنجره‌ی چک استراتژی جدید.

    استفاده:
        dlg = StrategyCheckDialog(parent, storage=storage, snapshot=snapshot)
        dlg.exec()
    """

    def __init__(self, parent=None, storage=None, snapshot=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 چک استراتژی جدید")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(950, 650)

        self.storage = storage
        self.snapshot = snapshot or self._fetch_snapshot()

        # ساخت completer
        self._symbol_items = self._build_symbol_items()
        self._completer = SymbolCompleter(self)
        self._completer.attach_callback(self._on_symbol_selected)
        self._completer.set_source(self._symbol_items)

        self._active_line_edit: Optional[QLineEdit] = None

        self._build_ui()

    # ═══════════════════════════════════════════════
    # Snapshot
    # ═══════════════════════════════════════════════

    def _fetch_snapshot(self):
        try:
            return get_market_snapshot(
                use_cache=True, force_refresh=False)
        except Exception as e:
            logger.warning(f"Snapshot failed: {e}")
            return None

    def _build_symbol_items(self) -> List[Dict[str, Any]]:
        """ساخت لیست نمادها از Snapshot."""
        items = []
        if self.snapshot is None:
            return items

        seen = set()
        for contract in self.snapshot.option_contracts:
            if not contract.ticker:
                continue
            symbol = normalize_symbol(contract.ticker)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)

            items.append({
                "symbol": symbol,
                "search_key": symbol.lower(),
                "data": {
                    "is_option": True,
                    "option_kind": contract.option_type,
                    "strike_price": float(contract.strike_price),
                    "contract_size": int(contract.contract_size),
                    "expiry_date": str(contract.expiry_date)
                        if contract.expiry_date else "",
                    "ins_code": str(contract.instrument_code or ""),
                    "underlying_ticker": normalize_symbol(
                        contract.underlying_ticker or ""),
                },
            })

        # سهم‌های پایه
        underlying_set = set()
        for contract in self.snapshot.option_contracts:
            if contract.underlying_ticker:
                underlying_set.add(
                    normalize_symbol(contract.underlying_ticker))
        for ua_key in self.snapshot.underlying_assets.keys():
            underlying_set.add(normalize_symbol(ua_key))

        for u in sorted(underlying_set):
            if not u:
                continue
            items.append({
                "symbol": u,
                "search_key": u.lower(),
                "data": {
                    "is_option": False,
                    "option_kind": OptionType.STOCK,
                    "strike_price": 0.0,
                    "contract_size": 1,
                    "expiry_date": "",
                    "ins_code": "",
                    "underlying_ticker": u,
                },
            })
        return items

    # ═══════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ─── توضیحات ───
        header = QLabel(
            "🔍 لگ‌های استراتژی جدید را وارد کنید و «چک» بزنید.\n"
            "برنامه بررسی می‌کند آیا این استراتژی با موقعیت‌های باز "
            "تداخل دارد یا نه.\n"
            "⚠️ این پنجره چیزی ذخیره نمی‌کند.")
        set_tone(header, "primary")
        header.setWordWrap(True)
        layout.addWidget(header)

        # ─── جدول لگ‌ها ───
        table_group = QGroupBox("لگ‌های استراتژی جدید")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget(0, N_COLS)
        self.table.setHorizontalHeaderLabels([
            "نماد (تایپ کنید)", "سمت", "قیمت اعمال", "سررسید", "وضعیت"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(COL_SYMBOL, 300)
        self.table.setColumnWidth(COL_SIDE, 100)
        self.table.setColumnWidth(COL_STRIKE, 140)
        self.table.setColumnWidth(COL_EXPIRY, 140)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(34)

        table_layout.addWidget(self.table)

        # ─── دکمه‌های افزودن/حذف ───
        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ افزودن لگ")
        btn_add.clicked.connect(self._add_leg_row)
        btn_row.addWidget(btn_add)

        btn_remove = QPushButton("➖ حذف لگ")
        btn_remove.clicked.connect(self._remove_leg_row)
        btn_row.addWidget(btn_remove)

        btn_row.addStretch()
        table_layout.addLayout(btn_row)

        layout.addWidget(table_group, 1)

        # ─── دکمه چک ───
        check_row = QHBoxLayout()
        check_row.addStretch()

        self.btn_check = QPushButton("🔍 چک استراتژی")
        self.btn_check.setMinimumWidth(200)
        self.btn_check.setMinimumHeight(38)
        set_kind(self.btn_check, "primary")
        self.btn_check.clicked.connect(self._on_check)
        check_row.addWidget(self.btn_check)

        check_row.addStretch()
        layout.addLayout(check_row)

        # ─── پنل نتیجه ───
        result_group = QGroupBox("نتیجه‌ی بررسی")
        result_layout = QVBoxLayout(result_group)

        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setMinimumHeight(150)
        self.txt_result.setStyleSheet(
            f"background-color: {Theme.CARD}; "
            f"border: 1px solid {Theme.BORDER}; "
            f"border-radius: 4px; padding: 8px;")
        result_layout.addWidget(self.txt_result)

        layout.addWidget(result_group)

        # ─── دکمه بستن ───
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("❌ بستن")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # ─── افزودن یک ردیف اولیه ───
        self._add_leg_row()

    # ═══════════════════════════════════════════════
    # مدیریت ردیف‌ها
    # ═══════════════════════════════════════════════

    def _add_leg_row(self):
        self._hide_completer()
        row = self.table.rowCount()
        self.table.insertRow(row)

        # ─── ستون ۰: نماد ───
        line_symbol = QLineEdit()
        line_symbol.setPlaceholderText(
            "نام نماد... (مثلاً ضفزر505)")
        line_symbol.textEdited.connect(
            lambda text, le=line_symbol:
                self._on_symbol_text_edited(le, text))
        line_symbol.installEventFilter(self)
        line_symbol.focusInEvent = (
            lambda event, le=line_symbol:
                self._on_line_focus_in(event, le))
        self.table.setCellWidget(row, COL_SYMBOL, line_symbol)

        # ─── ستون ۱: سمت ───
        cmb_side = QComboBox()
        cmb_side.addItem(LegType.BUY.label_fa, LegType.BUY)
        cmb_side.addItem(LegType.SELL.label_fa, LegType.SELL)
        self.table.setCellWidget(row, COL_SIDE, cmb_side)

        # ─── ستون ۲: strike ───
        spin_strike = QSpinBox()
        spin_strike.setRange(0, 1_000_000_000)
        spin_strike.setSingleStep(50)
        spin_strike.setGroupSeparatorShown(True)
        spin_strike.setButtonSymbols(QAbstractSpinBox.NoButtons)
        spin_strike.setValue(0)
        self.table.setCellWidget(row, COL_STRIKE, spin_strike)

        # ─── ستون ۳: expiry ───
        line_expiry = QLineEdit()
        line_expiry.setPlaceholderText("1405/05/25")
        line_expiry.setValidator(_make_date_validator())
        self.table.setCellWidget(row, COL_EXPIRY, line_expiry)

        # ─── ستون ۴: وضعیت ───
        status_item = QTableWidgetItem("⏳ در انتظار")
        status_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, COL_STATUS, status_item)

    def _remove_leg_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self._hide_completer()
            self.table.removeRow(row)

    # ═══════════════════════════════════════════════
    # Autocomplete
    # ═══════════════════════════════════════════════

    def _hide_completer(self):
        try:
            self._completer._hide_list()
        except Exception:
            pass

    def _on_line_focus_in(self, event, line_edit: QLineEdit):
        self._active_line_edit = line_edit
        text = line_edit.text().strip()
        if text and self._should_open_list(text):
            self._show_completer_for(line_edit, text)
        else:
            self._hide_completer()
        QLineEdit.focusInEvent(line_edit, event)

    def _should_open_list(self, text: str) -> bool:
        if not text:
            return False
        if text[0] in ("ض", "ط"):
            return len(text) >= 2
        return len(text) >= 1

    def _on_symbol_text_edited(self, line_edit: QLineEdit, text: str):
        self._active_line_edit = line_edit
        if not self._should_open_list(text):
            self._hide_completer()
            return
        self._show_completer_for(line_edit, text)

    def _show_completer_for(self, line_edit: QLineEdit, prefix: str):
        if self.snapshot is None or not self._symbol_items:
            return
        global_pos = line_edit.mapToGlobal(
            QPoint(0, line_edit.height()))
        width = line_edit.width()
        self._completer.filter_and_show(prefix, global_pos, width)

    def _on_symbol_selected(self, item: Dict[str, Any]):
        line_edit = self._active_line_edit
        if line_edit is None:
            return

        # پیدا کردن ردیف
        row = -1
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, COL_SYMBOL) is line_edit:
                row = r
                break

        if row < 0:
            self._hide_completer()
            return

        data = item.get("data", {})
        symbol = item.get("symbol", "")

        line_edit.blockSignals(True)
        line_edit.setText(symbol)
        line_edit.blockSignals(False)

        spin_strike = self.table.cellWidget(row, COL_STRIKE)
        spin_strike.setValue(int(data.get("strike_price", 0)))

        line_expiry = self.table.cellWidget(row, COL_EXPIRY)
        line_expiry.setText(data.get("expiry_date", ""))

        # به‌روزرسانی وضعیت
        self._update_row_status(row)

        self._hide_completer()

    def _update_row_status(self, row: int):
        """به‌روزرسانی وضعیت ردیف."""
        line_symbol = self.table.cellWidget(row, COL_SYMBOL)
        spin_strike = self.table.cellWidget(row, COL_STRIKE)
        line_expiry = self.table.cellWidget(row, COL_EXPIRY)

        if not line_symbol or not line_symbol.text().strip():
            status = "⚪ خالی"
            color = Theme.MUTED
        else:
            symbol = normalize_symbol(line_symbol.text())
            strike = spin_strike.value()
            expiry = line_expiry.text().strip()

            # بررسی در Snapshot
            found = False
            for it in self._symbol_items:
                if it["symbol"] == symbol:
                    found = True
                    break

            if found and (strike > 0 or not symbol.startswith(("ض", "ط"))):
                status = "✅ آماده چک"
                color = Theme.PROFIT
            else:
                status = "⚠️ ناقص (دستی پر کنید)"
                color = Theme.WARN

        item = QTableWidgetItem(status)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor(color))
        self.table.setItem(row, COL_STATUS, item)

    # ═══════════════════════════════════════════════
    # Event Filter
    # ═══════════════════════════════════════════════

    def eventFilter(self, obj, event):
        if obj is not self._active_line_edit:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.KeyPress:
            key = event.key()
            if self._completer.is_open():
                if key == Qt.Key_Down:
                    self._completer.move_selection(+1)
                    return True
                if key == Qt.Key_Up:
                    self._completer.move_selection(-1)
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    self._completer.select_current()
                    return True
                if key == Qt.Key_Escape:
                    self._hide_completer()
                    return True
        return super().eventFilter(obj, event)

    # ═══════════════════════════════════════════════
    # جمع‌آوری لگ‌ها
    # ═══════════════════════════════════════════════

    def _collect_legs(self) -> List[OptionLeg]:
        """جمع‌آوری لگ‌ها از جدول."""
        legs = []
        for r in range(self.table.rowCount()):
            line_symbol = self.table.cellWidget(r, COL_SYMBOL)
            cmb_side = self.table.cellWidget(r, COL_SIDE)
            spin_strike = self.table.cellWidget(r, COL_STRIKE)
            line_expiry = self.table.cellWidget(r, COL_EXPIRY)

            if not line_symbol or not line_symbol.text().strip():
                continue

            symbol = normalize_symbol(
                sanitize_symbol_input(line_symbol.text()))

            # تشخیص نوع
            option_kind = OptionType.STOCK
            if symbol.startswith("ض"):
                option_kind = OptionType.CALL
            elif symbol.startswith("ط"):
                option_kind = OptionType.PUT

            # بررسی در Snapshot (اولویت)
            for it in self._symbol_items:
                if it["symbol"] == symbol:
                    option_kind = it["data"].get(
                        "option_kind", option_kind)
                    break

            leg_type = cmb_side.currentData() or LegType.BUY
            strike = spin_strike.value()
            expiry = line_expiry.text().strip()
            is_option = (option_kind != OptionType.STOCK)

            leg = OptionLeg(
                symbol=symbol,
                is_option=is_option,
                option_kind=option_kind,
                leg_type=leg_type,
                strike_price=strike if is_option else 0.0,
                contract_size=1000 if is_option else 1,
                quantity=1,
                entry_price=0.0,
                current_price=0.0,
                expiry_date=expiry if is_option else "",
            )
            legs.append(leg)

        return legs

    # ═══════════════════════════════════════════════
    # دکمه‌ی چک
    # ═══════════════════════════════════════════════

    def _on_check(self):
        """بررسی تداخل و نمایش نتیجه."""
        legs = self._collect_legs()

        if not legs:
            self.txt_result.clear()
            self.txt_result.setHtml(
                "<p style='color: #C77700;'>⚠️ لطفاً ابتدا لگ‌ها را "
                "وارد کنید.</p>")
            return

        # بررسی کامل بودن
        incomplete = []
        for leg in legs:
            if leg.is_option:
                if leg.strike_price <= 0 or not leg.expiry_date:
                    incomplete.append(leg)

        # بررسی تداخل
        if self.storage is None:
            self.txt_result.clear()
            self.txt_result.setHtml(
                "<p style='color: #C77700;'>"
                "⚠️ دسترسی به storage ممکن نیست.</p>")
            return

        try:
            positions = self.storage.load_positions()
        except Exception as e:
            logger.exception(f"Load positions failed: {e}")
            positions = []

        conflicts = find_conflicts(legs, positions)

        # ─── ساخت پیام ───
        html = self._build_result_html(
            legs, conflicts, incomplete)
        self.txt_result.setHtml(html)

    def _build_result_html(
        self,
        legs: List[OptionLeg],
        conflicts: List[Dict[str, Any]],
        incomplete: List[OptionLeg],
    ) -> str:
        """ساخت HTML نتیجه."""
        parts = []

        # ─── هشدار برای ناقص‌ها ───
        if incomplete:
            parts.append(
                "<h3 style='color: #C77700;'>"
                f"⚠️ {len(incomplete)} لگ ناقص است</h3>")
            parts.append("<p>لطفاً اطلاعات زیر را دستی وارد کنید:</p><ul>")
            for leg in incomplete:
                missing = []
                if leg.strike_price <= 0:
                    missing.append("قیمت اعمال")
                if not leg.expiry_date:
                    missing.append("سررسید")
                parts.append(
                    f"<li>{leg.symbol} — کمبود: "
                    f"{'، '.join(missing)}</li>")
            parts.append("</ul>")

        # ─── نتیجه تداخل ───
        if not conflicts:
            parts.append(
                "<h2 style='color: #1B8A5A;'>✅ بدون تداخل</h2>")
            parts.append(
                "<p>هیچ تداخلی با موقعیت‌های باز موجود "
                "شناسایی نشد. می‌توانید استراتژی را اجرا کنید.</p>")
        else:
            parts.append(
                "<h2 style='color: #D64545;'>"
                f"⚠️ {len(conflicts)} تداخل شناسایی شد</h2>")
            parts.append(
                "<p>لگ‌های زیر با موقعیت‌های باز تداخل دارند:</p>")
            parts.append("<ol>")
            for c in conflicts:
                leg = c["leg"]
                pos = c["position"]
                existing = c["existing_leg"]

                pnl = 0.0
                try:
                    pnl, _ = PositionPnLCalculator.calculate_live_pnl(pos)
                except Exception:
                    pass

                parts.append("<li>")
                parts.append(
                    f"<b>{leg.leg_type.label_fa} {leg.symbol}</b> "
                    f"(strike={fmt_int(leg.strike_price)})<br>")
                parts.append(
                    f"&nbsp;&nbsp;└─ با موقعیت "
                    f"<code>{pos.position_id}</code> "
                    f"({pos.strategy_name or 'بدون نام'})<br>")
                parts.append(
                    f"&nbsp;&nbsp;└─ {existing.leg_type.label_fa} "
                    f"{existing.symbol} "
                    f"(باز از {existing.open_date or '—'})<br>")
                parts.append(
                    f"&nbsp;&nbsp;└─ PnL فعلی: "
                    f"{fmt_money(pnl)} {CURRENCY}")
                parts.append("</li>")
            parts.append("</ol>")

            parts.append(
                "<div style='padding: 10px; background-color: #FFF8E1; "
                "border: 1px solid #C77700; border-radius: 6px;'>")
            parts.append("<b>⚠️ توجه:</b>")
            parts.append("<ul>")
            parts.append(
                "<li>اگر این استراتژی را اجرا کنید، "
                "موقعیت‌های فوق آفست می‌شوند.</li>")
            parts.append(
                "<li>PnL آن‌ها قفل می‌شود و دیگر تغییر نمی‌کند.</li>")
            parts.append(
                "<li>لطفاً قبل از اجرای معامله، مطمئن شوید.</li>")
            parts.append("</ul>")
            parts.append("</div>")

        return "".join(parts)


__all__ = ["StrategyCheckDialog"]