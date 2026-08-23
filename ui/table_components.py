# ui/table_components.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import time
import logging
from typing import Any, List, Dict, Optional, Tuple, Union

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex,
    QSortFilterProxyModel, QTimer, Signal, QRectF
)
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.TableComponents")

FLASH_DURATION_SEC = 0.6


class StrategyCellDelegate(QStyledItemDelegate):
    """
    نماینده رندر گرافیکی پیشرفته جدول:
    ۱. رسم نوار هیت‌مپ شفاف (Heatmap Bar) در ستون‌های سود/زیان
    ۲. رسم میکروچارت اسپارک‌لاین در ستون استراتژی
    ۳. انیمیشن محوشونده تغییر قیمت (Tick Flashing)
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        col = index.column()

        # ۱. رسم نوار هیت‌مپ شفاف در ستون‌های سود و زیان (ستون‌های شماره ۷ به بعد)
        if col >= 7:
            val = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(val, (int, float)) and val != -999999999.0 and val != 0:
                rect = option.rect
                max_norm = 10000000.0  # نرمال‌سازی بصری
                ratio = min(abs(val) / max_norm, 1.0)
                bar_w = int(rect.width() * ratio * 0.8)

                bar_color = QColor(63, 185, 80, 45) if val > 0 else QColor(248, 81, 73, 45)
                bar_rect = QRectF(rect.x() + 4, rect.y() + 4, bar_w, rect.height() - 8)
                painter.fillRect(bar_rect, bar_color)

        super().paint(painter, option, index)

        # ۲. پویانمایی فلش قیمت (Tick Flashing)
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(bg_color, QColor) and bg_color.isValid() and bg_color.alpha() > 0:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.fillRect(option.rect, bg_color)

        painter.restore()