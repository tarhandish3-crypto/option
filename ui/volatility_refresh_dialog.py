# ui/volatility_refresh_dialog.py
# -*- coding: utf-8 -*-

"""
پنجره‌ی به‌روزرسانی داده‌ی نوسان تاریخی (VQ).

این پنجره فقط یک کار می‌کند: ساخت / به‌روزرسانی فایل
Historical_Volatility.xlsx.

کاربر با زدن دکمه‌ی «محاسبه نوسان تاریخی»، اسکریپت
0myStrategy/volatility_calculate.py را اجرا می‌کند.

طراحی:
    - بدون progress bar (طبق تصمیم)
    - پیغام ساده «لطفاً صبر کنید» حین اجرا
    - پیغام موفقیت با جزئیات
    - پیغام خطا + دکمه‌ی «تلاش مجدد»
    - بستن مسدود در حین اجرا
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGroupBox,
    QWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QCloseEvent

from ui import theme as ui_theme
from ui.workers import VolatilityRefreshWorker

logger = logging.getLogger("OptionScanner.UI.VolatilityRefreshDialog")


# ═══════════════════════════════════════════════════════════════
# ثابت‌های وضعیت
# ═══════════════════════════════════════════════════════════════

STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_SUCCESS = "success"
STATE_ERROR = "error"


# ═══════════════════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════════════════

class VolatilityRefreshDialog(QDialog):
    """
    پنجره‌ی به‌روزرسانی داده‌ی نوسان تاریخی.

    جریان:
        1. کاربر پنجره را باز می‌کند (وضعیت: آماده)
        2. روی «محاسبه نوسان تاریخی» می‌زند (وضعیت: در حال اجرا)
        3. پس از ۳۰-۶۰ ثانیه:
           - موفق → پیغام موفقیت
           - خطا → پیغام خطا + «تلاش مجدد»
        4. کاربر می‌بندد
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📊 به‌روزرسانی داده نوسان تاریخی (VQ)")
        self.setMinimumSize(560, 520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # وضعیت
        self._state: str = STATE_READY
        self._worker: Optional[VolatilityRefreshWorker] = None

        # تم
        self._theme_mode = ui_theme.current_mode() if hasattr(
            ui_theme, "current_mode"
        ) else "dark"

        self._init_ui()
        self._apply_initial_state()

    # ═══════════════════════════════════════════════════════════
    # ساخت UI
    # ═══════════════════════════════════════════════════════════

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ─── ۱. هدر توضیحات ─────────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            self._get_header_style()
        )
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(6)

        lbl_title = QLabel(
            "📊 به‌روزرسانی داده نوسان تاریخی (VQ)"
        )
        lbl_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #58a6ff;"
        )
        header_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "این پنجره فایل Historical_Volatility.xlsx را "
            "بازسازی می‌کند."
        )
        lbl_desc.setStyleSheet(
            "color: #8b949e; font-size: 11px;"
        )
        lbl_desc.setWordWrap(True)
        header_layout.addWidget(lbl_desc)

        main_layout.addWidget(header_frame)

        # ─── ۲. اطلاعات ─────────────────────────────────
        info_frame = QFrame()
        info_frame.setStyleSheet(self._get_info_style())
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        lbl_time = QLabel("⏱️ زمان تخمینی: ۳۰ تا ۶۰ ثانیه")
        lbl_time.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(lbl_time)

        lbl_items_title = QLabel("📋 چه چیزی محاسبه می‌شود؟")
        lbl_items_title.setStyleSheet("font-weight: bold; margin-top: 4px;")
        info_layout.addWidget(lbl_items_title)

        items = [
            "• نوسان تاریخی (HV_20, HV_60, HV_120)",
            "• روند بلندمدت (LongTrend)",
            "• آلفا و بازدهی نسبی (Alpha, RelativeReturn)",
            "• RSI و قدرت خریداران (RSI_14, BuyerStrength)",
            "• VolatilityQualityScore (VQ)",
        ]
        for item in items:
            lbl_item = QLabel(item)
            lbl_item.setStyleSheet(
                "color: #8b949e; font-size: 11px; padding-right: 8px;"
            )
            info_layout.addWidget(lbl_item)

        main_layout.addWidget(info_frame)

        # ─── ۳. دکمه‌ی محاسبه ────────────────────────────
        self.btn_calculate = QPushButton("🔄 محاسبه نوسان تاریخی")
        self.btn_calculate.setMinimumHeight(44)
        self.btn_calculate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_calculate.clicked.connect(self._on_calculate_clicked)
        main_layout.addWidget(self.btn_calculate)

        # ─── ۴. دکمه‌ی تلاش مجدد (فقط در حالت خطا) ────────
        self.btn_retry = QPushButton("🔁 تلاش مجدد")
        self.btn_retry.setMinimumHeight(36)
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self._on_calculate_clicked)
        self.btn_retry.setVisible(False)
        main_layout.addWidget(self.btn_retry)

        # ─── ۵. لیبل وضعیت ─────────────────────────────
        status_frame = QFrame()
        status_frame.setStyleSheet(self._get_status_style())
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_status = QLabel("آماده برای شروع")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            "font-weight: bold; font-size: 12px;"
        )
        status_layout.addWidget(self.lbl_status)

        main_layout.addWidget(status_frame)

        # ─── ۶. دکمه‌ی بستن ────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_close = QPushButton("❌ بستن")
        self.btn_close.setMinimumWidth(110)
        self.btn_close.setMinimumHeight(32)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        main_layout.addLayout(btn_row)

        # ─── ۷. اعمال استایل دکمه‌ها ────────────────────
        self._refresh_button_styles()

    # ═══════════════════════════════════════════════════════════
    # استایل‌ها
    # ═══════════════════════════════════════════════════════════

    def _get_header_style(self) -> str:
        if self._theme_mode == "dark":
            return """
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #1f6feb, stop:1 #0d419d);
                    border-radius: 8px;
                }
            """
        return """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0969da, stop:1 #0550ae);
                border-radius: 8px;
            }
        """

    def _get_info_style(self) -> str:
        if self._theme_mode == "dark":
            return """
                QFrame {
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                }
            """
        return """
            QFrame {
                background-color: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 8px;
            }
        """

    def _get_status_style(self) -> str:
        if self._theme_mode == "dark":
            return """
                QFrame {
                    background-color: #0d1117;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                }
            """
        return """
            QFrame {
                background-color: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 6px;
            }
        """

    def _refresh_button_styles(self) -> None:
        mode = self._theme_mode

        # دکمه‌ی محاسبه — برجسته
        if hasattr(ui_theme, "get_button_style"):
            self.btn_calculate.setStyleSheet(
                ui_theme.get_button_style(mode, role="primary")
            )
            self.btn_retry.setStyleSheet(
                ui_theme.get_button_style(mode, role="warning")
            )
            self.btn_close.setStyleSheet(
                ui_theme.get_button_style(mode, role="secondary")
            )

    # ═══════════════════════════════════════════════════════════
    # مدیریت وضعیت
    # ═══════════════════════════════════════════════════════════

    def _apply_initial_state(self) -> None:
        """وضعیت اولیه: آماده."""
        self._set_state(STATE_READY)

    def _set_state(self, state: str, message: str = "") -> None:
        """تنظیم وضعیت و به‌روزرسانی UI."""
        self._state = state

        if state == STATE_READY:
            self.lbl_status.setText(message or "آماده برای شروع")
            self.lbl_status.setStyleSheet(
                "font-weight: bold; font-size: 12px; color: #8b949e;"
            )
            self.btn_calculate.setEnabled(True)
            self.btn_calculate.setText("🔄 محاسبه نوسان تاریخی")
            self.btn_retry.setVisible(False)
            self.btn_close.setEnabled(True)

        elif state == STATE_RUNNING:
            self.lbl_status.setText("⏳ لطفاً صبر کنید... (۳۰-۶۰ ثانیه)")
            self.lbl_status.setStyleSheet(
                "font-weight: bold; font-size: 12px; color: #d29922;"
            )
            self.btn_calculate.setEnabled(False)
            self.btn_calculate.setText("⏳ در حال محاسبه...")
            self.btn_retry.setVisible(False)
            self.btn_close.setEnabled(False)

        elif state == STATE_SUCCESS:
            self.lbl_status.setText(message or "✅ با موفقیت انجام شد")
            self.lbl_status.setStyleSheet(
                "font-weight: bold; font-size: 12px; color: #3fb950;"
            )
            self.btn_calculate.setEnabled(True)
            self.btn_calculate.setText("🔄 محاسبه مجدد")
            self.btn_retry.setVisible(False)
            self.btn_close.setEnabled(True)

        elif state == STATE_ERROR:
            self.lbl_status.setText(message or "❌ خطا در محاسبه")
            self.lbl_status.setStyleSheet(
                "font-weight: bold; font-size: 12px; color: #f85149;"
            )
            self.btn_calculate.setEnabled(True)
            self.btn_calculate.setText("🔄 محاسبه نوسان تاریخی")
            self.btn_retry.setVisible(True)
            self.btn_close.setEnabled(True)

    # ═══════════════════════════════════════════════════════════
    # اسلات‌ها
    # ═══════════════════════════════════════════════════════════

    @Slot()
    def _on_calculate_clicked(self) -> None:
        """کاربر دکمه‌ی محاسبه را زد."""
        # جلوگیری از اجرای همزمان
        if self._worker is not None and self._worker.isRunning():
            return

        logger.info("Volatility refresh requested by user")
        self._set_state(STATE_RUNNING)

        # ساخت worker
        self._worker = VolatilityRefreshWorker(parent=self)
        self._worker.success.connect(self._on_worker_success)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    @Slot(dict)
    def _on_worker_success(self, data: dict) -> None:
        """کاربر موفق شد."""
        n_symbols = data.get("n_symbols", 0)
        duration = data.get("duration", 0.0)
        filepath = data.get("filepath", "")

        msg = (
            f"✅ نوسان تاریخی با موفقیت محاسبه شد.\n\n"
            f"• تعداد نمادها: {n_symbols}\n"
            f"• مدت اجرا: {duration:.1f} ثانیه\n"
            f"• فایل: {filepath}\n\n"
            f"حالا می‌توانید این پنجره را بسته و اسکن کنید."
        )

        self._set_state(STATE_SUCCESS, msg)
        logger.info(
            f"VQ refresh succeeded: {n_symbols} symbols, "
            f"{duration:.1f}s"
        )

    @Slot(str)
    def _on_worker_error(self, error_msg: str) -> None:
        """خطا در اجرا."""
        self._set_state(STATE_ERROR, f"❌ {error_msg}")
        logger.error(f"VQ refresh failed: {error_msg}")

    @Slot()
    def _on_worker_finished(self) -> None:
        """Worker تمام شد."""
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    # ═══════════════════════════════════════════════════════════
    # مدیریت بستن
    # ═══════════════════════════════════════════════════════════

    def closeEvent(self, event: QCloseEvent) -> None:
        """مدیریت بستن در حین اجرا."""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self,
                "لطفاً صبر کنید",
                "محاسبه نوسان در حال اجراست.\n\n"
                "لطفاً تا اتمام محاسبه (۳۰-۶۰ ثانیه) صبر کنید.",
            )
            event.ignore()
            return

        event.accept()

    def reject(self) -> None:
        """مدیریت رد کردن (Esc) در حین اجرا."""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self,
                "لطفاً صبر کنید",
                "محاسبه نوسان در حال اجراست.\n\n"
                "لطفاً تا اتمام محاسبه (۳۰-۶۰ ثانیه) صبر کنید.",
            )
            return

        super().reject()


__all__ = ["VolatilityRefreshDialog"]