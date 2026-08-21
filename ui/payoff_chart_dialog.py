# ui/payoff_chart_dialog.py
# -*- coding: utf-8 -*-

"""
دیالوگ نمایش نمودار سود و زیان برای استراتژی‌های انتخابی
با قابلیت دابل‌کلیک روی سطرهای جدول
"""

import logging
from typing import Any, Optional

import matplotlib
matplotlib.use('Qt5Agg')  # برای نمایش در پنجره GUI
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, 
    QFrame, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.PayoffChart")


class PayoffChartCanvas(FigureCanvas):
    """Canvas اختصاصی برای نمایش نمودار سود و زیان در پنجره GUI"""
    
    def __init__(self, parent: Optional[QDialog] = None, width: float = 10, height: float = 6, dpi: int = 100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # تنظیمات ظاهری
        self.fig.patch.set_facecolor('#f5f7fa')
        self.ax.set_facecolor('#ffffff')
        
        # فونت فارسی
        try:
            font = QFont("Vazirmatn", 9)
            self.ax.tick_params(labelsize=9)
        except Exception:
            pass
    
    def draw_payoff_chart(
        self, 
        price_levels: list, 
        profits: list,
        strategy_name: str,
        ticker: str,
        current_price: Optional[float] = None,
        breakeven_points: Optional[list] = None
    ):
        """ترسیم نمودار سود و زیان"""
        self.ax.clear()
        
        # تنظیمات فونت پیش‌فرض
        self.ax.tick_params(axis='both', which='major', labelsize=8)
        
        # رسم خط اصلی سود و زیان
        self.ax.plot(price_levels, profits, linewidth=2, color='#136F8E', label='P&L')
        
        # خط صفر (مرز سود و زیان)
        self.ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8, alpha=0.3)
        
        # خط قیمت فعلی
        if current_price is not None:
            self.ax.axvline(x=current_price, color='#2CA02C', linestyle='--', linewidth=1.5, alpha=0.8, label=f'قیمت فعلی: {current_price:,.0f}')
        
        # نقاط سربه‌سر
        if breakeven_points:
            for be in breakeven_points:
                self.ax.axvline(x=be, color='#D62728', linestyle=':', linewidth=1.2, alpha=0.7)
        
        # استفاده از fill_between برای ناحیه سود و زیان
        self.ax.fill_between(
            price_levels, profits, 0,
            where=(profits > 0),
            interpolate=True,
            color='#2CA02C', alpha=0.15, label='سود'
        )
        self.ax.fill_between(
            price_levels, profits, 0,
            where=(profits < 0),
            interpolate=True,
            color='#D62728', alpha=0.1, label='ضرر'
        )
        
        # تنظیمات عنوان و برچسب‌ها
        self.ax.set_title(f'{strategy_name} - {ticker}', fontsize=12, fontweight='bold', pad=15)
        self.ax.set_xlabel('قیمت سررسید', fontsize=10)
        self.ax.set_ylabel('سود/زیان (ریال)', fontsize=10)
        self.ax.grid(True, linestyle='--', alpha=0.4)
        
        # اضافه کردن legend
        self.ax.legend(loc='upper left', frameon=True, facecolor='white', fontsize=8)
        
        # تنظیم layout
        self.fig.tight_layout()
        
        # رفرش کردن canvas
        self.draw()


class PayoffChartDialog(QDialog):
    """
    دیالوگ نمایش نمودار سود و زیان برای یک استراتژی خاص
    با قابلیت دابل‌کلیک روی سطرهای جدول اصلی
    """
    
    def __init__(self, parent: Optional['QMainWindow'] = None):
        super().__init__(parent)
        self.setWindowTitle("نمودار سود و زیان - تحلیل استراتژی")
        self.resize(900, 600)
        self.setMinimumSize(700, 500)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self._current_strategy: Any = None
        self._theme_mode: ui_theme.ThemeMode = "dark"
        
        self._init_ui()
    
    def _init_ui(self):
        """ساخت رابط کاربری"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # عنوان
        title_label = QLabel("📊 نمودار سود و زیان استراتژی")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # ناحیه نمودار
        self.chart_canvas = PayoffChartCanvas(self, width=10, height=6, dpi=100)
        chart_frame = QFrame()
        chart_frame.setFrameShape(QFrame.Shape.StyledPanel)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(5, 5, 5, 5)
        chart_layout.addWidget(self.chart_canvas)
        main_layout.addWidget(chart_frame, stretch=1)
        
        # اطلاعات استراتژی
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(6)
        
        self.lbl_strategy_name = QLabel("نام استراتژی: -")
        self.lbl_ticker = QLabel("نماد: -")
        self.lbl_max_profit = QLabel("حداکثر سود: -")
        self.lbl_max_loss = QLabel("حداکثر ضرر: -")
        self.lbl_breakeven = QLabel("نقطه سربه‌سر: -")
        
        for label in [self.lbl_strategy_name, self.lbl_ticker, self.lbl_max_profit, self.lbl_max_loss, self.lbl_breakeven]:
            label.setStyleSheet("font-size: 9pt; padding: 4px;")
            info_layout.addWidget(label)
        
        main_layout.addWidget(info_frame)
        
        # دکمه بستن
        close_btn = QPushButton("❌ بستن")
        close_btn.setStyleSheet("QPushButton { background-color: #e11d48; color: white; padding: 8px 20px; border-radius: 4px; font-weight: bold; }")
        close_btn.clicked.connect(self.close)
        close_btn.setAutoDefault(False)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)
    
    def load_strategy(self, strategy: Any, theme_mode: ui_theme.ThemeMode = "dark"):
        """بارگذاری استراتژی و رسم نمودار"""
        self._current_strategy = strategy
        self._theme_mode = theme_mode
        
        if not strategy:
            return
        
        # دریافت اطلاعات استراتژی
        strategy_name = str(getattr(strategy, 'strategy_name', 'استراتژی'))
        ticker = str(getattr(strategy, 'underlying_ticker', '-'))
        
        # دریافت داده‌های نمودار
        metadata = getattr(strategy, 'metadata', {}) or {}
        
        price_levels = metadata.get('price_levels', [])
        profits = metadata.get('returns_monthly_pct', [])
        
        if not price_levels or not profits:
            # اگر داده نیست، نمودار خالی رسم کن
            self.chart_canvas.draw_payoff_chart(
                price_levels=[], profits=[], 
                strategy_name=strategy_name, ticker=ticker,
                current_price=None, breakeven_points=[]
            )
            self.lbl_strategy_name.setText(f"نام استراتژی: {strategy_name}")
            self.lbl_ticker.setText(f"نماد: {ticker}")
            self.lbl_max_profit.setText("حداکثر سود: -")
            self.lbl_max_loss.setText("حداکثر ضرر: -")
            self.lbl_breakeven.setText("نقطه سربه‌سر: -")
            return
        
        # دریافت نقاط سربه‌سر
        breakeven_points = metadata.get('break_even_points', [])
        
        # دریافت قیمت فعلی (اگر موجود باشد)
        current_price = metadata.get('current_price', None)
        if current_price is None:
            current_price = getattr(strategy, 'current_price', None)
        
        # دریافت حداکثر سود و ضرر
        max_profit = getattr(strategy, 'max_profit', 0) or metadata.get('max_profit', 0)
        max_loss = getattr(strategy, 'max_loss', 0) or metadata.get('max_loss', 0)
        
        # تنظیم رنگ بر اساس تم
        self._apply_theme(theme_mode)
        
        # رسم نمودار
        self.chart_canvas.draw_payoff_chart(
            price_levels=price_levels,
            profits=profits,
            strategy_name=strategy_name,
            ticker=ticker,
            current_price=current_price,
            breakeven_points=breakeven_points
        )
        
        # نمایش اطلاعات استراتژی
        self.lbl_strategy_name.setText(f"نام استراتژی: {strategy_name}")
        self.lbl_ticker.setText(f"نماد: {ticker}")
        self.lbl_max_profit.setText(f"حداکثر سود: {ui_theme.format_rial(max_profit, unit='ریال')}")
        self.lbl_max_loss.setText(f"حداکثر ضرر: {ui_theme.format_rial(max_loss, unit='ریال')}")
        
        if breakeven_points:
            be_str = "، ".join(ui_theme.format_rial(p) for p in breakeven_points)
            self.lbl_breakeven.setText(f"نقطه سربه‌سر: {be_str}")
        else:
            self.lbl_breakeven.setText("نقطه سربه‌سر: -")
    
    def _apply_theme(self, mode: ui_theme.ThemeMode):
        """اعمال پوسته به دیالوگ"""
        if mode == "dark":
            self.setStyleSheet("""
                QDialog {
                    background-color: #22272e;
                }
                QFrame {
                    background-color: #2d333b;
                    border: 1px solid #444c56;
                    border-radius: 6px;
                }
                QLabel {
                    color: #cdd9e5;
                }
            """)
            self.chart_canvas.fig.patch.set_facecolor('#2d333b')
            self.chart_canvas.ax.set_facecolor('#2d333b')
            self.chart_canvas.ax.tick_params(colors='#cdd9e5')
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f7fa;
                }
                QFrame {
                    background-color: white;
                    border: 1px solid #d0d7de;
                    border-radius: 6px;
                }
                QLabel {
                    color: #24292e;
                }
            """)
            self.chart_canvas.fig.patch.set_facecolor('#f5f7fa')
            self.chart_canvas.ax.set_facecolor('#ffffff')
            self.chart_canvas.ax.tick_params(colors='#24292e')
        
        # رفرش نمودار
        self.chart_canvas.draw()