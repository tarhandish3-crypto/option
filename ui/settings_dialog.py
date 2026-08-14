# ui/settings_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ تنظیمات جامع سیستم (Settings Dialog)
تمام عملیات ذخیره/بارگذاری از طریق SettingsManager انجام می‌شود.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QGroupBox, QFormLayout,
    QFileDialog, QMessageBox, QDialogButtonBox, QTextEdit,
    QInputDialog, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.settings_manager import settings_manager, _DEFAULT_PROFILE_NAME

logger = logging.getLogger("OptionScanner.UI.Settings")


class SettingsDialog(QDialog):
    """
    دیالوگ تنظیمات با مدیریت کامل پروفایل از طریق SettingsManager.

    Signals:
        settings_saved: تنظیمات جدید پس از ذخیره ارسال می‌شود
    """

    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تنظیمات سیستم")
        self.resize(680, 650)
        self.setMinimumSize(580, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # تنظیمات جاری از manager
        self._current_settings: Dict[str, Any] = settings_manager.get_active_settings()
        self._initial_settings: Dict[str, Any] = dict(self._current_settings)
        self._has_changes = False

        self._init_ui()
        self._refresh_profile_combo()
        self._load_settings_into_ui(self._current_settings)
        self._update_preview()
        self._update_title()

    # =====================================================
    # ساخت UI
    # =====================================================

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # ── نوار پروفایل ──────────────────────────────
        profile_frame = QFrame()
        profile_frame.setStyleSheet(
            "QFrame { background:#f0f2f5; border-radius:8px; padding:6px; }"
        )
        pl = QHBoxLayout(profile_frame)
        pl.setContentsMargins(8, 4, 8, 4)

        pl.addWidget(QLabel("📂 پروفایل فعال:"))

        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(160)
        self.combo_profiles.currentTextChanged.connect(self._on_profile_selected)
        pl.addWidget(self.combo_profiles)

        self.btn_save_profile = QPushButton("💾 ذخیره با نام...")
        self.btn_save_profile.setToolTip("ذخیره تنظیمات فعلی به عنوان پروفایل جدید یا بازنویسی")
        self.btn_save_profile.clicked.connect(self._save_profile)
        pl.addWidget(self.btn_save_profile)

        self.btn_delete_profile = QPushButton("🗑️ حذف")
        self.btn_delete_profile.setToolTip("حذف پروفایل انتخاب‌شده")
        self.btn_delete_profile.clicked.connect(self._delete_profile)
        pl.addWidget(self.btn_delete_profile)

        pl.addStretch()

        self.lbl_changes = QLabel("")
        self.lbl_changes.setStyleSheet("color:#e67e22; font-weight:bold;")
        pl.addWidget(self.lbl_changes)

        main_layout.addWidget(profile_frame)

        # ── تب‌ها ────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border:1px solid #d0d7de; border-radius:6px; padding:10px; }
            QTabBar::tab { padding:8px 16px; margin-right:4px; border-radius:4px; }
            QTabBar::tab:selected { background:#4a6fa5; color:white; }
        """)

        self.tab_widget.addTab(self._create_api_tab(),      "🌐 شبکه و API")
        self.tab_widget.addTab(self._create_scanner_tab(),  "📊 اسکنر")
        self.tab_widget.addTab(self._create_general_tab(),  "⚙️ عمومی")
        self.tab_widget.addTab(self._create_advanced_tab(), "🔧 پیشرفته")
        self.tab_widget.addTab(self._create_bale_tab(),     "📣 اعلان بله")
        self.tab_widget.addTab(self._create_broker_tab(),   "🏦 کارگزاری")
        self.tab_widget.addTab(self._create_preview_tab(),  "📋 پیش‌نمایش")
        main_layout.addWidget(self.tab_widget)

        # ── دکمه‌های پایین ───────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults |
            QDialogButtonBox.StandardButton.Reset,
            Qt.Orientation.Horizontal, self
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("💾 اعمال و بستن")
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background:#27ae60; color:white; font-weight:bold; padding:6px 16px;"
        )
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        btn_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("🔄 بازگشت به پیش‌فرض config.py")
        btn_box.button(QDialogButtonBox.StandardButton.Reset).setText("↩️ لغو تغییرات")

        btn_box.accepted.connect(self._apply_and_close)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._restore_factory_defaults)
        btn_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self._discard_changes)

        main_layout.addWidget(btn_box)

    # ── تب‌ها ─────────────────────────────────────────

    def _create_api_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)
        grp = QGroupBox("پارامترهای شبکه")
        form = QFormLayout(grp); form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_api_timeout = QSpinBox()
        self.spin_api_timeout.setRange(3, 120); self.spin_api_timeout.setSuffix(" ثانیه")
        self.spin_api_timeout.valueChanged.connect(self._on_changed)
        form.addRow("⏱️ Timeout:", self.spin_api_timeout)

        self.spin_max_retries = QSpinBox()
        self.spin_max_retries.setRange(1, 10)
        self.spin_max_retries.valueChanged.connect(self._on_changed)
        form.addRow("🔄 تلاش مجدد:", self.spin_max_retries)

        self.spin_request_delay = QSpinBox()
        self.spin_request_delay.setRange(0, 10000); self.spin_request_delay.setSingleStep(100)
        self.spin_request_delay.setSuffix(" ms")
        self.spin_request_delay.valueChanged.connect(self._on_changed)
        form.addRow("⏳ تأخیر بین درخواست:", self.spin_request_delay)

        layout.addWidget(grp); layout.addStretch()
        return w

    def _create_scanner_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)

        grp1 = QGroupBox("پارامترهای بازار")
        f1 = QFormLayout(grp1); f1.setSpacing(10)

        self.spin_rf_rate = QDoubleSpinBox()
        self.spin_rf_rate.setRange(0, 200); self.spin_rf_rate.setSingleStep(1)
        self.spin_rf_rate.setSuffix(" ٪"); self.spin_rf_rate.setDecimals(2)
        self.spin_rf_rate.valueChanged.connect(self._on_changed)
        f1.addRow("💰 نرخ بدون ریسک:", self.spin_rf_rate)

        self.spin_min_open_int = QSpinBox()
        self.spin_min_open_int.setRange(0, 1_000_000); self.spin_min_open_int.setSingleStep(10)
        self.spin_min_open_int.valueChanged.connect(self._on_changed)
        f1.addRow("📊 حداقل موقعیت باز:", self.spin_min_open_int)

        layout.addWidget(grp1)

        grp2 = QGroupBox("روزهای تا سررسید (DTE)")
        f2 = QFormLayout(grp2); f2.setSpacing(10)

        self.spin_min_dte = QSpinBox()
        self.spin_min_dte.setRange(0, 365)
        self.spin_min_dte.valueChanged.connect(self._on_changed)
        f2.addRow("📅 حداقل DTE:", self.spin_min_dte)

        self.spin_max_dte = QSpinBox()
        self.spin_max_dte.setRange(1, 1000)
        self.spin_max_dte.valueChanged.connect(self._on_changed)
        f2.addRow("📅 حداکثر DTE:", self.spin_max_dte)

        layout.addWidget(grp2)

        grp3 = QGroupBox("بازه تغییر قیمت برای P&L")
        f3 = QFormLayout(grp3); f3.setSpacing(10)

        self.spin_vol_min = QDoubleSpinBox()
        self.spin_vol_min.setRange(-200, 0); self.spin_vol_min.setSuffix(" ٪")
        self.spin_vol_min.valueChanged.connect(self._on_changed)
        f3.addRow("📉 حداقل درصد:", self.spin_vol_min)

        self.spin_vol_max = QDoubleSpinBox()
        self.spin_vol_max.setRange(0, 200); self.spin_vol_max.setSuffix(" ٪")
        self.spin_vol_max.valueChanged.connect(self._on_changed)
        f3.addRow("📈 حداکثر درصد:", self.spin_vol_max)

        layout.addWidget(grp3)
        layout.addStretch()
        return w

    def _create_general_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)

        grp1 = QGroupBox("UI و نمایش")
        f1 = QFormLayout(grp1); f1.setSpacing(10)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["روشن (Light)", "تاریک (Dark)", "سیستم (System)"])
        self.combo_theme.currentTextChanged.connect(self._on_changed)
        f1.addRow("🎨 پوسته:", self.combo_theme)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log_level.currentTextChanged.connect(self._on_changed)
        f1.addRow("📝 سطح لاگ:", self.combo_log_level)

        self.chk_auto_refresh = QCheckBox("اسکن خودکار دوره‌ای")
        self.chk_auto_refresh.stateChanged.connect(self._on_changed)
        f1.addRow(self.chk_auto_refresh)

        self.spin_refresh_interval = QSpinBox()
        self.spin_refresh_interval.setRange(30, 3600); self.spin_refresh_interval.setSuffix(" ثانیه")
        self.spin_refresh_interval.valueChanged.connect(self._on_changed)
        f1.addRow("⏱️ فاصله اسکن خودکار:", self.spin_refresh_interval)

        layout.addWidget(grp1)

        grp2 = QGroupBox("📁 پوشه خروجی اکسل")
        fl = QHBoxLayout(grp2)
        self.txt_export_dir = QLineEdit()
        self.txt_export_dir.textChanged.connect(self._on_changed)
        self.btn_browse = QPushButton("📁 انتخاب...")
        self.btn_browse.clicked.connect(self._browse_dir)
        fl.addWidget(self.txt_export_dir); fl.addWidget(self.btn_browse)
        layout.addWidget(grp2)

        layout.addStretch()
        return w

    def _create_advanced_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)
        grp = QGroupBox("پردازش موازی و کش")
        form = QFormLayout(grp); form.setSpacing(10)

        self.chk_parallel = QCheckBox("فعال‌سازی پردازش موازی")
        self.chk_parallel.stateChanged.connect(self._on_changed)
        form.addRow(self.chk_parallel)

        self.spin_max_workers = QSpinBox()
        self.spin_max_workers.setRange(1, 16)
        self.spin_max_workers.valueChanged.connect(self._on_changed)
        form.addRow("⚡ تعداد Workers:", self.spin_max_workers)

        self.chk_cache = QCheckBox("فعال‌سازی کش داده")
        self.chk_cache.stateChanged.connect(self._on_changed)
        form.addRow(self.chk_cache)

        self.spin_cache_ttl = QSpinBox()
        self.spin_cache_ttl.setRange(1, 3600); self.spin_cache_ttl.setSuffix(" ثانیه")
        self.spin_cache_ttl.valueChanged.connect(self._on_changed)
        form.addRow("⏱️ TTL کش:", self.spin_cache_ttl)

        layout.addWidget(grp); layout.addStretch()
        return w

    def _create_bale_tab(self) -> QWidget:
        """تب تنظیمات پیام‌رسان بله"""
        w = QWidget()
        layout = QVBoxLayout(w)

        grp = QGroupBox("📣 ارسال نتایج اسکن به پیام‌رسان بله")
        form = QFormLayout(grp)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.chk_bale_enabled = QCheckBox("فعال‌سازی ارسال اعلان به بله")
        self.chk_bale_enabled.stateChanged.connect(self._on_changed)
        form.addRow(self.chk_bale_enabled)

        self.txt_bale_token = QLineEdit()
        self.txt_bale_token.setPlaceholderText("token")
        self.txt_bale_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_bale_token.textChanged.connect(self._on_changed)
        form.addRow("🔑 توکن ربات:", self.txt_bale_token)

        self.txt_bale_chat_id = QLineEdit()
        self.txt_bale_chat_id.setPlaceholderText("@chat_id")
        self.txt_bale_chat_id.textChanged.connect(self._on_changed)
        form.addRow("💬 Chat ID:", self.txt_bale_chat_id)

        self.spin_bale_top_n = QSpinBox()
        self.spin_bale_top_n.setRange(1, 10)
        self.spin_bale_top_n.setValue(2)
        self.spin_bale_top_n.setSuffix(" سطر اول")
        self.spin_bale_top_n.valueChanged.connect(self._on_changed)
        form.addRow("📊 تعداد نتایج:", self.spin_bale_top_n)

        # دکمه تست
        self.btn_test_bale = QPushButton("🧪 ارسال پیام تست")
        self.btn_test_bale.clicked.connect(self._test_bale)
        self.btn_test_bale.setStyleSheet(
            "background-color: #2980b9; color: white; font-weight: bold;"
        )
        form.addRow(self.btn_test_bale)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _test_bale(self) -> None:
        """ارسال پیام تست به بله"""
        from alerts.bale_notifier import send_message_to_bale
        token = self.txt_bale_token.text().strip()
        chat_id = self.txt_bale_chat_id.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "هشدار", "توکن و Chat ID را وارد کنید.")
            return
        result = send_message_to_bale(
            token, chat_id,
            "✅ پیام تست از اسکنر اختیار معامله — اتصال برقرار است."
        )
        if result:
            QMessageBox.information(self, "موفق", "✅ پیام تست با موفقیت ارسال شد.")
        else:
            QMessageBox.critical(self, "خطا", "❌ ارسال پیام ناموفق بود.\nتوکن و Chat ID را بررسی کنید.")

    def _create_broker_tab(self) -> QWidget:
        """تب تنظیمات کارگزاری اومکس خبرگان"""
        w = QWidget()
        layout = QVBoxLayout(w)

        # لیبل توضیحی
        lbl_info = QLabel(
            "این اطلاعات برای ورود خودکار به سامانه خبرگان کارگزاری اومکس استفاده می‌شود.\n"
            "اطلاعات به صورت رمزشده در فایل تنظیمات محلی ذخیره می‌شوند."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(
            "background:#fff3cd; border:1px solid #ffc107; border-radius:6px;"
            " padding:10px; color:#856404;"
        )
        layout.addWidget(lbl_info)

        grp = QGroupBox("🏦 اطلاعات ورود به سامانه خبرگان کارگزاری اومکس")
        form = QFormLayout(grp)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_broker_username = QLineEdit()
        self.txt_broker_username.setPlaceholderText("نام کاربری")
        self.txt_broker_username.textChanged.connect(self._on_changed)
        form.addRow("👤 نام کاربری:", self.txt_broker_username)

        self.txt_broker_password = QLineEdit()
        self.txt_broker_password.setPlaceholderText("رمز عبور")
        self.txt_broker_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_broker_password.textChanged.connect(self._on_changed)
        form.addRow("🔒 رمز عبور:", self.txt_broker_password)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _create_preview_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Courier New", 9))
        layout.addWidget(self.preview_text)
        return w

    # =====================================================
    # بارگذاری / استخراج تنظیمات از/به ویجت‌ها
    # =====================================================

    def _load_settings_into_ui(self, s: Dict[str, Any]) -> None:
        """پر کردن ویجت‌ها از دیکشنری تنظیمات."""
        # API
        self.spin_api_timeout.setValue(s.get("api_timeout", 30))
        self.spin_max_retries.setValue(s.get("api_max_retries", 3))
        self.spin_request_delay.setValue(s.get("request_delay_ms", 5000))

        # Scanner
        rf = s.get("risk_free_rate", 0.24)
        self.spin_rf_rate.setValue(rf * 100 if rf <= 1.0 else rf)
        self.spin_min_open_int.setValue(s.get("min_open_interest", 50))
        self.spin_min_dte.setValue(s.get("min_days_to_maturity", 2))
        self.spin_max_dte.setValue(s.get("max_days_to_maturity", 365))
        self.spin_vol_min.setValue(s.get("volatility_range_min", -45.0))
        self.spin_vol_max.setValue(s.get("volatility_range_max", 45.0))

        # General
        theme = s.get("theme", "روشن (Light)")
        idx = self.combo_theme.findText(theme)
        self.combo_theme.setCurrentIndex(idx if idx >= 0 else 0)

        log_lvl = s.get("log_level", "INFO")
        idx_l = self.combo_log_level.findText(log_lvl)
        self.combo_log_level.setCurrentIndex(idx_l if idx_l >= 0 else 1)

        self.chk_auto_refresh.setChecked(s.get("auto_refresh_enabled", False))
        self.spin_refresh_interval.setValue(s.get("auto_refresh_interval_sec", 120))
        self.txt_export_dir.setText(s.get("export_dir", ""))

        # Advanced
        self.chk_parallel.setChecked(s.get("enable_parallel_processing", False))
        self.spin_max_workers.setValue(s.get("max_parallel_workers", 3))
        self.chk_cache.setChecked(s.get("cache_enabled", True))
        self.spin_cache_ttl.setValue(s.get("cache_ttl_seconds", 6))

        # Bale
        self.chk_bale_enabled.setChecked(s.get("bale_enabled", False))
        self.txt_bale_token.setText(s.get("bale_bot_token", ""))
        self.txt_bale_chat_id.setText(s.get("bale_chat_id", ""))
        self.spin_bale_top_n.setValue(s.get("bale_top_n", 2))

        # Broker
        self.txt_broker_username.setText(s.get("broker_username", ""))
        self.txt_broker_password.setText(s.get("broker_password", ""))

    def _read_settings_from_ui(self) -> Dict[str, Any]:
        """خواندن مقادیر فعلی ویجت‌ها."""
        return {
            "api_timeout":              self.spin_api_timeout.value(),
            "api_max_retries":          self.spin_max_retries.value(),
            "request_delay_ms":         self.spin_request_delay.value(),
            "risk_free_rate":           round(self.spin_rf_rate.value() / 100.0, 4),
            "min_open_interest":        self.spin_min_open_int.value(),
            "min_days_to_maturity":     self.spin_min_dte.value(),
            "max_days_to_maturity":     self.spin_max_dte.value(),
            "volatility_range_min":     self.spin_vol_min.value(),
            "volatility_range_max":     self.spin_vol_max.value(),
            "theme":                    self.combo_theme.currentText(),
            "log_level":                self.combo_log_level.currentText(),
            "auto_refresh_enabled":     self.chk_auto_refresh.isChecked(),
            "auto_refresh_interval_sec": self.spin_refresh_interval.value(),
            "export_dir":               self.txt_export_dir.text().strip(),
            "enable_parallel_processing": self.chk_parallel.isChecked(),
            "max_parallel_workers":     self.spin_max_workers.value(),
            "cache_enabled":            self.chk_cache.isChecked(),
            "cache_ttl_seconds":        self.spin_cache_ttl.value(),
            # Bale
            "bale_enabled":             self.chk_bale_enabled.isChecked(),
            "bale_bot_token":           self.txt_bale_token.text().strip(),
            "bale_chat_id":             self.txt_bale_chat_id.text().strip(),
            "bale_top_n":               self.spin_bale_top_n.value(),
            # Broker
            "broker_username":          self.txt_broker_username.text().strip(),
            "broker_password":          self.txt_broker_password.text(),
        }

    # =====================================================
    # مدیریت تغییرات و عنوان
    # =====================================================

    def _on_changed(self) -> None:
        current = self._read_settings_from_ui()
        self._has_changes = (current != self._initial_settings)
        self._update_title()
        self._update_preview()

    def _update_title(self) -> None:
        active = settings_manager.get_active_profile_name()
        title = f"تنظیمات سیستم — [{active}]"
        if self._has_changes:
            title += " *"
            self.lbl_changes.setText("⚠️ تغییرات ذخیره‌نشده")
        else:
            self.lbl_changes.setText("")
        self.setWindowTitle(title)

    def _update_preview(self) -> None:
        s = self._read_settings_from_ui()
        lines = ["═" * 40, f"  پروفایل فعال: {settings_manager.get_active_profile_name()}", "═" * 40]
        for k, v in s.items():
            lines.append(f"  {k}: {v}")
        self.preview_text.setPlainText("\n".join(lines))

    # =====================================================
    # مدیریت پروفایل‌ها
    # =====================================================

    def _refresh_profile_combo(self) -> None:
        """بازسازی لیست پروفایل‌ها در ComboBox."""
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        # اول 'پیش‌فرض' ثابت
        self.combo_profiles.addItem(_DEFAULT_PROFILE_NAME)
        # بعد پروفایل‌های کاربر
        for name in settings_manager.get_profile_names():
            self.combo_profiles.addItem(name)

        active = settings_manager.get_active_profile_name()
        idx = self.combo_profiles.findText(active)
        self.combo_profiles.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_profiles.blockSignals(False)

        # 'پیش‌فرض' قابل حذف نیست
        self.btn_delete_profile.setEnabled(active != _DEFAULT_PROFILE_NAME)

    def _on_profile_selected(self, name: str) -> None:
        """وقتی کاربر پروفایل دیگری انتخاب می‌کند."""
        if not name:
            return

        # اگر تغییر ذخیره‌نشده داریم، بپرس
        if self._has_changes:
            reply = QMessageBox.question(
                self,
                "تغییرات ذخیره‌نشده",
                "تغییرات فعلی ذخیره نشده‌اند.\nآیا می‌خواهید بدون ذخیره پروفایل را تغییر دهید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                # برگرد به پروفایل قبلی
                self._refresh_profile_combo()
                return

        settings_manager.set_active_profile(name)
        new_settings = settings_manager.get_active_settings()
        self._current_settings = new_settings
        self._initial_settings = dict(new_settings)
        self._has_changes = False
        self._load_settings_into_ui(new_settings)
        self._update_title()
        self.btn_delete_profile.setEnabled(name != _DEFAULT_PROFILE_NAME)
        logger.info(f"پروفایل '{name}' بارگذاری شد.")

    def _save_profile(self) -> None:
        """ذخیره تنظیمات فعلی با یک نام (جدید یا بازنویسی)."""
        current_name = settings_manager.get_active_profile_name()
        suggested = "" if current_name == _DEFAULT_PROFILE_NAME else current_name

        name, ok = QInputDialog.getText(
            self,
            "ذخیره پروفایل",
            "نام پروفایل را وارد کنید:",
            text=suggested,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if name == _DEFAULT_PROFILE_NAME:
            QMessageBox.warning(self, "نام نامعتبر",
                                f"نام '{_DEFAULT_PROFILE_NAME}' رزرو است.")
            return

        # اگر قبلاً وجود داشت، بپرس
        if name in settings_manager.get_profile_names():
            reply = QMessageBox.question(
                self, "بازنویسی پروفایل",
                f"پروفایل '{name}' از قبل وجود دارد. بازنویسی شود؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        settings = self._read_settings_from_ui()
        settings_manager.save_profile(name, settings)

        self._initial_settings = dict(settings)
        self._has_changes = False
        self._refresh_profile_combo()
        self._update_title()

        QMessageBox.information(self, "ذخیره شد",
                                f"✅ پروفایل '{name}' با موفقیت ذخیره شد.")
        logger.info(f"پروفایل '{name}' ذخیره شد.")

    def _delete_profile(self) -> None:
        name = settings_manager.get_active_profile_name()
        if name == _DEFAULT_PROFILE_NAME:
            return

        reply = QMessageBox.question(
            self, "حذف پروفایل",
            f"آیا از حذف پروفایل '{name}' مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        settings_manager.delete_profile(name)
        # بعد از حذف، پروفایل فعال به پیش‌فرض رفته
        new_settings = settings_manager.get_active_settings()
        self._current_settings = new_settings
        self._initial_settings = dict(new_settings)
        self._has_changes = False
        self._load_settings_into_ui(new_settings)
        self._refresh_profile_combo()
        self._update_title()

    # =====================================================
    # دکمه‌های پایین
    # =====================================================

    def _apply_and_close(self) -> None:
        """اعمال تنظیمات و بستن دیالوگ."""
        if self.spin_min_dte.value() >= self.spin_max_dte.value():
            QMessageBox.warning(self, "خطا",
                                "حداقل DTE باید کمتر از حداکثر DTE باشد.")
            self.tab_widget.setCurrentIndex(1)
            return

        settings = self._read_settings_from_ui()

        # اگر تغییری هست و پروفایل نامگذاری‌شده‌ای فعال است → بازنویسی خودکار
        active = settings_manager.get_active_profile_name()
        if self._has_changes and active != _DEFAULT_PROFILE_NAME:
            settings_manager.save_profile(active, settings)
        elif self._has_changes and active == _DEFAULT_PROFILE_NAME:
            # کاربر پیش‌فرض را تغییر داده — باید با نام ذخیره کند
            reply = QMessageBox.question(
                self,
                "ذخیره تغییرات",
                "شما تنظیمات پیش‌فرض را تغییر داده‌اید.\n"
                "برای ذخیره، باید یک نام پروفایل انتخاب کنید.\n\n"
                "آیا می‌خواهید تنظیمات را با نام جدید ذخیره کنید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_profile()
                return  # بعد از ذخیره، کاربر دوباره Ok می‌زند
            # اگر No: بدون ذخیره، فقط signal ارسال می‌کنیم

        self.settings_saved.emit(settings)
        logger.info(f"تنظیمات اعمال شد — پروفایل: '{settings_manager.get_active_profile_name()}'")
        self.accept()

    def _discard_changes(self) -> None:
        """لغو تغییرات و بازگشت به آنچه هنگام باز شدن دیالوگ بود."""
        self._has_changes = False
        self._load_settings_into_ui(self._initial_settings)
        self._update_title()

    def _restore_factory_defaults(self) -> None:
        """بازگشت کامل به مقادیر config.py (بدون حذف پروفایل‌های ذخیره‌شده)."""
        reply = QMessageBox.question(
            self,
            "بازگشت به پیش‌فرض",
            "تنظیمات به مقادیر اولیه config.py بازگردانده می‌شود.\n"
            "پروفایل‌های ذخیره‌شده شما حذف نخواهند شد.\n\n"
            "ادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        settings_manager.restore_defaults()
        defaults = settings_manager.get_defaults()
        self._current_settings = defaults
        self._initial_settings = dict(defaults)
        self._has_changes = False
        self._load_settings_into_ui(defaults)
        self._refresh_profile_combo()
        self._update_title()
        logger.info("تنظیمات به پیش‌فرض config.py بازگردانده شد.")

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "انتخاب پوشه خروجی", self.txt_export_dir.text()
        )
        if path:
            self.txt_export_dir.setText(path)

    # =====================================================
    # API عمومی برای main_window
    # =====================================================

    def get_settings(self) -> Dict[str, Any]:
        """تنظیمات نهایی پس از بستن دیالوگ."""
        return self._read_settings_from_ui()
