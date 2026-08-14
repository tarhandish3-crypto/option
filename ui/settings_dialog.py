# ui/settings_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ تنظیمات جامع سیستم (Settings Dialog)
مدیریت پارامترهای API، پارامترهای پیش‌فرض اسکنر و تنظیمات عمومی UI.

این دیالوگ با config.py یکپارچه شده و تمام تنظیمات را از طریق
توابع config.get_ui_settings() و config.update_ui_settings() مدیریت می‌کند.
"""

import logging
import json
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

import config

logger = logging.getLogger("OptionScanner.UI.Settings")


class SettingsDialog(QDialog):
    """
    دیالوگ تنظیمات نرم‌افزار با قابلیت تب‌بندی، ذخیره‌سازی و مدیریت پروفایل‌ها

    Signals:
        settings_saved: سیگنال ارسال تنظیمات جدید پس از ذخیره
    """

    settings_saved = Signal(dict)

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تنظیمات سیستم")
        self.resize(650, 620)
        self.setMinimumSize(580, 550)
        self.setLayoutDirection(Qt.RightToLeft)

        # دریافت تنظیمات: اول از config_dict پاس شده، بعد از config.py
        if config_dict is not None:
            self.settings: Dict[str, Any] = config_dict.copy()
        elif hasattr(config, 'get_ui_settings'):
            self.settings = config.get_ui_settings()
        else:
            self.settings = self._get_default_settings()
        self._initial_settings = self.settings.copy()
        self._has_changes = False

        self._init_ui()
        self._load_settings_into_ui()
        self._update_preview()
        self._update_window_title()

        logger.info("⚙️ SettingsDialog initialized with config.py integration")

    # =============================================
    # ساخت UI اصلی
    # =============================================

    def _init_ui(self) -> None:
        """راه‌اندازی ساختار گرافیکی دیالوگ"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # ---------------------------------------------
        # بخش پروفایل‌ها
        # ---------------------------------------------
        profile_frame = QFrame()
        profile_frame.setStyleSheet("""
            QFrame {
                background-color: #f0f2f5;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        profile_layout = QHBoxLayout(profile_frame)
        profile_layout.addWidget(QLabel("📂 پروفایل:"))

        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(150)

        # بارگذاری لیست پروفایل‌ها
        profile_names = config.get_all_profiles() if hasattr(
            config, "get_all_profiles") else ["پیش‌فرض"]
        self.combo_profiles.addItems(profile_names)
        self.combo_profiles.addItem("سفارشی")
        self.combo_profiles.currentTextChanged.connect(self._load_profile)
        self.combo_profiles.setToolTip(
            "انتخاب پروفایل تنظیمات برای استراتژی‌های متفاوت.")
        profile_layout.addWidget(self.combo_profiles)

        self.btn_save_profile = QPushButton("💾 ذخیره")
        self.btn_save_profile.setToolTip(
            "ذخیره تنظیمات فعلی به عنوان پروفایل جدید")
        self.btn_save_profile.clicked.connect(self._save_profile)
        profile_layout.addWidget(self.btn_save_profile)

        self.btn_delete_profile = QPushButton("🗑️ حذف")
        self.btn_delete_profile.setToolTip("حذف پروفایل انتخاب‌شده")
        self.btn_delete_profile.clicked.connect(self._delete_profile)
        profile_layout.addWidget(self.btn_delete_profile)

        profile_layout.addStretch()

        self.lbl_changes = QLabel("")
        self.lbl_changes.setStyleSheet("color: #e67e22; font-weight: bold;")
        profile_layout.addWidget(self.lbl_changes)

        main_layout.addWidget(profile_frame)

        # ---------------------------------------------
        # ساخت تب‌ها
        # ---------------------------------------------
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(QFont("Vazir", 9))
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 10px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 4px;
                border-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #4a6fa5;
                color: white;
            }
        """)

        self.tab_api = self._create_api_tab()
        self.tab_scanner = self._create_scanner_tab()
        self.tab_general = self._create_general_tab()
        self.tab_advanced = self._create_advanced_tab()
        self.tab_preview = self._create_preview_tab()

        self.tab_widget.addTab(self.tab_api, "🌐 شبکه و API")
        self.tab_widget.addTab(self.tab_scanner, "📊 محاسبات اسکنر")
        self.tab_widget.addTab(self.tab_general, "⚙️ عمومی و UI")
        self.tab_widget.addTab(self.tab_advanced, "🔧 پیشرفته")
        self.tab_widget.addTab(self.tab_preview, "📋 پیش‌نمایش")

        main_layout.addWidget(self.tab_widget)

        # ---------------------------------------------
        # دکمه‌های پایین دیالوگ
        # ---------------------------------------------
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults |
            QDialogButtonBox.StandardButton.Reset,
            Qt.Orientation.Horizontal, self
        )

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("💾 ذخیره تنظیمات")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 6px 16px;"
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        self.button_box.button(
            QDialogButtonBox.StandardButton.RestoreDefaults).setText("🔄 پیش‌فرض اولیه")
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).setText(
            "↩️ بازگشت به قبلی")

        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._restore_defaults)
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self._reset_to_previous)

        main_layout.addWidget(self.button_box)

    # =============================================
    # ساخت تب‌ها
    # =============================================

    def _create_api_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("پارامترهای درخواست‌های شبکه")
        form_layout = QFormLayout(group)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.spin_api_timeout = QSpinBox()
        self.spin_api_timeout.setRange(3, 60)
        self.spin_api_timeout.setSuffix(" ثانیه")
        self.spin_api_timeout.valueChanged.connect(self._on_setting_changed)
        form_layout.addRow("⏱️ زمان وقفه (Timeout):", self.spin_api_timeout)

        self.spin_max_retries = QSpinBox()
        self.spin_max_retries.setRange(1, 10)
        self.spin_max_retries.valueChanged.connect(self._on_setting_changed)
        form_layout.addRow("🔄 تعداد تلاش مجدد:", self.spin_max_retries)

        self.spin_request_delay = QSpinBox()
        self.spin_request_delay.setRange(0, 5000)
        self.spin_request_delay.setSingleStep(50)
        self.spin_request_delay.setSuffix(" میلی‌ثانیه")
        self.spin_request_delay.valueChanged.connect(self._on_setting_changed)
        form_layout.addRow("⏳ تاخیر بین درخواست‌ها:", self.spin_request_delay)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_scanner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # گروه ۱: بازار
        group_market = QGroupBox("پارامترهای پایه بازار")
        form_market = QFormLayout(group_market)
        form_market.setSpacing(12)

        self.spin_rf_rate = QDoubleSpinBox()
        self.spin_rf_rate.setRange(0.0, 100.0)
        self.spin_rf_rate.setSingleStep(0.5)
        self.spin_rf_rate.setSuffix(" ٪")
        self.spin_rf_rate.valueChanged.connect(self._on_setting_changed)
        form_market.addRow("💰 نرخ سود بدون ریسک:", self.spin_rf_rate)

        self.spin_min_open_int = QSpinBox()
        self.spin_min_open_int.setRange(0, 1_000_000)
        self.spin_min_open_int.setSingleStep(50)
        self.spin_min_open_int.valueChanged.connect(self._on_setting_changed)
        form_market.addRow("📊 حداقل موقعیت باز:", self.spin_min_open_int)

        layout.addWidget(group_market)

        # گروه ۲: سررسید
        group_maturity = QGroupBox("📅 محدوده روز تا سررسید (DTE)")
        form_maturity = QFormLayout(group_maturity)
        form_maturity.setSpacing(12)

        self.spin_min_dte = QSpinBox()
        self.spin_min_dte.setRange(0, 365)
        self.spin_min_dte.valueChanged.connect(self._on_setting_changed)
        form_maturity.addRow("📅 حداقل روز تا سررسید:", self.spin_min_dte)

        self.spin_max_dte = QSpinBox()
        self.spin_max_dte.setRange(1, 1000)
        self.spin_max_dte.valueChanged.connect(self._on_setting_changed)
        form_maturity.addRow("📅 حداکثر روز تا سررسید:", self.spin_max_dte)

        layout.addWidget(group_maturity)

        # گروه ۳: گام نوسان‌پذیری
        group_steps = QGroupBox("📈 تنظیمات گام نمونه‌برداری نوسان‌پذیری")
        form_steps = QFormLayout(group_steps)
        form_steps.setSpacing(12)

        self.spin_vol_step = QDoubleSpinBox()
        self.spin_vol_step.setRange(0.5, 20.0)
        self.spin_vol_step.setSingleStep(0.5)
        self.spin_vol_step.setSuffix(" ٪")
        self.spin_vol_step.valueChanged.connect(self._on_setting_changed)
        form_steps.addRow("📈 اندازه گام:", self.spin_vol_step)

        vol_range_layout = QHBoxLayout()
        self.spin_vol_min = QDoubleSpinBox()
        self.spin_vol_min.setRange(-90.0, 0.0)
        self.spin_vol_min.setSuffix(" ٪")
        self.spin_vol_min.valueChanged.connect(self._on_setting_changed)

        self.spin_vol_max = QDoubleSpinBox()
        self.spin_vol_max.setRange(0.0, 300.0)
        self.spin_vol_max.setSuffix(" ٪")
        self.spin_vol_max.valueChanged.connect(self._on_setting_changed)

        vol_range_layout.addWidget(QLabel("از:"))
        vol_range_layout.addWidget(self.spin_vol_min)
        vol_range_layout.addWidget(QLabel("تا:"))
        vol_range_layout.addWidget(self.spin_vol_max)

        form_steps.addRow("📊 دامنه نمونه‌برداری:", vol_range_layout)
        layout.addWidget(group_steps)

        layout.addStretch()
        return widget

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group_ui = QGroupBox("🎨 پوسته و به‌روزرسانی")
        form_ui = QFormLayout(group_ui)
        form_ui.setSpacing(12)

        self.chk_auto_refresh = QCheckBox(
            "فعال‌سازی به‌روزرسانی دوره‌ای خودکار")
        self.chk_auto_refresh.stateChanged.connect(self._on_setting_changed)
        form_ui.addRow(self.chk_auto_refresh)

        self.spin_refresh_interval = QSpinBox()
        self.spin_refresh_interval.setRange(5, 3600)
        self.spin_refresh_interval.setSuffix(" ثانیه")
        self.spin_refresh_interval.valueChanged.connect(
            self._on_setting_changed)
        form_ui.addRow("⏱️ بازه به‌روزرسانی:", self.spin_refresh_interval)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(
            ["تاریک (Dark)", "روشن (Light)", "سیستم (System)"])
        self.combo_theme.currentTextChanged.connect(self._on_setting_changed)
        form_ui.addRow("🎨 پوسته برنامه:", self.combo_theme)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log_level.currentTextChanged.connect(
            self._on_setting_changed)
        form_ui.addRow("📝 سطح لاگ‌گیری:", self.combo_log_level)

        layout.addWidget(group_ui)

        group_path = QGroupBox("📁 مسیرهای ذخیره‌سازی")
        form_path = QHBoxLayout(group_path)

        self.txt_export_dir = QLineEdit()
        self.txt_export_dir.textChanged.connect(self._on_setting_changed)

        self.btn_browse_dir = QPushButton("📁 انتخاب پوشه")
        self.btn_browse_dir.clicked.connect(self._browse_export_directory)

        form_path.addWidget(self.txt_export_dir)
        form_path.addWidget(self.btn_browse_dir)

        layout.addWidget(group_path)
        layout.addStretch()
        return widget

    def _create_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group_advanced = QGroupBox("🔧 تنظیمات پیشرفته")
        form_advanced = QFormLayout(group_advanced)
        form_advanced.setSpacing(12)

        self.chk_parallel = QCheckBox("فعال‌سازی پردازش موازی")
        self.chk_parallel.stateChanged.connect(self._on_setting_changed)
        form_advanced.addRow(self.chk_parallel)

        self.spin_max_workers = QSpinBox()
        self.spin_max_workers.setRange(1, 16)
        self.spin_max_workers.valueChanged.connect(self._on_setting_changed)
        form_advanced.addRow("⚡ تعداد پردازش‌گرها:", self.spin_max_workers)

        self.chk_cache = QCheckBox("فعال‌سازی کش داده")
        self.chk_cache.stateChanged.connect(self._on_setting_changed)
        form_advanced.addRow(self.chk_cache)

        self.spin_cache_ttl = QSpinBox()
        self.spin_cache_ttl.setRange(10, 3600)
        self.spin_cache_ttl.setSuffix(" ثانیه")
        self.spin_cache_ttl.valueChanged.connect(self._on_setting_changed)
        form_advanced.addRow("⏱️ مدت اعتبار کش:", self.spin_cache_ttl)

        layout.addWidget(group_advanced)
        layout.addStretch()
        return widget

    def _create_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.preview_browser = QTextEdit()
        self.preview_browser.setReadOnly(True)
        self.preview_browser.setFont(QFont("Vazir", 9))
        layout.addWidget(self.preview_browser)
        return widget

    # =============================================
    # متدهای بارگذاری، استخراج و همگام‌سازی
    # =============================================

    def _load_settings_into_ui(self) -> None:
        """مقداردهی کامل تمام ویجت‌ها از دیکشنری settings"""
        # API
        self.spin_api_timeout.setValue(self.settings.get("api_timeout", 10))
        self.spin_max_retries.setValue(self.settings.get("api_max_retries", 3))
        self.spin_request_delay.setValue(
            self.settings.get("request_delay_ms", 200))

        # Scanner
        rf_rate = self.settings.get("risk_free_rate", 0.30)
        self.spin_rf_rate.setValue(
            rf_rate * 100 if rf_rate <= 1.0 else rf_rate)
        self.spin_min_open_int.setValue(
            self.settings.get("min_open_interest", 100))
        self.spin_min_dte.setValue(
            self.settings.get("min_days_to_maturity", 2))
        self.spin_max_dte.setValue(
            self.settings.get("max_days_to_maturity", 365))
        self.spin_vol_step.setValue(
            self.settings.get("volatility_step_percent", 5.0))
        self.spin_vol_min.setValue(
            self.settings.get("volatility_range_min", -50.0))
        self.spin_vol_max.setValue(
            self.settings.get("volatility_range_max", 50.0))

        # General
        self.chk_auto_refresh.setChecked(
            self.settings.get("auto_refresh_enabled", True))
        self.spin_refresh_interval.setValue(
            self.settings.get("auto_refresh_interval_sec", 60))

        theme = self.settings.get("theme", "تاریک (Dark)")
        idx = self.combo_theme.findText(theme)
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)

        log_lvl = self.settings.get("log_level", "INFO")
        idx_log = self.combo_log_level.findText(log_lvl)
        if idx_log >= 0:
            self.combo_log_level.setCurrentIndex(idx_log)

        self.txt_export_dir.setText(self.settings.get(
            "export_dir", str(Path.home() / "OptionScanner_Exports")))

        # Advanced
        self.chk_parallel.setChecked(self.settings.get(
            "enable_parallel_processing", True))
        self.spin_max_workers.setValue(
            self.settings.get("max_parallel_workers", 4))
        self.chk_cache.setChecked(self.settings.get("cache_enabled", True))
        self.spin_cache_ttl.setValue(
            self.settings.get("cache_ttl_seconds", 300))

    def _get_settings_from_ui(self) -> Dict[str, Any]:
        """استخراج وضعیت فعلی ویجت‌ها"""
        return {
            "api_timeout": self.spin_api_timeout.value(),
            "api_max_retries": self.spin_max_retries.value(),
            "request_delay_ms": self.spin_request_delay.value(),
            "risk_free_rate": round(self.spin_rf_rate.value() / 100.0, 4),
            "min_open_interest": self.spin_min_open_int.value(),
            "min_days_to_maturity": self.spin_min_dte.value(),
            "max_days_to_maturity": self.spin_max_dte.value(),
            "volatility_step_percent": self.spin_vol_step.value(),
            "volatility_range_min": self.spin_vol_min.value(),
            "volatility_range_max": self.spin_vol_max.value(),
            "auto_refresh_enabled": self.chk_auto_refresh.isChecked(),
            "auto_refresh_interval_sec": self.spin_refresh_interval.value(),
            "theme": self.combo_theme.currentText(),
            "log_level": self.combo_log_level.currentText(),
            "export_dir": self.txt_export_dir.text().strip(),
            "enable_parallel_processing": self.chk_parallel.isChecked(),
            "max_parallel_workers": self.spin_max_workers.value(),
            "cache_enabled": self.chk_cache.isChecked(),
            "cache_ttl_seconds": self.spin_cache_ttl.value()
        }

    # =============================================
    # متدهای مدیریت وضعیت و رویدادها
    # =============================================

    def _on_setting_changed(self) -> None:
        """تشخیص تغییرات"""
        current = self._get_settings_from_ui()
        self._has_changes = (current != self._initial_settings)
        self._update_window_title()
        self._update_preview()

    def _update_window_title(self) -> None:
        title = "تنظیمات سیستم"
        if self._has_changes:
            title += " * (تغییرات اعمال‌نشده)"
            self.lbl_changes.setText("⚠️ تغییرات ذخیره‌نشده")
        else:
            self.lbl_changes.setText("")
        self.setWindowTitle(title)

    def _update_preview(self) -> None:
        settings = self._get_settings_from_ui()
        preview_text = "📋 **خلاصه تنظیمات فعلی UI**:\n\n"
        for k, v in settings.items():
            preview_text += f"• **{k}**: {v}\n"
        self.preview_browser.setText(preview_text)

    def _browse_export_directory(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "انتخاب پوشه پیش‌فرض خروجی‌ها", self.txt_export_dir.text()
        )
        if dir_path:
            self.txt_export_dir.setText(dir_path)

    def _load_profile(self, profile_name: str) -> None:
        if not profile_name or profile_name == "سفارشی":
            return
        try:
            if hasattr(config, "apply_profile"):
                updated = config.apply_profile(profile_name)
                self.settings = updated.to_dict() if hasattr(updated, "to_dict") else updated
            self._load_settings_into_ui()
            self._on_setting_changed()
            logger.info(f"📂 Profile '{profile_name}' applied.")
        except Exception as e:
            logger.error(f"Failed to load profile {profile_name}: {e}")

    def _save_profile(self) -> None:
        profile_name, ok = QInputDialog.getText(
            self, "ذخیره پروفایل", "نام پروفایل جدید:")
        if ok and profile_name.strip():
            if hasattr(config, "save_custom_profile"):
                config.save_custom_profile(
                    profile_name.strip(), self._get_settings_from_ui())
                if self.combo_profiles.findText(profile_name) == -1:
                    self.combo_profiles.addItem(profile_name)
                self.combo_profiles.setCurrentText(profile_name)

    def _delete_profile(self) -> None:
        profile_name = self.combo_profiles.currentText()
        if profile_name in ["پیش‌فرض", "سفارشی"]:
            QMessageBox.warning(
                self, "خطا", "امکان حذف این پروفایل وجود ندارد.")
            return
        if hasattr(config, "delete_custom_profile"):
            config.delete_custom_profile(profile_name)
            idx = self.combo_profiles.findText(profile_name)
            if idx >= 0:
                self.combo_profiles.removeItem(idx)

    def _reset_to_previous(self) -> None:
        self.settings = self._initial_settings.copy()
        self._load_settings_into_ui()
        self._on_setting_changed()

    def _restore_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "بازنشانی", "آیا می‌خواهید تنظیمات به پیش‌فرض اولیه برگردند؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(config, "get_default_settings"):
                self.settings = config.get_default_settings()
            else:
                self.settings = self._get_default_settings()
            self._load_settings_into_ui()
            self._on_setting_changed()

    @staticmethod
    def _get_default_settings() -> Dict[str, Any]:
        """مقادیر پیش‌فرض در صورت عدم وجود در config"""
        return {
            "api_timeout": 10,
            "api_max_retries": 3,
            "request_delay_ms": 200,
            "risk_free_rate": 0.24,
            "min_open_interest": 50,
            "min_days_to_maturity": 2,
            "max_days_to_maturity": 365,
            "volatility_step_percent": 5.0,
            "volatility_range_min": -45.0,
            "volatility_range_max": 45.0,
            "auto_refresh_enabled": False,
            "auto_refresh_interval_sec": 120,
            "theme": "روشن (Light)",
            "log_level": "INFO",
            "export_dir": str(Path.home() / "OptionScanner_Exports"),
            "enable_parallel_processing": False,
            "max_parallel_workers": 3,
            "cache_enabled": True,
            "cache_ttl_seconds": 6,
        }

    def get_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات نهایی برای استفاده در main_window"""
        return self._get_settings_from_ui()

    def _save_and_accept(self) -> None:
        if self.spin_min_dte.value() >= self.spin_max_dte.value():
            QMessageBox.warning(
                self, "خطا", "حداقل روز تا سررسید باید کمتر از حداکثر آن باشد.")
            self.tab_widget.setCurrentIndex(1)
            return

        new_settings = self._get_settings_from_ui()

        # ذخیره نهایی در config.py (در صورت وجود)
        if hasattr(config, "update_ui_settings"):
            config.update_ui_settings(new_settings)

        self.settings = new_settings
        self.settings_saved.emit(self.settings)
        logger.info("💾 Settings saved successfully")
        self.accept()
