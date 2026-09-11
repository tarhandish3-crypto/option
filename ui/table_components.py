# ui/table_components.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QModelIndex, QObject, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTableWidgetItem

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.TableComponents")

FLASH_DURATION_SEC = 0.6
_FLASH_TICK_MS = 40  # فاصله بروزرسانی محو‌شدگی (~۲۵ فریم بر ثانیه، کافی و سبک)

# مقیاس پیش‌فرض نوار هیت‌مپ تا رسیدن اولین populate_table واقعی (ستون‌های سود/زیان
# مقادیر بازده درصدی هستند، نه ریال؛ رجوع کنید به analytics/payoff_calculator.py).
_DEFAULT_HEATMAP_MAX_ABS = 50.0


class CellFlashManager(QObject):
    """
    مدیریت متمرکز انیمیشن محوشونده «فلش تغییر قیمت» (Tick Flash) روی سلول‌های جدول.

    نکته‌ی مهمِ طراحی: این کلاس هیچ‌وقت `item.setData(...)` روی مدل صدا نمی‌زند.
    فلش صرفاً یک افکت لایه‌ی View است — رنگ لحظه‌ای هر سلول در حال فلش، مستقیماً
    داخل StrategyCellDelegate.paint() و فقط بر مبنای زمان سپری‌شده محاسبه می‌شود
    (متد current_color). نقش این کلاس فقط دو چیز است:
      ۱. نگه‌داری اینکه «کدام آیتم از چه زمانی با چه رنگی در حال فلش زدن است».
      ۲. هر _FLASH_TICK_MS، فقط ناحیه‌ی تصویری همان سلول‌ها را invalidate کند
         (viewport().update) تا Qt دوباره paint() را برایشان صدا بزند.
    چون هیچ داده‌ای در مدل تغییر نمی‌کند، هیچ سیگنال dataChanged/itemChanged‌ای
    هم هرگز منتشر نمی‌شود — نه اینکه منتشر و بعد block شود.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # کلید دیکشنری id(item) است (همیشه hashable، صرف‌نظر از نسخه‌ی PySide6)،
        # اما خودِ آبجکت item هم به‌عنوان مقدار داخل دیکشنری نگه داشته می‌شود.
        # همین رفرنس زنده باعث می‌شود CPython اجازه‌ی بازاستفاده از همان آدرس
        # حافظه برای آبجکت دیگری را ندهد؛ یعنی تداخل احتمالی روی id() منتفی است.
        self._active: Dict[int, Dict[str, Any]] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(_FLASH_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    def flash(
        self,
        item: QTableWidgetItem,
        direction: str,
        duration_sec: float = FLASH_DURATION_SEC,
    ) -> None:
        """شروع/ری‌استارت فلش روی یک آیتم؛ بدون هیچ تغییری در مدل."""
        if item is None:
            return

        base_color = ui_theme.get_flash_qcolor(direction)
        self._active[id(item)] = {
            "item": item,
            "start": time.monotonic(),
            "duration": max(duration_sec, _FLASH_TICK_MS / 1000.0),
            "base_color": base_color,
        }
        self._request_repaint(item)

        if not self._timer.isActive():
            self._timer.start()

    def current_color(self, item: Optional[QTableWidgetItem]) -> Optional[QColor]:
        """
        رنگ لحظه‌ای فلش برای یک آیتم، فقط بر مبنای زمان سپری‌شده (بدون خواندن
        هیچ داده‌ای از خودِ آیتم). این تنها متدی است که StrategyCellDelegate.paint()
        صدا می‌زند. اگر آیتم در حال فلش نباشد یا انیمیشنش تمام شده باشد None
        برمی‌گرداند.
        """
        if item is None:
            return None
        info = self._active.get(id(item))
        if info is None or info["item"] is not item:
            return None

        elapsed = time.monotonic() - info["start"]
        progress = elapsed / info["duration"]
        if progress >= 1.0:
            self._active.pop(id(item), None)
            return None

        faded = QColor(info["base_color"])
        faded.setAlpha(int(info["base_color"].alpha() * (1.0 - progress)))
        return faded

    def _on_tick(self) -> None:
        finished_keys = []
        for key, info in list(self._active.items()):
            item: QTableWidgetItem = info["item"]
            elapsed = time.monotonic() - info["start"]
            try:
                if elapsed >= info["duration"] or not self._request_repaint(item):
                    finished_keys.append(key)
            except RuntimeError:
                # آبجکت Qt زیرین حذف شده (مثلاً بعد از رفرش/پاک‌سازی جدول)
                finished_keys.append(key)

        for key in finished_keys:
            self._active.pop(key, None)

        if not self._active:
            self._timer.stop()

    @staticmethod
    def _request_repaint(item: QTableWidgetItem) -> bool:
        """
        فقط ناحیه‌ی بصری همین سلول را invalidate می‌کند (بدون تغییر داده‌ی مدل،
        پس بدون هیچ سیگنالی). اگر جدول دیگر در دسترس نباشد False برمی‌گرداند.
        """
        table = item.tableWidget()
        if table is None:
            return False
        table.viewport().update(table.visualItemRect(item))
        return True

    def clear(self) -> None:
        """توقف کامل و پاک‌سازی تمام فلش‌های در حال اجرا (مثلاً هنگام پاک‌کردن نتایج جدول)."""
        self._active.clear()
        self._timer.stop()


_flash_manager: Optional[CellFlashManager] = None


def get_flash_manager(parent: Optional[QObject] = None) -> CellFlashManager:
    """دسترسی به نمونه یکتای CellFlashManager (Singleton سبک، بدون وابستگی سراسری)."""
    global _flash_manager
    if _flash_manager is None:
        _flash_manager = CellFlashManager(parent)
    return _flash_manager


class StrategyCellDelegate(QStyledItemDelegate):
    """
    نماینده رندر گرافیکی پیشرفته جدول:
    ۱. رسم نوار هیت‌مپ شفاف (Heatmap Bar) در ستون‌های سود/زیان — نرمال‌شده نسبت
       به بیشینه‌ی واقعی مقادیرِ همان اسکن (نه یک عدد ثابت حدس‌زده‌شده).
    ۲. انیمیشن محوشونده تغییر قیمت (Tick Flash) — کاملاً در لایه‌ی View، بدون
       تغییر داده‌ی مدل و بدون فایر شدن هیچ سیگنالی.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # همان Singleton سراسری؛ پاس دادن parent هزینه‌ای ندارد چون فقط بار اول
        # استفاده می‌شود (اگر MainWindow زودتر آن را ساخته باشد، همان برگردانده می‌شود).
        self._flash_manager = get_flash_manager(parent)
        self._heatmap_max_abs = _DEFAULT_HEATMAP_MAX_ABS

    def set_heatmap_scale(self, max_abs: float) -> None:
        """
        تنظیم بیشینه‌ی مقیاس نوار هیت‌مپ. باید بعد از هر populate_table با
        بیشینه‌ی |مقدار| واقعیِ ستون‌های سود/زیانِ همان اسکن فراخوانی شود
        (نه یک ثابت حدسی که برای مقیاس اشتباه کالیبره شده بود).
        """
        self._heatmap_max_abs = max(float(max_abs), 1e-6)

    def _item_for_index(self, index: QModelIndex) -> Optional[QTableWidgetItem]:
        """
        دلگیت روی خودِ QTableWidget ست می‌شود (رجوع کنید به main_window.py:
        table.setItemDelegate(StrategyCellDelegate(table)))، پس parent همان
        جدول است و می‌توانیم آیتم واقعی این ایندکس را از آن بگیریم.
        """
        table = self.parent()
        if table is None:
            return None
        try:
            return table.item(index.row(), index.column())
        except AttributeError:
            return None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        col = index.column()

        # ۱. نوار هیت‌مپ — زیر متن رسم می‌شود (قبل از super().paint)
        if col >= 7:
            val = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(val, (int, float)) and val != -999999999.0 and val != 0:
                rect = option.rect
                ratio = min(abs(val) / self._heatmap_max_abs, 1.0)
                bar_w = int(rect.width() * ratio * 0.8)

                bar_color = QColor(63, 185, 80, 45) if val > 0 else QColor(248, 81, 73, 45)
                bar_rect = QRectF(rect.x() + 4, rect.y() + 4, bar_w, rect.height() - 8)
                painter.fillRect(bar_rect, bar_color)

        # رسم پیش‌فرض سلول (پس‌زمینه‌ی معمولی/انتخاب‌شده، متن). چون BackgroundRole
        # هیچ‌جا روی مدل ست نمی‌شود، این مرحله چیزی اضافه بر رنگ‌آمیزی نمی‌کند.
        super().paint(painter, option, index)

        # ۲. فلش تغییر قیمت — روی متن، دقیقاً یک‌بار رنگ‌آمیزی می‌شود
        item = self._item_for_index(index)
        flash_color = self._flash_manager.current_color(item)
        if flash_color is not None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.fillRect(option.rect, flash_color)

        painter.restore()