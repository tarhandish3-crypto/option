# ui/icons.py
# -*- coding: utf-8 -*-
"""
آیکون‌های SVG خطی (به‌جای ایموجی). بدون وابستگی جدید: QtSvg همراه PySide6.

استفاده:
    from ui import icons
    btn.setIcon(icons.icon("refresh", color="#8FB0FF", size=18))
    btn.setIcon(icons.themed_icon("refresh"))      # رنگ از تم فعلی
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

logger = logging.getLogger("OptionScanner.UI.Icons")

try:
    from PySide6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except ImportError:  # pragma: no cover
    QSvgRenderer = None  # type: ignore[misc, assignment]
    _HAS_SVG = False
    logger.warning("PySide6.QtSvg در دسترس نیست؛ آیکون‌های SVG خالی می‌مانند.")

# مسیرهای stroke-based روی بوم ۲۴×۲۴
_PATHS: Dict[str, str] = {
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "play": '<path d="M7 5l12 7-12 7z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "filter": '<path d="M4 5h16l-6 8v5l-4 2v-7z"/>',
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 3v3M12 18v3M3 12h3M18 12h3'
        'M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>'
    ),
    "chart": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 15l4-5 3 3 5-6"/>',
    "matrix": (
        '<rect x="4" y="4" width="7" height="7" rx="1.5"/>'
        '<rect x="13" y="4" width="7" height="7" rx="1.5"/>'
        '<rect x="4" y="13" width="7" height="7" rx="1.5"/>'
        '<rect x="13" y="13" width="7" height="7" rx="1.5"/>'
    ),
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2'
        'M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/>'
    ),
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "bolt": '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    "download": '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
}


def svg_markup(name: str, color: str = "#FFFFFF", stroke: float = 1.8) -> str:
    body = _PATHS.get(name, "")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def pixmap(name: str, color: str = "#FFFFFF", size: int = 18, dpr: float = 2.0) -> QPixmap:
    px = int(size * dpr)
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    if _HAS_SVG:
        renderer = QSvgRenderer(QByteArray(svg_markup(name, color).encode("utf-8")))
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = "#FFFFFF", size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def themed_icon(name: str, size: int = 18, tone: str = "prt") -> QIcon:
    from ui.theme import tokens
    return icon(name, tokens()[tone], size)


def write_png(name: str, color: str, size: int, filename: str) -> str:
    """برای QSS (image:url(...)) فایل PNG موقت می‌سازد و مسیر (با / ) را برمی‌گرداند."""
    if not _HAS_SVG:
        return ""
    folder = Path(tempfile.gettempdir()) / "option_scanner_ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    pixmap(name, color, size, dpr=2.0).save(str(path), "PNG")
    return path.as_posix()
