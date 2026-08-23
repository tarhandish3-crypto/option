# ui/matrix_dialog.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

import matplotlib
try:
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from matplotlib.figure import Figure
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.UI.MatrixDialog")


class RiskRewardMatrixDialog(QDialog):
    """
    نمودار ماتریس پراکندگی ریسک و بازده (Risk-Reward Scatter Matrix)
    محور X: وجه تضمین / مارجین درگیر (ریال)
    محور Y: بازده روی مارجین (درصد)
    اندازه حباب: احتمال سود (PoP)
    """
    strategy_selected = Signal(object)

    def __init__(self, strategies: List[Any], theme_mode: ui_theme.ThemeMode = "dark", parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("📊 ماتریس پراکندگی ریسک و بازده استراتژی‌ها")
        self.resize(1000, 680)
        self.setMinimumSize(850, 550)

        self.strategies = strategies or []
        self._theme_mode = theme_mode

        self._init_ui()
        self._plot_matrix()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        h_box = QHBoxLayout(header_frame)
        lbl_info = QLabel(
            "💡 <b>راهنما:</b> روی هر حباب کلیک کنید تا استراتژی مربوطه انتخاب و تحلیل شود.")
        lbl_info.setStyleSheet("color: #58a6ff; font-size: 11px;")
        h_box.addWidget(lbl_info)
        layout.addWidget(header_frame)

        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

        self.canvas.mpl_connect("button_press_event", self._on_scatter_click)

    def _plot_matrix(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        is_dark = (self._theme_mode == "dark")
        bg_color = "#0d1117" if is_dark else "#ffffff"
        text_color = "#cdd9e5" if is_dark else "#24292e"
        grid_color = "#30363d" if is_dark else "#e1e4e8"

        self.figure.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

        if not self.strategies:
            ax.text(0.5, 0.5, "داده‌ای برای نمایش وجود ندارد",
                    color=text_color, ha="center", va="center")
            self.canvas.draw()
            return

        x_margins = []
        y_rois = []
        sizes = []
        labels = []

        for strat in self.strategies:
            m = float(getattr(strat, 'margin_required', 0.0) or 0.0)
            roi = float(getattr(strat, 'return_on_margin', 0.0) or 0.0)
            pop = float(getattr(strat, 'probability_of_profit', 0.5) or 0.5)
            name = f"{getattr(strat, 'strategy_name', '')} ({getattr(strat, 'underlying_ticker', '')})"

            x_margins.append(m / 1e6)  # به میلیون ریال
            y_rois.append(roi)
            sizes.append(max(60, pop * 300))
            labels.append(name)

        scatter = ax.scatter(
            x_margins, y_rois, s=sizes, c=y_rois, cmap="viridis",
            alpha=0.75, edgecolors="#ffffff", linewidths=1.2, picker=True
        )

        cbar = self.figure.colorbar(scatter, ax=ax)
        cbar.set_label("بازده روی مارجین (%)", color=text_color, fontsize=10)
        cbar.ax.yaxis.set_tick_params(color=text_color)
        for label in cbar.ax.yaxis.get_ticklabels():
            label.set_color(text_color)

        ax.set_title("Strategy Risk-Reward Scatter Matrix",
                     color=text_color, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("Margin Required (Million Rials)",
                      color=text_color, fontsize=10)
        ax.set_ylabel("Expected Return on Margin - ROI (%)",
                      color=text_color, fontsize=10)
        ax.grid(True, linestyle=":", color=grid_color, alpha=0.6)
        ax.tick_params(colors=text_color, labelsize=9)

        for spine in ax.spines.values():
            spine.set_color(grid_color)

        self.figure.tight_layout()
        self.canvas.draw()

    def _on_scatter_click(self, event):
        if event.inaxes is None or not self.strategies:
            return

        min_dist = float("inf")
        selected_idx = -1

        for idx, strat in enumerate(self.strategies):
            m = float(getattr(strat, 'margin_required', 0.0) or 0.0) / 1e6
            roi = float(getattr(strat, 'return_on_margin', 0.0) or 0.0)
            dist = (event.xdata - m)**2 + (event.ydata - roi)**2
            if dist < min_dist:
                min_dist = dist
                selected_idx = idx

        if selected_idx >= 0:
            strat = self.strategies[selected_idx]
            self.strategy_selected.emit(strat)
            self.accept()
