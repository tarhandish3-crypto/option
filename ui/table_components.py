# ui/table_components.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import time
import logging
from typing import Any, List, Dict, Optional, Tuple, Union

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex,
    QSortFilterProxyModel, QTimer, Signal
)
from PySide6.QtGui import QColor, QBrush, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.TableComponents")

FLASH_DURATION_SEC = 0.6  # مدت‌زمان افکت محوشونده تغییر قیمت (ثانیه)


# =========================================================================
# ۱. مدل اصلی و پرسرعت جدول (Fast Strategy Table Model)
# =========================================================================

class FastStrategyTableModel(QAbstractTableModel):
    """
    مدل داده‌ای بهینه‌شده برای مدیریت صدها استراتژی معاملاتی،
    پشتیبانی از ستون‌های داینامیک P&L و انیمیشن Tick Flashing.
    """
    flash_tick_signal = Signal()
    checked_strategy_changed = Signal(object)

    def __init__(
        self,
        price_steps: Optional[List[float]] = None,
        theme_mode: ui_theme.ThemeMode = "dark",
        parent: Optional[Any] = None
    ):
        super().__init__(parent)
        self._price_steps: List[float] = price_steps or []
        self._theme_mode: ui_theme.ThemeMode = theme_mode
        self._strategies: List[Any] = []
        # فقط یک سطر می‌تواند تیک بخورد (Single-Select)
        self._checked_row: int = -1

        # دیکشنری نگهداری زمان و جهت تغییر قیمت برای پویانمایی: {(row_id, col_idx): (timestamp, "UP"|"DOWN")}
        self._flash_map: Dict[Tuple[str, int], Tuple[float, str]] = {}

        # تایمر نرم برای رندر مجدد سلول‌های در حال افکت (Fade Effect Timer)
        self._anim_timer = QTimer(self)
        # ~16 FPS برای انیمیشن سبک و بدون بار اضافی
        self._anim_timer.setInterval(60)
        self._anim_timer.timeout.connect(self._on_anim_timer_tick)

        self._fixed_headers = [
            "✓", "Rank", "Strategy", "Positions", "DTE / سررسید", "Ticker", "Breakeven"
        ]
        self._rebuild_headers()

    def _rebuild_headers(self) -> None:
        """ساخت کامل لیست عناوین ستون‌ها با احتساب درصدهای داینامیک"""
        dynamic_headers = [f"{step:+.1f}%" if step !=
                           0 else "0.0%" for step in self._price_steps]
        self._headers = self._fixed_headers + dynamic_headers

    def set_price_steps(self, steps: List[float]) -> None:
        """تغییر ستون‌های درصدی قیمت"""
        self.beginResetModel()
        self._price_steps = steps
        self._rebuild_headers()
        self.endResetModel()

    def set_theme_mode(self, mode: ui_theme.ThemeMode) -> None:
        """بروزرسانی تم مدل"""
        self._theme_mode = mode
        self.layoutChanged.emit()

    # ------------------ متدهای پایه QAbstractTableModel ------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._strategies)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(self._headers):
                return self._headers[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        default_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            return default_flags | Qt.ItemFlag.ItemIsUserCheckable
        return default_flags

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._strategies)):
            return None

        row = index.row()
        col = index.column()
        strat = self._strategies[row]

        # ۱. وضعیت چک‌باکس ستون اول
        if col == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if self._checked_row == row else Qt.CheckState.Unchecked

        # ۲. مقدار کامل شیء استراتژی (UserRole + 1)
        if role == Qt.ItemDataRole.UserRole + 1:
            return strat

        # ۳. رندر داده‌های متنی (DisplayRole)
        if role == Qt.ItemDataRole.DisplayRole:
            return self._get_display_value(strat, row, col)

        # ۴. مقدار عددی خام برای مرتب‌سازی (UserRole)
        if role == Qt.ItemDataRole.UserRole:
            return self._get_sort_value(strat, row, col)

        # ۵. رنگ متن سود / زیان (ForegroundRole)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._get_foreground_color(strat, col)

        # ۶. انیمیشن تغییر قیمت (BackgroundRole - Tick Flashing)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._get_flash_background(strat, col)

        # ۷. تراز متن (TextAlignmentRole)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 4, 5):
                return Qt.AlignmentFlag.AlignCenter
            if col >= 7:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        # ۸. فونت بولد برای ستون‌های کلیدی
        if role == Qt.ItemDataRole.FontRole:
            if col in (1, 2, 5):
                font = QFont()
                font.setBold(True)
                return font

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False

        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            prev_checked = self._checked_row
            if value == Qt.CheckState.Checked:
                self._checked_row = index.row()
                selected_strat = self._strategies[self._checked_row]
            else:
                self._checked_row = -1
                selected_strat = None

            # بروزرسانی سطر قبلی و سطر فعلی در جدول
            if prev_checked != -1 and prev_checked < len(self._strategies):
                self.dataChanged.emit(self.index(
                    prev_checked, 0), self.index(prev_checked, 0))
            self.dataChanged.emit(index, index)

            self.checked_strategy_changed.emit(selected_strat)
            return True

        return False

    # ------------------ استخراج و فرمت‌بندی مقادیر سلول‌ها ------------------

    def _get_display_value(self, strat: Any, row: int, col: int) -> str:
        if col == 0:
            return ""
        if col == 1:
            return str(getattr(strat, 'rank', row + 1))
        if col == 2:
            return str(getattr(strat, 'strategy_name', 'N/A'))
        if col == 3:
            return self._format_positions(strat)
        if col == 4:
            return self._format_dte_expiry(strat)
        if col == 5:
            return str(getattr(strat, 'underlying_ticker', '-'))
        if col == 6:
            return self._format_breakeven(strat)

        # ستون‌های داینامیک سود و زیان (P&L Returns)
        dynamic_idx = col - 7
        return self._format_dynamic_pnl(strat, dynamic_idx)

    def _get_sort_value(self, strat: Any, row: int, col: int) -> Union[int, float, str]:
        if col == 0:
            return 1 if self._checked_row == row else 0
        if col == 1:
            return int(getattr(strat, 'rank', row + 1))
        if col == 2:
            return str(getattr(strat, 'strategy_name', ''))
        if col == 4:
            return int(getattr(strat, 'days_to_maturity', 0))
        if col == 5:
            return str(getattr(strat, 'underlying_ticker', ''))
        if col >= 7:
            pnl_list = self._get_pnl_data_list(strat)
            idx = col - 7
            if idx < len(pnl_list) and pnl_list[idx] is not None:
                try:
                    return float(pnl_list[idx])
                except (ValueError, TypeError):
                    return -999999999.0
            return -999999999.0
        return str(self._get_display_value(strat, row, col))

    def _get_foreground_color(self, strat: Any, col: int) -> Optional[QBrush]:
        if col >= 7:
            pnl_list = self._get_pnl_data_list(strat)
            idx = col - 7
            if idx < len(pnl_list) and pnl_list[idx] is not None:
                try:
                    val = float(pnl_list[idx])
                    if val != 0:
                        return QBrush(ui_theme.get_pnl_qcolor(val, self._theme_mode))
                except (ValueError, TypeError):
                    pass
        return None

    def _get_flash_background(self, strat: Any, col: int) -> Optional[QColor]:
        strat_id = self._get_strat_id(strat)
        flash_info = self._flash_map.get((strat_id, col))
        if not flash_info:
            return None

        ts, direction = flash_info
        elapsed = time.time() - ts
        if elapsed < FLASH_DURATION_SEC:
            alpha = int(190 * (1.0 - elapsed / FLASH_DURATION_SEC))
            return ui_theme.get_flash_qcolor(direction, alpha=alpha)
        else:
            return None

    # ------------------ فرمت‌بندی داده‌های تخصصی ------------------

    def _format_positions(self, strat: Any) -> str:
        legs = getattr(strat, 'legs', [])
        if not legs:
            return "-"
        parts = []
        for leg in legs:
            contract = getattr(leg, 'contract', None)
            ticker = contract.ticker if contract else 'سهام'
            side_str = "خرید" if str(getattr(leg, 'side', '')).upper() in (
                "BUY", "SIDE.BUY") else "فروش"
            ratio = getattr(leg, 'ratio', 1)
            parts.append(f"{ticker} ({ratio}x{side_str})")
        return " | ".join(parts)

    def _format_dte_expiry(self, strat: Any) -> str:
        dte = int(getattr(strat, 'days_to_maturity', 0))
        legs = getattr(strat, 'legs', [])
        if legs and getattr(legs[0], 'contract', None):
            expiry = getattr(legs[0].contract, 'expiry_date', None)
            if expiry:
                return ui_theme.format_jalali_date(expiry, include_dte=True)
        return f"{dte} روز"

    def _format_breakeven(self, strat: Any) -> str:
        be_list = getattr(strat, 'break_even_points', [])
        metadata = getattr(strat, 'metadata', {})
        if not be_list and isinstance(metadata, dict):
            be_list = metadata.get('break_even_points', [])
        if be_list:
            return ", ".join(ui_theme.format_rial(p) for p in be_list)
        return "-"

    def _format_dynamic_pnl(self, strat: Any, index: int) -> str:
        pnl_list = self._get_pnl_data_list(strat)
        if index < len(pnl_list) and pnl_list[index] is not None:
            try:
                num_val = float(pnl_list[index])
                return ui_theme.format_rial(num_val, show_sign=True)
            except (ValueError, TypeError):
                return str(pnl_list[index])
        return "-"

    def _get_pnl_data_list(self, strat: Any) -> List[Any]:
        metadata = getattr(strat, 'metadata', {})
        if isinstance(metadata, dict):
            data = metadata.get('returns_monthly_pct', [])
            if not data:
                data = metadata.get('net_returns_closed', [])
            return data
        return []

    def _get_strat_id(self, strat: Any) -> str:
        """شناسه یکتای استراتژی برای ترکینگ تغییرات قیمت"""
        if hasattr(strat, 'id'):
            return str(strat.id)
        ticker = getattr(strat, 'underlying_ticker', '')
        name = getattr(strat, 'strategy_name', '')
        rank = getattr(strat, 'rank', 0)
        return f"{ticker}_{name}_{rank}"

    # ------------------ مدیریت بروزرسانی دسته‌ای و پویانمایی ------------------

    def update_strategies_batch(self, new_strategies: List[Any]) -> None:
        """
        بروزرسانی داده‌ها به صورت دسته‌ای همراه با مقایسه مقادیر قبلی
        و ثبت انیمیشن تغییر قیمت (Tick Flashing).
        """
        now = time.time()
        old_map = {self._get_strat_id(s): s for s in self._strategies}

        # بررسی و فعال‌سازی تیک فلش برای سلول‌هایی که تغییر کرده‌اند
        for s in new_strategies:
            sid = self._get_strat_id(s)
            if sid in old_map:
                old_s = old_map[sid]
                old_pnls = self._get_pnl_data_list(old_s)
                new_pnls = self._get_pnl_data_list(s)

                for idx, (old_p, new_p) in enumerate(zip(old_pnls, new_pnls)):
                    try:
                        if float(new_p) > float(old_p):
                            self._flash_map[(sid, 7 + idx)] = (now, "UP")
                        elif float(new_p) < float(old_p):
                            self._flash_map[(sid, 7 + idx)] = (now, "DOWN")
                    except (ValueError, TypeError):
                        pass

        self.beginResetModel()
        self._strategies = list(new_strategies)
        self._checked_row = -1
        self.endResetModel()

        # استارت تایمر افکت در صورت وجود تغییرات
        if self._flash_map and not self._anim_timer.isActive():
            self._anim_timer.start()

    def set_strategies(self, strategies: List[Any]) -> None:
        """تنظیم و بارگذاری لیست استراتژی‌ها"""
        self.beginResetModel()
        self._strategies = list(strategies)
        self._checked_row = -1
        self._flash_map.clear()
        self.endResetModel()

    def clear(self) -> None:
        """پاک‌سازی جدول"""
        self.beginResetModel()
        self._strategies.clear()
        self._checked_row = -1
        self._flash_map.clear()
        self.endResetModel()

    def get_strategy(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._strategies):
            return self._strategies[row]
        return None

    def get_checked_strategy(self) -> Optional[Any]:
        if 0 <= self._checked_row < len(self._strategies):
            return self._strategies[self._checked_row]
        return None

    def _on_anim_timer_tick(self) -> None:
        """بررسی زمان انقضای انیمیشن‌ها و تریگر رندر مجدد جدول"""
        now = time.time()
        expired_keys = [
            k for k, (ts, _) in self._flash_map.items()
            if (now - ts) >= FLASH_DURATION_SEC
        ]
        for k in expired_keys:
            del self._flash_map[k]

        if not self._flash_map:
            self._anim_timer.stop()

        self.layoutChanged.emit()


# =========================================================================
# ۲. نماینده رندر سلول‌ها (Tick Flash Styled Delegate)
# =========================================================================

class StrategyCellDelegate(QStyledItemDelegate):
    """
    نماینده اختصاصی برای رندر سریع سلول‌ها، پدینگ زیبا و اعمال انیمیشن تغییر قیمت.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # ۱. ابتدا رندر پیش‌فرض آیتم
        super().paint(painter, option, index)

        # ۲. اعمال افکت فلش قیمت روی سلول در صورت وجود
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(bg_color, QColor) and bg_color.isValid() and bg_color.alpha() > 0:
            painter.save()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.fillRect(option.rect, bg_color)
            painter.restore()


# =========================================================================
# ۳. مدل پراکسی فیلتر و مرتب‌سازی (Strategy Filter Proxy Model)
# =========================================================================

class StrategyFilterProxyModel(QSortFilterProxyModel):
    """
    پراکسی مدل پیشرفته جهت:
    ۱. مرتب‌سازی عددی صحیح بر اساس UserRole
    ۲. فیلتر کردن نمادهای بلاک‌شده یا عبارات جستجو شده
    """

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self._excluded_symbols: set[str] = set()
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setDynamicSortFilter(True)

    def set_excluded_symbols(self, symbols: List[str]) -> None:
        self._excluded_symbols = set(symbols)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._excluded_symbols:
            return True

        model = self.sourceModel()
        if not model:
            return True

        # استخراج نماد دارایی پایه از ستون ۵
        ticker_idx = model.index(source_row, 5, source_parent)
        ticker = str(model.data(ticker_idx, Qt.ItemDataRole.DisplayRole) or "")

        if ticker in self._excluded_symbols:
            return False

        # استخراج متن موقعیت‌ها از ستون ۳
        pos_idx = model.index(source_row, 3, source_parent)
        pos_text = str(model.data(pos_idx, Qt.ItemDataRole.DisplayRole) or "")
        if any(sym in pos_text for sym in self._excluded_symbols):
            return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_data = left.data(Qt.ItemDataRole.UserRole)
        right_data = right.data(Qt.ItemDataRole.UserRole)

        if left_data is None or right_data is None:
            return super().lessThan(left, right)

        try:
            return float(left_data) < float(right_data)
        except (ValueError, TypeError):
            return str(left_data) < str(right_data)
