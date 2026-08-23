# ui/settings_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ تنظیمات جامع سیستم (Settings Dialog)
تمام عملیات ذخیره/بارگذاری و مدیریت پروفایل‌ها از طریق SettingsManager انجام می‌شود.
"""

import logging
from typing import Dict, Any, Optional

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
from ui import theme as ui_theme
import config

logger = logging.getLogger("OptionScanner.UI.Settings")


class SettingsDialog(QDialog):
    """
    دیالوگ تنظیمات با مدیریت کامل پروفایل از طریق SettingsManager.

    Signals:
        settings_saved: تنظیمات جدید پس از ذخیره ارسال می‌شود
    """

    settings_saved = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("تنظیمات برنامه")
        self.resize(700, 660)
        self.setMinimumSize(600, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # تنظیمات جاری از manager
        self._current_settings: Dict[str, Any] = settings_manager.get_active_settings()
        self._initial_settings: Dict[str, Any] = dict(self._current_settings)
        self._has_changes = False

        self._init_ui()
        self._apply_dialog_theme()
        self._refresh_profile_combo()
        self._load_settings_into_ui(self._current_settings)
        self._update_preview()
        self._update_title()

    # =====================================================
    # ساخت UI
    # =====================================================

    def _apply_dialog_theme(self) -> None:
        """اعمال استایل‌های وابسته به پوسته روی بخش‌های اختصاصی دیالوگ."""
        mode = ui_theme.current_mode() if hasattr(ui_theme, "current_mode") else "dark"
        if hasattr(self, "profile_frame") and hasattr(ui_theme, "get_dialog_profile_frame_style"):
            self.profile_frame.setStyleSheet(ui_theme.get_dialog_profile_frame_style(mode))
        if hasattr(self, "tab_widget") and hasattr(ui_theme, "get_dialog_tab_style"):
            self.tab_widget.setStyleSheet(ui_theme.get_dialog_tab_style(mode))
        if hasattr(self, "lbl_changes"):
            color = "#f0883e" if mode == "dark" else "#e67e22"
            self.lbl_changes.setStyleSheet(f"color:{color}; font-weight:bold;")
        if hasattr(self, "lbl_broker_info") and hasattr(ui_theme, "get_dialog_warning_banner_style"):
            self.lbl_broker_info.setStyleSheet(ui_theme.get_dialog_warning_banner_style(mode))

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # ── نوار پروفایل ──────────────────────────────
        profile_frame = QFrame()
        self.profile_frame = profile_frame
        profile_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        pl = QHBoxLayout(profile_frame)
        pl.setContentsMargins(8, 4, 8, 4)
        pl.setSpacing(8)

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
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 5px; padding: 6px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 6px 14px; margin-right: 2px; border-radius: 4px; font-weight: bold; }
            QTabBar::tab:selected { background: #1f6feb; color: white; }
        """)

        self.tab_widget.addTab(self._create_api_tab(),      "🌐 شبکه و API")
        self.tab_widget.addTab(self._create_scanner_tab(),  "📊 اسکنر و ماتریس سود")
        self.tab_widget.addTab(self._create_general_tab(),  "⚙️ عمومی و پوسته")
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
            "background:#238636; color:white; font-weight:bold; padding:6px 16px; border-radius:4px;"
        )
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("❌ انصراف")
        btn_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("🔄 بازگشت به پیش‌فرض کارخانه")
        btn_box.button(QDialogButtonBox.StandardButton.Reset).setText("↩️ لغو تغییرات")

        btn_box.accepted.connect(self._apply_and_close)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_factory_defaults)
        btn_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._discard_changes)

        main_layout.addWidget(btn_box)

    # ── تب‌ها ─────────────────────────────────────────

    def _create_api_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        grp = QGroupBox("پارامترهای شبکه و ارتباط با TSETMC")
        form = QFormLayout(grp)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_api_timeout = QSpinBox()
        self.spin_api_timeout.setRange(3, 120)
        self.spin_api_timeout.setSuffix(" ثانیه")
        self.spin_api_timeout.valueChanged.connect(self._on_changed)
        form.addRow("⏱️ Timeout درخواست‌ها:", self.spin_api_timeout)

        self.spin_max_retries = QSpinBox()
        self.spin_max_retries.setRange(1, 10)
        self.spin_max_retries.valueChanged.connect(self._on_changed)
        form.addRow("🔄 تعداد تلاش مجدد:", self.spin_max_retries)

        self.spin_request_delay = QSpinBox()
        self.spin_request_delay.setRange(0, 10000)
        self.spin_request_delay.setSingleStep(100)
        self.spin_request_delay.setSuffix(" ms")
        self.spin_request_delay.valueChanged.connect(self._on_changed)
        form.addRow("⏳ تأخیر بین درخواست‌ها:", self.spin_request_delay)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _create_scanner_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        grp1 = QGroupBox("پارامترهای مالی بازار")
        f1 = QFormLayout(grp1)
        f1.setSpacing(10)

        self.spin_rf_rate = QDoubleSpinBox()
        self.spin_rf_rate.setRange(0, 200)
        self.spin_rf_rate.setSingleStep(1)
        self.spin_rf_rate.setSuffix(" ٪")
        self.spin_rf_rate.setDecimals(2)
        self.spin_rf_rate.valueChanged.connect(self._on_changed)
        f1.addRow("💰 نرخ سود بدون ریسک سالانه:", self.spin_rf_rate)

        self.spin_min_open_int = QSpinBox()
        self.spin_min_open_int.setRange(0, 1_000_000)
        self.spin_min_open_int.setSingleStep(10)
        self.spin_min_open_int.valueChanged.connect(self._on_changed)
        f1.addRow("📊 حداقل موقعیت باز معتبر (OI):", self.spin_min_open_int)

        layout.addWidget(grp1)

        grp2 = QGroupBox("روزهای تا سررسید (DTE)")
        f2 = QFormLayout(grp2)
        f2.setSpacing(10)

        self.spin_min_dte = QSpinBox()
        self.spin_min_dte.setRange(0, 365)
        self.spin_min_dte.valueChanged.connect(self._on_changed)
        f2.addRow("📅 حداقل DTE:", self.spin_min_dte)

        self.spin_max_dte = QSpinBox()
        self.spin_max_dte.setRange(1, 1000)
        self.spin_max_dte.valueChanged.connect(self._on_changed)
        f2.addRow("📅 حداکثر DTE:", self.spin_max_dte)

        layout.addWidget(grp2)

        grp3 = QGroupBox("ماتریس دامنه تغییر قیمت دارایی پایه (محور P&L)")
        f3 = QFormLayout(grp3)
        f3.setSpacing(10)

        self.spin_vol_min = QDoubleSpinBox()
        self.spin_vol_min.setRange(-200, 0)
        self.spin_vol_min.setSuffix(" ٪")
        self.spin_vol_min.valueChanged.connect(self._on_changed)
        f3.addRow("📉 حداقل تغییر قیمت (سمت چپ):", self.spin_vol_min)

        self.spin_vol_max = QDoubleSpinBox()
        self.spin_vol_max.setRange(0, 200)
        self.spin_vol_max.setSuffix(" ٪")
        self.spin_vol_max.valueChanged.connect(self._on_changed)
        f3.addRow("📈 حداکثر تغییر قیمت (سمت راست):", self.spin_vol_max)

        self.spin_p_pts = QSpinBox()
        self.spin_p_pts.setRange(5, 51)
        self.spin_p_pts.setValue(21)
        self.spin_p_pts.valueChanged.connect(self._on_changed)
        f3.addRow("🔢 تعداد نقاط گام قیمت:", self.spin_p_pts)

        layout.addWidget(grp3)
        layout.addStretch()
        return w

    def _create_general_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        grp1 = QGroupBox("پوسته و نمایش")
        f1 = QFormLayout(grp1)
        f1.setSpacing(10)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["روشن (Light)", "تاریک (Dark)", "سیستم (System)"])
        self.combo_theme.currentTextChanged.connect(self._on_changed)
        f1.addRow("🎨 پوسته برنامه:", self.combo_theme)

        self.combo_layout_direction = QComboBox()
        self.combo_layout_direction.addItems(["راست‌چین (RTL)", "چپ‌چین (LTR)"])
        self.combo_layout_direction.currentTextChanged.connect(self._on_changed)
        f1.addRow("📐 جهت چیدمان:", self.combo_layout_direction)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log_level.currentTextChanged.connect(self._on_changed)
        f1.addRow("📝 سطح لاگ:", self.combo_log_level)

        self.chk_auto_refresh = QCheckBox("اسکن خودکار دوره‌ای")
        self.chk_auto_refresh.stateChanged.connect(self._on_changed)
        f1.addRow(self.chk_auto_refresh)

        self.spin_refresh_interval = QSpinBox()
        self.spin_refresh_interval.setRange(10, 3600)
        self.spin_refresh_interval.setSuffix(" ثانیه")
        self.spin_refresh_interval.valueChanged.connect(self._on_changed)
        f1.addRow("⏱️ فاصله اسکن خودکار:", self.spin_refresh_interval)

        layout.addWidget(grp1)

        grp2 = QGroupBox("📁 پوشه خروجی فایل‌های اکسل")
        fl = QHBoxLayout(grp2)
        self.txt_export_dir = QLineEdit()
        self.txt_export_dir.textChanged.connect(self._on_changed)
        self.btn_browse = QPushButton("📁 انتخاب...")
        self.btn_browse.clicked.connect(self._browse_dir)
        fl.addWidget(self.txt_export_dir)
        fl.addWidget(self.btn_browse)
        layout.addWidget(grp2)

        grp3 = QGroupBox("پردازش موازی و کش")
        f3 = QFormLayout(grp3)
        f3.setSpacing(10)

        self.chk_parallel = QCheckBox("فعال‌سازی پردازش موازی")
        self.chk_parallel.stateChanged.connect(self._on_changed)
        f3.addRow(self.chk_parallel)

        self.spin_max_workers = QSpinBox()
        self.spin_max_workers.setRange(1, 16)
        self.spin_max_workers.valueChanged.connect(self._on_changed)
        f3.addRow("⚡ تعداد Threads/Workers:", self.spin_max_workers)

        self.chk_cache = QCheckBox("فعال‌سازی کش داده‌های دریافتی")
        self.chk_cache.stateChanged.connect(self._on_changed)
        f3.addRow(self.chk_cache)

        self.spin_cache_ttl = QSpinBox()
        self.spin_cache_ttl.setRange(1, 3600)
        self.spin_cache_ttl.setSuffix(" ثانیه")
        self.spin_cache_ttl.valueChanged.connect(self._on_changed)
        f3.addRow("⏱️ مدت اعتبار کش (TTL):", self.spin_cache_ttl)

        layout.addWidget(grp3)
        layout.addStretch()
        return w

    def _create_bale_tab(self) -> QWidget:
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
        self.txt_bale_token.setPlaceholderText("Bot Token (مثلاً 123456:ABC-DEF...)")
        self.txt_bale_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_bale_token.textChanged.connect(self._on_changed)
        form.addRow("🔑 توکن ربات:", self.txt_bale_token)

        self.txt_bale_chat_id = QLineEdit()
        self.txt_bale_chat_id.setPlaceholderText("شناسه چت یا کانال (مثلاً 123456789)")
        self.txt_bale_chat_id.textChanged.connect(self._on_changed)
        form.addRow("💬 Chat ID:", self.txt_bale_chat_id)

        self.spin_bale_top_n = QSpinBox()
        self.spin_bale_top_n.setRange(1, 10)
        self.spin_bale_top_n.setValue(2)
        self.spin_bale_top_n.setSuffix(" فرصت اول")
        self.spin_bale_top_n.valueChanged.connect(self._on_changed)
        form.addRow("📊 تعداد ارسال در هر اسکن:", self.spin_bale_top_n)

        self.btn_test_bale = QPushButton("🧪 ارسال پیام تست به بله")
        self.btn_test_bale.clicked.connect(self._test_bale)
        self.btn_test_bale.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        form.addRow(self.btn_test_bale)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _test_bale(self) -> None:
        token = self.txt_bale_token.text().strip()
        chat_id = self.txt_bale_chat_id.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "هشدار", "لطفاً توکن ربات و Chat ID را وارد نمایید.")
            return

        try:
            from alerts.bale_notifier import send_message_to_bale
            result = send_message_to_bale(
                token, chat_id,
                "✅ پیام تست از اسکنر اختیار معامله — ارتباط با ربات بله برقرار است."
            )
            if result:
                QMessageBox.information(self, "موفق", "✅ پیام تست با موفقیت به بله ارسال شد.")
            else:
                QMessageBox.critical(self, "خطا", "❌ ارسال پیام ناموفق بود.\nلطفاً صحت توکن و Chat ID را بررسی کنید.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ارسال پیام به بله:\n{e}")

    def _create_broker_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        lbl_info = QLabel(
            "این اطلاعات برای ورود خودکار به سامانه خبرگان کارگزاری اومکس استفاده می‌شود.\n"
            "اطلاعات به صورت امن در فایل تنظیمات محلی شما ذخیره می‌گردند."
        )
        self.lbl_broker_info = lbl_info
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 8px; color: #8b949e;")
        layout.addWidget(lbl_info)

        grp = QGroupBox("🏦 اطلاعات ورود به سامانه آنلاین کارگزاری")
        form = QFormLayout(grp)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_broker_username = QLineEdit()
        self.txt_broker_username.setPlaceholderText("نام کاربری کارگزاری")
        self.txt_broker_username.textChanged.connect(self._on_changed)
        form.addRow("👤 نام کاربری:", self.txt_broker_username)

        self.txt_broker_password = QLineEdit()
        self.txt_broker_password.setPlaceholderText("رمز عبور")
        self.txt_broker_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_broker_password.textChanged.connect(self._on_changed)
        form.addRow("🔒 رمز عبور:", self.txt_broker_password)

        self.chk_broker_headless = QCheckBox("اجرا در پس‌زمینه بدون باز شدن مرورگر (Headless)")
        self.chk_broker_headless.stateChanged.connect(self._on_changed)
        form.addRow(self.chk_broker_headless)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _create_preview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
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

        # Scanner & Price Range
        rf = s.get("risk_free_rate", 0.24)
        self.spin_rf_rate.setValue(rf * 100 if rf <= 1.0 else rf)
        self.spin_min_open_int.setValue(s.get("min_open_interest", 50))
        self.spin_min_dte.setValue(s.get("min_days_to_maturity", 2))
        self.spin_max_dte.setValue(s.get("max_days_to_maturity", 365))

        p_range = s.get("price_range", {})
        self.spin_vol_min.setValue(p_range.get("min_percent", s.get("volatility_range_min", -45.0)))
        self.spin_vol_max.setValue(p_range.get("max_percent", s.get("volatility_range_max", 45.0)))
        self.spin_p_pts.setValue(p_range.get("num_points", 21))

        # General
        theme = s.get("theme", "روشن (پیش‌فرض)")
        idx = self.combo_theme.findText(theme)
        self.combo_theme.setCurrentIndex(idx if idx >= 0 else 0)

        layout_dir = s.get("layout_direction", "راست‌چین (RTL)")
        idx_dir = self.combo_layout_direction.findText(layout_dir)
        self.combo_layout_direction.setCurrentIndex(idx_dir if idx_dir >= 0 else 0)

        log_lvl = s.get("log_level", "INFO")
        idx_l = self.combo_log_level.findText(log_lvl)
        self.combo_log_level.setCurrentIndex(idx_l if idx_l >= 0 else 1)

        self.chk_auto_refresh.setChecked(s.get("auto_scan_enabled", s.get("auto_refresh_enabled", True)))
        self.spin_refresh_interval.setValue(s.get("auto_scan_interval", s.get("auto_refresh_interval_sec", 60)))
        self.txt_export_dir.setText(s.get("export_dir", str(getattr(config, "OUTPUT_DIR", ""))))

        # پردازش موازی و کش
        self.chk_parallel.setChecked(s.get("enable_parallel_processing", False))
        self.spin_max_workers.setValue(s.get("max_parallel_workers", 3))
        self.chk_cache.setChecked(s.get("cache_enabled", True))
        self.spin_cache_ttl.setValue(s.get("cache_ttl_seconds", 6))

        # Bale
        bale_dict = s.get("bale", {})
        self.chk_bale_enabled.setChecked(bale_dict.get("enabled", s.get("bale_enabled", False)))
        self.txt_bale_token.setText(bale_dict.get("bot_token", s.get("bale_bot_token", "")))
        self.txt_bale_chat_id.setText(bale_dict.get("chat_id", s.get("bale_chat_id", "")))
        self.spin_bale_top_n.setValue(bale_dict.get("top_n", s.get("bale_top_n", 2)))

        # Broker
        broker_dict = s.get("broker", {})
        self.txt_broker_username.setText(broker_dict.get("username", s.get("broker_username", "")))
        self.txt_broker_password.setText(broker_dict.get("password", s.get("broker_password", "")))
        self.chk_broker_headless.setChecked(broker_dict.get("headless", False))

    def _read_settings_from_ui(self) -> Dict[str, Any]:
        """خواندن مقادیر فعلی ویجت‌ها."""
        vol_min = self.spin_vol_min.value()
        vol_max = self.spin_vol_max.value()
        num_pts = self.spin_p_pts.value()

        return {
            "api_timeout":              self.spin_api_timeout.value(),
            "api_max_retries":          self.spin_max_retries.value(),
            "request_delay_ms":         self.spin_request_delay.value(),
            "risk_free_rate":           round(self.spin_rf_rate.value() / 100.0, 4),
            "min_open_interest":        self.spin_min_open_int.value(),
            "min_days_to_maturity":     self.spin_min_dte.value(),
            "max_days_to_maturity":     self.spin_max_dte.value(),
            "volatility_range_min":     vol_min,
            "volatility_range_max":     vol_max,
            "price_range": {
                "min_percent": vol_min,
                "max_percent": vol_max,
                "num_points": num_pts,
                "step_size": None,
                "labels_format": "{:.1f}%"
            },
            "theme":                    self.combo_theme.currentText(),
            "layout_direction":         self.combo_layout_direction.currentText(),
            "log_level":                self.combo_log_level.currentText(),
            "auto_scan_enabled":        self.chk_auto_refresh.isChecked(),
            "auto_scan_interval":       self.spin_refresh_interval.value(),
            "export_dir":               self.txt_export_dir.text().strip(),
            "enable_parallel_processing": self.chk_parallel.isChecked(),
            "max_parallel_workers":     self.spin_max_workers.value(),
            "cache_enabled":            self.chk_cache.isChecked(),
            "cache_ttl_seconds":        self.spin_cache_ttl.value(),
            "bale": {
                "enabled":   self.chk_bale_enabled.isChecked(),
                "bot_token": self.txt_bale_token.text().strip(),
                "chat_id":   self.txt_bale_chat_id.text().strip(),
                "top_n":     self.spin_bale_top_n.value()
            },
            "broker": {
                "broker_name": "خوارزمی / خبرگان",
                "username":    self.txt_broker_username.text().strip(),
                "password":    self.txt_broker_password.text(),
                "headless":    self.chk_broker_headless.isChecked()
            }
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
        active = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else "پیش‌فرض"
        title = f"تنظیمات سیستم — [{active}]"
        if self._has_changes:
            title += " *"
            self.lbl_changes.setText("⚠️ تغییرات ذخیره‌نشده")
        else:
            self.lbl_changes.setText("")
        self.setWindowTitle(title)

    def _update_preview(self) -> None:
        s = self._read_settings_from_ui()
        active_prof = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else "پیش‌فرض"
        lines = ["═" * 45, f"  پروفایل فعال: {active_prof}", "═" * 45]
        for k, v in s.items():
            if isinstance(v, dict):
                lines.append(f"  [{k}]:")
                for sub_k, sub_v in v.items():
                    lines.append(f"    - {sub_k}: {sub_v}")
            else:
                lines.append(f"  {k}: {v}")
        self.preview_text.setPlainText("\n".join(lines))

    # =====================================================
    # مدیریت پروفایل‌ها
    # =====================================================

    def _refresh_profile_combo(self) -> None:
        """بازسازی لیست پروفایل‌ها در ComboBox."""
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        
        default_name = getattr(settings_manager, "_DEFAULT_PROFILE_NAME", "پیش‌فرض")
        self.combo_profiles.addItem(default_name)
        
        if hasattr(settings_manager, "get_profile_names"):
            for name in settings_manager.get_profile_names():
                if name != default_name:
                    self.combo_profiles.addItem(name)

        active = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else default_name
        idx = self.combo_profiles.findText(active)
        self.combo_profiles.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_profiles.blockSignals(False)

        self.btn_delete_profile.setEnabled(active != default_name)

    def _on_profile_selected(self, name: str) -> None:
        if not name:
            return

        if self._has_changes:
            reply = QMessageBox.question(
                self,
                "تغییرات ذخیره‌نشده",
                "تغییرات فعلی ذخیره نشده‌اند.\nآیا می‌خواهید بدون ذخیره، پروفایل را تغییر دهید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                self._refresh_profile_combo()
                return

        if hasattr(settings_manager, "set_active_profile"):
            settings_manager.set_active_profile(name)
        
        new_settings = settings_manager.get_active_settings()
        self._current_settings = new_settings
        self._initial_settings = dict(new_settings)
        self._has_changes = False
        self._load_settings_into_ui(new_settings)
        self._update_title()
        default_name = getattr(settings_manager, "_DEFAULT_PROFILE_NAME", "پیش‌فرض")
        self.btn_delete_profile.setEnabled(name != default_name)
        logger.info(f"Profile '{name}' loaded.")

    def _save_profile(self) -> None:
        default_name = getattr(settings_manager, "_DEFAULT_PROFILE_NAME", "پیش‌فرض")
        current_name = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else default_name
        suggested = "" if current_name == default_name else current_name

        name, ok = QInputDialog.getText(
            self,
            "ذخیره پروفایل",
            "نام پروفایل را وارد کنید:",
            text=suggested,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if name == default_name:
            QMessageBox.warning(self, "نام نامعتبر", f"نام '{default_name}' رزرو است.")
            return

        if hasattr(settings_manager, "get_profile_names") and name in settings_manager.get_profile_names():
            reply = QMessageBox.question(
                self, "بازنویسی پروفایل",
                f"پروفایل '{name}' از قبل وجود دارد. بازنویسی شود؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        settings = self._read_settings_from_ui()
        if hasattr(settings_manager, "save_profile"):
            settings_manager.save_profile(name, settings)
        else:
            settings_manager.save_settings(settings)

        self._initial_settings = dict(settings)
        self._has_changes = False
        self._refresh_profile_combo()
        self._update_title()

        QMessageBox.information(self, "ذخیره شد", f"✅ پروفایل '{name}' با موفقیت ذخیره شد.")
        logger.info(f"Profile '{name}' saved.")

    def _delete_profile(self) -> None:
        default_name = getattr(settings_manager, "_DEFAULT_PROFILE_NAME", "پیش‌فرض")
        name = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else default_name
        if name == default_name:
            return

        reply = QMessageBox.question(
            self, "حذف پروفایل",
            f"آیا از حذف پروفایل '{name}' مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if hasattr(settings_manager, "delete_profile"):
            settings_manager.delete_profile(name)
        
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
        if self.spin_min_dte.value() >= self.spin_max_dte.value():
            QMessageBox.warning(self, "خطا", "حداقل DTE باید کمتر از حداکثر DTE باشد.")
            self.tab_widget.setCurrentIndex(1)
            return

        settings = self._read_settings_from_ui()
        default_name = getattr(settings_manager, "_DEFAULT_PROFILE_NAME", "پیش‌فرض")
        active = settings_manager.get_active_profile_name() if hasattr(settings_manager, "get_active_profile_name") else default_name

        if self._has_changes and active != default_name and hasattr(settings_manager, "save_profile"):
            settings_manager.save_profile(active, settings)
        else:
            settings_manager.save_settings(settings)

        self.settings_saved.emit(settings)
        logger.info(f"Settings applied -- profile: '{active}'")
        self.accept()

    def _discard_changes(self) -> None:
        self._has_changes = False
        self._load_settings_into_ui(self._initial_settings)
        self._update_title()

    def _restore_factory_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "بازگشت به پیش‌فرض کارخانه",
            "آیا می‌خواهید تمام پارامترها به مقادیر اولیه config بازگردانده شوند؟\n"
            "(پروفایل‌های ذخیره‌شده شما حذف نخواهند شد)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if hasattr(settings_manager, "restore_defaults"):
            settings_manager.restore_defaults()
            defaults = settings_manager.get_defaults()
        else:
            defaults = config.DEFAULT_SETTINGS
            settings_manager.save_settings(dict(defaults))

        self._current_settings = defaults
        self._initial_settings = dict(defaults)
        self._has_changes = False
        self._load_settings_into_ui(defaults)
        self._refresh_profile_combo()
        self._update_title()
        logger.info("Settings restored to factory defaults.")

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "انتخاب پوشه خروجی", self.txt_export_dir.text()
        )
        if path:
            self.txt_export_dir.setText(path)

    def get_settings(self) -> Dict[str, Any]:
        return self._read_settings_from_ui()