# ui/widgets.py
# -*- coding: utf-8 -*-
"""ویجت‌های کوچک و قابل‌استفاده‌ی مجدد: کارت، تایل آماری، پیل وضعیت، چیپ فیلتر، دکمه‌ی آیکنی."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui.theme import repolish


class Card(QFrame):
    """کارت با گوشه‌ی گرد (استایل از QSS سراسری: QFrame#card)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("card")


def vsep() -> QFrame:
    frame = QFrame()
    frame.setObjectName("vsep")
    frame.setFixedWidth(1)
    return frame


def hsep() -> QFrame:
    frame = QFrame()
    frame.setObjectName("hsep")
    frame.setFixedHeight(1)
    return frame


class StatTile(QFrame):
    """تایل آماری: عنوان کوچک + مقدار پررنگ. tone: ok | er | wn | pr | ''"""

    def __init__(self, caption: str, value: str = "-", tone: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("statTile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._cap = QLabel(caption)
        self._cap.setObjectName("tileCaption")
        self._val = QLabel(value)
        self._val.setObjectName("tileValue")
        self._val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._cap.setAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter)
        self._val.setAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._cap)
        lay.addWidget(self._val)
        self.set_tone(tone)

    def set_value(self, text: str, tone: Optional[str] = None) -> None:
        self._val.setText(text)
        if tone is not None:
            self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self._val.setProperty("tone", tone)
        repolish(self._val)


class StatusPill(QLabel):
    """نشانگر وضعیت: state = idle | ok | err | warn"""

    def __init__(self, text: str = "", state: str = "idle", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.set_state(state)

    def set_state(self, state: str, text: Optional[str] = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("pill", state)
        repolish(self)


class FilterChip(QPushButton):
    """چیپ فیلتر (قابل کلیک). حالت فعال با property active."""

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setProperty("chip", True)
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", bool(active))
        repolish(self)


class IconButton(QPushButton):
    """دکمه‌ی مربعی آیکنی ۴۴×۴۴ (برای نوار ابزار)."""

    def __init__(self, tooltip: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("iconButton")
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


def set_role(button: QPushButton, role: str) -> None:
    """role: primary | success | danger | warning | '' (پیش‌فرض)"""
    button.setProperty("role", role)
    repolish(button)
