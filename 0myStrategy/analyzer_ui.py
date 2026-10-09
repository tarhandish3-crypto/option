# 0myStrategy/analyzer_ui.py
# -*- coding: utf-8 -*-
"""
UI دسکتاپ تحلیلگر آپشن با PySide6

اجرا:
    python analyzer_ui.py

این فایل خودش:
1. Backend (api_server.py) را در Threadهای جداگانه اجرا می‌کند
2. UI را در Main Thread اجرا می‌کند
"""

import sys
import time
import requests
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# 🔧 مسیرها
# ═══════════════════════════════════════════════════════════════

current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent          # 0myStrategy/
root_dir = current_dir.parent                   # generate_strategyV4/

sys.path.insert(0, str(current_dir))            # برای import api_server
sys.path.insert(0, str(root_dir))

# ═══════════════════════════════════════════════════════════════
# Imports
# ═══════════════════════════════════════════════════════════════

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QSpinBox, QHeaderView, QMessageBox, QStatusBar, QFrame,
    QAbstractItemView, QButtonGroup, QFileDialog, QProgressBar,
    QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QColor, QFont, QBrush, QIcon, QPalette

# 🔗 Import Backend
from api_server import run_api_server_threaded


# ═══════════════════════════════════════════════════════════════
# تنظیمات
# ═══════════════════════════════════════════════════════════════

API_URL = "http://127.0.0.1:8001"
DEFAULT_REFRESH_SEC = 3          # ⏱ سریع‌تر (چون فقط یک استراتژی محاسبه می‌شود)
DEFAULT_STRATEGY = 'bull_call_spread'

COLORS = {
    'bg': '#0d1117',
    'bg_secondary': '#161b22',
    'bg_tertiary': '#21262d',
    'bg_hover': '#30363d',
    'border': '#30363d',
    'border_light': '#484f58',
    'text': '#c9d1d9',
    'text_muted': '#8b949e',
    'primary': '#58a6ff',
    'success': '#3fb950',
    'warning': '#d29922',
    'danger': '#f85149',
    'bull_call': '#3fb950',
    'covered_call': '#58a6ff',
    'long_call': '#d29922',
    'selected_bg': '#1f6feb',
}


# ═══════════════════════════════════════════════════════════════
# Workers (HTTP-based)
# ═══════════════════════════════════════════════════════════════

class FetchWorker(QThread):
    """
    خواندن موقعیت‌ها از API.
    
    نکته: چون Watcher فقط استراتژی فعال را محاسبه می‌کند،
    این Worker فقط همان را می‌خواند.
    """
    data_received = Signal(dict)
    error_occurred = Signal(str)

    def run(self):
        try:
            # خواندن /all-positions (که فقط استراتژی فعال داده دارد)
            r = requests.get(f"{API_URL}/all-positions", timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.data_received.emit(data)
            else:
                self.error_occurred.emit(f"HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("اتصال به API برقرار نیست")
        except Exception as e:
            self.error_occurred.emit(str(e))


class SendWorker(QThread):
    send_completed = Signal(bool, str)

    def __init__(self, strategy, index):
        super().__init__()
        self.strategy = strategy
        self.index = index

    def run(self):
        try:
            r = requests.post(
                f"{API_URL}/select-position",
                json={"strategy": self.strategy, "index": self.index},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                if "error" in data:
                    self.send_completed.emit(False, data["error"])
                else:
                    self.send_completed.emit(
                        True,
                        "موقعیت به کارگزاری ارسال شد!\nحالا در تب کارگزاری، Snippet آن را پر می‌کند."
                    )
            else:
                self.send_completed.emit(False, f"HTTP {r.status_code}")
        except Exception as e:
            self.send_completed.emit(False, str(e))


class BaleWorker(QThread):
    send_completed = Signal(bool, str)

    def __init__(self, message):
        super().__init__()
        self.message = message

    def run(self):
        try:
            r = requests.post(
                f"{API_URL}/send-to-bale",
                json={"message": self.message},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if "error" in data:
                    self.send_completed.emit(False, data["error"])
                else:
                    self.send_completed.emit(True, "پیام به بله ارسال شد")
            else:
                self.send_completed.emit(False, f"HTTP {r.status_code}")
        except Exception as e:
            self.send_completed.emit(False, str(e))


class SetStrategyWorker(QThread):
    """اطلاع دادن تغییر استراتژی به Backend"""
    strategy_set = Signal(bool, str)

    def __init__(self, strategy):
        super().__init__()
        self.strategy = strategy

    def run(self):
        try:
            r = requests.post(
                f"{API_URL}/set-active-strategy",
                json={"strategy": self.strategy},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                if "error" in data:
                    self.strategy_set.emit(False, data["error"])
                else:
                    self.strategy_set.emit(True, self.strategy)
            else:
                self.strategy_set.emit(False, f"HTTP {r.status_code}")
        except Exception as e:
            self.strategy_set.emit(False, str(e))


# ═══════════════════════════════════════════════════════════════
# جدول راست‌چین با انتخاب تکی
# ═══════════════════════════════════════════════════════════════

class RTLSingleSelectionTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)

        header = self.horizontalHeader()
        header.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.setStyleSheet(f"""
            QTableWidget {{
                background: {COLORS['bg_secondary']};
                color: {COLORS['text']};
                gridline-color: {COLORS['border']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-family: Tahoma;
                font-size: 12px;
                selection-background-color: {COLORS['selected_bg']};
                selection-color: white;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QTableWidget::item:selected {{
                background: {COLORS['selected_bg']};
                color: white;
            }}
            QHeaderView::section {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text']};
                padding: 10px 8px;
                border: none;
                border-left: 1px solid {COLORS['border']};
                border-bottom: 2px solid {COLORS['primary']};
                font-weight: bold;
                font-size: 12px;
            }}
            QHeaderView::section:first {{
                border-left: none;
            }}
        """)


# ═══════════════════════════════════════════════════════════════
# پنجره اصلی
# ═══════════════════════════════════════════════════════════════

class AnalyzerWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("📊 تحلیلگر آپشن بورس تهران")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.current_data = {}
        self.current_rows = []
        self.selected_row_idx = None
        self.active_strategy = DEFAULT_STRATEGY
        self.auto_timer = None
        self.fetch_worker = None
        self.send_worker = None
        self.bale_worker = None
        self.set_strategy_worker = None

        self.setStyleSheet(self._get_global_style())
        self._init_ui()
        self._start_auto_refresh()

    def _get_global_style(self):
        return f"""
            QMainWindow {{ background: {COLORS['bg']}; }}
            QWidget {{
                font-family: Tahoma, Segoe UI, Arial;
                color: {COLORS['text']};
            }}
            QLabel {{ color: {COLORS['text']}; }}
            QFrame {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            QGroupBox {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
                color: {COLORS['text']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                right: 15px;
                padding: 0 8px;
                color: {COLORS['primary']};
            }}
            QCheckBox {{
                color: {COLORS['text']};
                spacing: 8px;
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {COLORS['border']};
                border-radius: 4px;
                background: {COLORS['bg_tertiary']};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['primary']};
                border-color: {COLORS['primary']};
            }}
            QSpinBox {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                min-width: 80px;
            }}
            QSpinBox:focus {{ border-color: {COLORS['primary']}; }}
            QStatusBar {{
                background: {COLORS['bg_secondary']};
                color: {COLORS['text_muted']};
                font-size: 12px;
                border-top: 1px solid {COLORS['border']};
            }}
            QProgressBar {{
                background: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                text-align: center;
                color: {COLORS['text']};
            }}
            QProgressBar::chunk {{
                background: {COLORS['primary']};
                border-radius: 4px;
            }}
        """

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        main_layout.addWidget(self._create_top_bar())
        main_layout.addWidget(self._create_strategy_selector())
        main_layout.addWidget(self._create_results_table(), stretch=1)
        main_layout.addWidget(self._create_bottom_bar())

        self._setup_status_bar()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(8)
        main_layout.addWidget(self.progress_bar)

    def _create_top_bar(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        layout.setDirection(QHBoxLayout.Direction.RightToLeft)

        # دکمه اسکن دستی
        self.btn_scan = QPushButton("🔄 اسکن دستی")
        self.btn_scan.setStyleSheet(self._button_style('success', large=True))
        self.btn_scan.clicked.connect(self.do_scan)
        layout.addWidget(self.btn_scan)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        layout.addWidget(sep)

        # اسکن خودکار
        self.chk_auto = QCheckBox("⏱ اسکن خودکار")
        self.chk_auto.setChecked(True)   # ← پیش‌فرض روشن
        self.chk_auto.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.chk_auto.stateChanged.connect(self.toggle_auto_scan)
        layout.addWidget(self.chk_auto)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(2, 3600)
        self.spin_interval.setValue(DEFAULT_REFRESH_SEC)
        self.spin_interval.setSuffix(" ثانیه")
        self.spin_interval.setSingleStep(1)
        self.spin_interval.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        layout.addWidget(self.spin_interval)

        layout.addStretch()

        # نمایش زمان اجرا
        self.lbl_duration = QLabel("⏱ --")
        self.lbl_duration.setStyleSheet(f"""
            color: {COLORS['warning']};
            font-size: 11px;
            font-weight: bold;
        """)
        layout.addWidget(self.lbl_duration)

        self.lbl_last_update = QLabel("آخرین به‌روزرسانی: --")
        self.lbl_last_update.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
        """)
        layout.addWidget(self.lbl_last_update)

        return frame

    def _create_strategy_selector(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        layout.setDirection(QHBoxLayout.Direction.RightToLeft)

        label = QLabel("🎯 استراتژی فعال:")
        label.setStyleSheet(f"""
            color: {COLORS['text']};
            font-weight: bold;
            font-size: 13px;
        """)
        layout.addWidget(label)

        self.strategy_buttons = {}
        strategies = [
            ('bull_call_spread', '🐂 Bull Call Spread'),
            ('covered_call', '🛡 Covered Call'),
            ('long_call', '📈 Long Call'),
        ]

        self.strategy_group = QButtonGroup(self)
        self.strategy_group.setExclusive(True)

        for key, name in strategies:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(self._strategy_button_style())
            btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            btn.clicked.connect(lambda checked, k=key: self.set_active_strategy(k))
            self.strategy_buttons[key] = btn
            self.strategy_group.addButton(btn)
            layout.addWidget(btn)

        self.strategy_buttons[DEFAULT_STRATEGY].setChecked(True)
        layout.addStretch()

        self.lbl_count = QLabel("۰ موقعیت")
        self.lbl_count.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
        """)
        layout.addWidget(self.lbl_count)

        return frame

    def _strategy_button_style(self):
        return f"""
            QPushButton {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text']};
                border: 2px solid {COLORS['border_light']};
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 13px;
                font-weight: bold;
                font-family: Tahoma;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_hover']};
                border-color: {COLORS['primary']};
                color: white;
            }}
            QPushButton:checked {{
                background: {COLORS['selected_bg']};
                color: white;
                border-color: {COLORS['selected_bg']};
            }}
        """

    def _create_results_table(self):
        group = QGroupBox("📋 نتایج اسکن")
        group.setStyleSheet(f"""
            QGroupBox {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
                font-size: 13px;
                font-weight: bold;
                color: {COLORS['primary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                right: 15px;
                padding: 0 8px;
            }}
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)

        self.table = RTLSingleSelectionTable()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "استراتژی",
            "نماد پایه",
            "لگ اول",
            "لگ دوم",
            "سربه‌سر",
            "درصد سود ماهانه",
            "امتیاز",
            "روز تا سررسید",
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self.on_row_selection_changed)
        layout.addWidget(self.table)

        return group

    def _create_bottom_bar(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        layout.setDirection(QHBoxLayout.Direction.RightToLeft)

        self.lbl_selected = QLabel("📍 موقعیتی انتخاب نشده")
        self.lbl_selected.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
            padding: 8px 15px;
            background: {COLORS['bg_tertiary']};
            border-radius: 6px;
        """)
        self.lbl_selected.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout.addWidget(self.lbl_selected, stretch=1)

        self.btn_send_broker = QPushButton("🚀 ارسال به کارگزاری")
        self.btn_send_broker.setStyleSheet(self._button_style('success'))
        self.btn_send_broker.clicked.connect(self.send_to_broker)
        self.btn_send_broker.setEnabled(False)
        layout.addWidget(self.btn_send_broker)

        self.btn_send_bale = QPushButton("📱 ارسال به بله")
        self.btn_send_bale.setStyleSheet(self._button_style('primary'))
        self.btn_send_bale.clicked.connect(self.send_to_bale)
        self.btn_send_bale.setEnabled(False)
        layout.addWidget(self.btn_send_bale)

        self.btn_save_excel = QPushButton("💾 ذخیره Excel")
        self.btn_save_excel.setStyleSheet(self._button_style('warning'))
        self.btn_save_excel.clicked.connect(self.save_to_excel)
        layout.addWidget(self.btn_save_excel)

        self.btn_clear = QPushButton("🗑 پاک کردن")
        self.btn_clear.setStyleSheet(self._button_style('danger'))
        self.btn_clear.clicked.connect(self.clear_results)
        layout.addWidget(self.btn_clear)

        return frame

    def _button_style(self, role='primary', large=False):
        colors = {
            'primary': COLORS['primary'],
            'success': COLORS['success'],
            'warning': COLORS['warning'],
            'danger': COLORS['danger'],
        }
        color = colors.get(role, COLORS['primary'])
        padding = "10px 24px" if large else "8px 18px"
        font_size = "14px" if large else "13px"

        return f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: {padding};
                font-size: {font_size};
                font-weight: bold;
                font-family: Tahoma;
                min-width: 100px;
            }}
            QPushButton:hover {{ background: {color}dd; }}
            QPushButton:pressed {{ background: {color}aa; }}
            QPushButton:disabled {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_muted']};
            }}
        """

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.status_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("🟢 آماده")

    # ═══════════════════════════════════════════════════════════════
    # State — تغییر استراتژی
    # ═══════════════════════════════════════════════════════════════

    def set_active_strategy(self, strategy):
        """تنظیم استراتژی فعال + اطلاع به Backend"""
        if strategy == self.active_strategy:
            return

        self.active_strategy = strategy
        self.strategy_buttons[strategy].setChecked(True)
        
        # پاک کردن جدول فعلی
        self.current_data = {}
        self.current_rows = []
        self.table.setRowCount(0)
        self.selected_row_idx = None
        self.lbl_selected.setText("📍 موقعیتی انتخاب نشده")
        self.btn_send_broker.setEnabled(False)
        self.btn_send_bale.setEnabled(False)
        
        # نمایش وضعیت
        strategy_names = {
            'bull_call_spread': '🐂 بول کال اسپرد',
            'covered_call': '🛡 کاورد کال',
            'long_call': '📈 لانگ کال',
        }
        self.status_bar.showMessage(
            f"⏳ در حال تغییر استراتژی به {strategy_names.get(strategy, strategy)}..."
        )
        
        # اطلاع دادن به Backend
        self.set_strategy_worker = SetStrategyWorker(strategy)
        self.set_strategy_worker.strategy_set.connect(self.on_strategy_set)
        self.set_strategy_worker.start()

    def on_strategy_set(self, success, result):
        """نتیجه تغییر استراتژی"""
        if success:
            strategy_names = {
                'bull_call_spread': '🐂 بول کال اسپرد',
                'covered_call': '🛡 کاورد کال',
                'long_call': '📈 لانگ کال',
            }
            self.status_bar.showMessage(
                f"✅ استراتژی فعال: {strategy_names.get(result, result)}"
            )
            # اسکن فوری برای دریافت نتایج جدید
            QTimer.singleShot(500, self.do_scan)
        else:
            self.status_bar.showMessage(f"❌ خطا در تغییر استراتژی: {result}")

    def toggle_auto_scan(self, state):
        if state == Qt.CheckState.Checked.value:
            self.spin_interval.setEnabled(True)
            self._start_auto_timer()
        else:
            self.spin_interval.setEnabled(False)
            self._stop_auto_timer()

    def _on_interval_changed(self, value):
        if self.chk_auto.isChecked():
            self._start_auto_timer()

    def _start_auto_timer(self):
        self._stop_auto_timer()
        interval_sec = self.spin_interval.value()
        self.auto_timer = QTimer()
        self.auto_timer.timeout.connect(self.do_scan)
        self.auto_timer.start(interval_sec * 1000)
        self.status_bar.showMessage(f"⏱ اسکن خودکار - هر {interval_sec} ثانیه")

    def _stop_auto_timer(self):
        if self.auto_timer:
            self.auto_timer.stop()
            self.auto_timer = None

    def _start_auto_refresh(self):
        QTimer.singleShot(2500, self.do_scan)
        # شروع تایمر خودکار
        if self.chk_auto.isChecked():
            self._start_auto_timer()

    # ═══════════════════════════════════════════════════════════════
    # Scan
    # ═══════════════════════════════════════════════════════════════

    def do_scan(self):
        if self.fetch_worker and self.fetch_worker.isRunning():
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.fetch_worker = FetchWorker()
        self.fetch_worker.data_received.connect(self.on_data_received)
        self.fetch_worker.error_occurred.connect(self.on_fetch_error)
        self.fetch_worker.finished.connect(self.on_fetch_finished)
        self.fetch_worker.start()

    def on_data_received(self, data):
        self.current_data = data
        self.render_table(data)

    def on_fetch_error(self, error):
        self.status_bar.showMessage(f"❌ خطا: {error}")

    def on_fetch_finished(self):
        self.progress_bar.setVisible(False)

    # ═══════════════════════════════════════════════════════════════
    # Render
    # ═══════════════════════════════════════════════════════════════

    def render_table(self, data):
        positions = data.get('positions', {})
        active = data.get('active_strategy', self.active_strategy)
        duration_ms = data.get('last_duration_ms', 0)

        # ⚠️ فقط استراتژی فعال را نمایش بده
        rows = []

        strategy_names = {
            'bull_call_spread': ('🐂 بول کال اسپرد', COLORS['bull_call']),
            'covered_call': ('🛡 کاورد کال', COLORS['covered_call']),
            'long_call': ('📈 لانگ کال', COLORS['long_call']),
        }

        # فقط داده‌های استراتژی فعال را پردازش کن
        positions_list = positions.get(active, [])
        name, color = strategy_names.get(active, (active, COLORS['primary']))

        for idx, pos in enumerate(positions_list):
            if active == 'bull_call_spread':
                leg1 = f"🟢 خرید {pos.get('long_option_symbol', '-')}"
                leg2 = f"🔴 فروش {pos.get('short_option_symbol', '-')}"
            elif active == 'covered_call':
                leg1 = f"🟢 خرید {pos.get('underlying', '-')}"
                leg2 = f"🔴 فروش {pos.get('option_symbol', '-')}"
            else:
                leg1 = f"🟢 خرید {pos.get('option_symbol', '-')}"
                leg2 = "-"

            score = pos.get('composite_score', 0)
            try:
                score_num = float(score)
            except:
                score_num = 0

            monthly = pos.get('monthly_return_%', 0) or pos.get('monthly_return', 0)
            breakeven = pos.get('break_even_price', 0)

            try:
                breakeven_str = f"{int(breakeven):,}"
            except:
                breakeven_str = str(breakeven)

            rows.append({
                'strategy': active,
                'strategy_name': name,
                'strategy_color': color,
                'index': idx,
                'underlying': pos.get('underlying', '-'),
                'leg1': leg1,
                'leg2': leg2,
                'breakeven': breakeven_str,
                'score': score,
                'score_num': score_num,
                'monthly_return': monthly,
                'days': pos.get('days_to_maturity', 0),
                'original': pos,
            })

        rows.sort(key=lambda r: r['score_num'], reverse=True)
        self.current_rows = rows

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            # 0: استراتژی
            item = QTableWidgetItem(row['strategy_name'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QBrush(QColor(row['strategy_color'])))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.table.setItem(row_idx, 0, item)

            # 1: نماد پایه
            item = QTableWidgetItem(row['underlying'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.table.setItem(row_idx, 1, item)

            # 2: لگ اول
            item = QTableWidgetItem(row['leg1'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_idx, 2, item)

            # 3: لگ دوم
            item = QTableWidgetItem(row['leg2'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_idx, 3, item)

            # 4: سربه‌سر
            item = QTableWidgetItem(row['breakeven'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 4, item)

            # 5: درصد سود ماهانه
            item = QTableWidgetItem(f"{row['monthly_return']}%")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QBrush(QColor(COLORS['success'])))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.table.setItem(row_idx, 5, item)

            # 6: امتیاز
            item = QTableWidgetItem(str(row['score']))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            if row['score_num'] >= 15:
                item.setForeground(QBrush(QColor(COLORS['success'])))
            elif row['score_num'] >= 8:
                item.setForeground(QBrush(QColor(COLORS['warning'])))
            else:
                item.setForeground(QBrush(QColor(COLORS['danger'])))
            self.table.setItem(row_idx, 6, item)

            # 7: روز تا سررسید
            item = QTableWidgetItem(f"{row['days']} روز")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 7, item)

        self.table.setSortingEnabled(True)

        self.lbl_count.setText(f"{len(rows)} موقعیت")

        now = datetime.now().strftime("%H:%M:%S")
        self.lbl_last_update.setText(f"آخرین به‌روزرسانی: {now}")
        
        # نمایش زمان اجرای Backend
        if duration_ms > 0:
            self.lbl_duration.setText(f"⏱ {duration_ms}ms")

        self.status_bar.showMessage(f"✅ {len(rows)} موقعیت ({active})")

    # ═══════════════════════════════════════════════════════════════
    # Selection
    # ═══════════════════════════════════════════════════════════════

    def on_row_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()

        if not rows:
            self.selected_row_idx = None
            self.lbl_selected.setText("📍 موقعیتی انتخاب نشده")
            self.btn_send_broker.setEnabled(False)
            self.btn_send_bale.setEnabled(False)
            return

        row = rows[0].row()
        self.selected_row_idx = row

        if row >= len(self.current_rows):
            return

        info = self.current_rows[row]
        self.lbl_selected.setText(
            f"📍 انتخاب‌شده: {info['strategy_name']} | "
            f"{info['underlying']} | "
            f"امتیاز: {info['score']}"
        )

        self.btn_send_broker.setEnabled(True)
        self.btn_send_bale.setEnabled(True)

    # ═══════════════════════════════════════════════════════════════
    # Send to Broker
    # ═══════════════════════════════════════════════════════════════

    def send_to_broker(self):
        if self.selected_row_idx is None:
            QMessageBox.warning(self, "هشدار", "لطفاً یک موقعیت انتخاب کنید")
            return

        info = self.current_rows[self.selected_row_idx]

        reply = QMessageBox.question(
            self,
            "تأیید ارسال",
            f"ارسال موقعیت زیر به کارگزاری؟\n\n"
            f"استراتژی: {info['strategy_name']}\n"
            f"نماد: {info['underlying']}\n"
            f"لگ ۱: {info['leg1']}\n"
            f"لگ ۲: {info['leg2']}\n"
            f"امتیاز: {info['score']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_send_broker.setEnabled(False)
        self.btn_send_broker.setText("⏳ در حال ارسال...")

        self.send_worker = SendWorker(info['strategy'], info['index'])
        self.send_worker.send_completed.connect(self.on_send_completed)
        self.send_worker.start()

    def on_send_completed(self, success, message):
        self.btn_send_broker.setEnabled(True)
        self.btn_send_broker.setText("🚀 ارسال به کارگزاری")

        if success:
            self.status_bar.showMessage("✅ " + message.split('\n')[0])
            QMessageBox.information(
                self, "موفق",
                message + "\n\n📌 حالا در تب کارگزاری، Snippet آن را پر می‌کند."
            )
        else:
            self.status_bar.showMessage(f"❌ خطا: {message}")
            QMessageBox.critical(self, "خطا", f"خطا:\n{message}")

    # ═══════════════════════════════════════════════════════════════
    # Send to Bale
    # ═══════════════════════════════════════════════════════════════

    def send_to_bale(self):
        if self.selected_row_idx is None:
            QMessageBox.warning(self, "هشدار", "لطفاً یک موقعیت انتخاب کنید")
            return

        info = self.current_rows[self.selected_row_idx]

        message = (
            f"🤖 *{info['strategy_name']}*\n"
            f"📌 {info['underlying']}\n"
            f"📊 {info['leg1']}\n"
            f"📊 {info['leg2']}\n"
            f"🎯 سربه‌سر: {info['breakeven']}\n"
            f"🏆 امتیاز: {info['score']}\n"
            f"📈 سود ماهانه: {info['monthly_return']}%\n"
            f"⏱ {info['days']} روز"
        )

        self.btn_send_bale.setEnabled(False)
        self.btn_send_bale.setText("⏳ در حال ارسال...")

        self.bale_worker = BaleWorker(message)
        self.bale_worker.send_completed.connect(self.on_bale_completed)
        self.bale_worker.start()

    def on_bale_completed(self, success, message):
        self.btn_send_bale.setEnabled(True)
        self.btn_send_bale.setText("📱 ارسال به بله")

        if success:
            self.status_bar.showMessage("✅ " + message)
            QMessageBox.information(self, "موفق", "پیام به بله ارسال شد")
        else:
            self.status_bar.showMessage(f"❌ خطا: {message}")
            QMessageBox.critical(self, "خطا", f"خطا: {message}")

    # ═══════════════════════════════════════════════════════════════
    # Save Excel
    # ═══════════════════════════════════════════════════════════════

    def save_to_excel(self):
        if not self.current_rows:
            QMessageBox.information(self, "اطلاعات", "داده‌ای برای ذخیره وجود ندارد")
            return

        default_name = f"option_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "ذخیره نتایج",
            default_name,
            "Excel Files (*.xlsx)",
        )

        if not filepath:
            return

        try:
            import pandas as pd

            data = []
            for row in self.current_rows:
                data.append({
                    'استراتژی': row['strategy_name'],
                    'نماد پایه': row['underlying'],
                    'لگ اول': row['leg1'],
                    'لگ دوم': row['leg2'],
                    'سربه‌سر': row['breakeven'],
                    'درصد سود ماهانه': row['monthly_return'],
                    'امتیاز': row['score'],
                    'روز تا سررسید': row['days'],
                })

            df = pd.DataFrame(data)
            df.to_excel(filepath, index=False, engine='openpyxl')

            self.status_bar.showMessage(f"✅ ذخیره شد: {filepath}")
            QMessageBox.information(self, "موفق", f"فایل ذخیره شد:\n{filepath}")

        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره: {e}")

    # ═══════════════════════════════════════════════════════════════
    # Clear
    # ═══════════════════════════════════════════════════════════════

    def clear_results(self):
        reply = QMessageBox.question(
            self,
            "تأیید",
            "آیا از پاک کردن نتایج مطمئن هستید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.table.setRowCount(0)
        self.current_rows = []
        self.current_data = {}
        self.selected_row_idx = None
        self.lbl_selected.setText("📍 موقعیتی انتخاب نشده")
        self.lbl_count.setText("۰ موقعیت")
        self.btn_send_broker.setEnabled(False)
        self.btn_send_bale.setEnabled(False)

        self.status_bar.showMessage("🗑 نتایج پاک شد")

    def closeEvent(self, event):
        self._stop_auto_timer()

        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.terminate()
            self.fetch_worker.wait(1000)

        event.accept()


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("🚀 Option Analyzer - All-in-One")
    print("=" * 60)

    # ۱. شروع Backend
    run_api_server_threaded()

    # صبر تا Backend آماده شود
    time.sleep(2)

    # ۲. شروع UI
    print("✅ Starting UI (PySide6)...")

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyle("Fusion")

    # پالت تیره
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS['bg']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS['text']))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS['bg_secondary']))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS['bg_tertiary']))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS['text']))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS['bg_tertiary']))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['text']))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS['primary']))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor('white'))
    app.setPalette(palette)

    window = AnalyzerWindow()
    window.showMaximized()

    print("=" * 60)
    print("📡 API Server: http://127.0.0.1:8000")
    print("🖥️  UI: Running")
    print("=" * 60)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()