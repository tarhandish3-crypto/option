# reports/chart_plotter.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple, TypedDict, Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use('Agg')  # مناسب برای لایو سرورها و تسک‌های پس‌زمینه

logger = logging.getLogger("OptionScanner.Reports.ChartPlotter")


class HeatmapData(TypedDict):
    name: str
    profits: np.ndarray


class ChartPlotter:
    """
    ترسیم و ذخیره نمودارهای سنتی سود و زیان (Payoff) و هیت‌مپ‌های مقایسه‌ای استراتژی‌های آپشن
    """

    def __init__(self, output_dir: str = "reports/charts", dpi: int = 150):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dpi = dpi
        self._default_style = 'seaborn-v0_8-whitegrid'

    def plot_pnl(
        self,
        price_levels: np.ndarray,
        profits: np.ndarray,
        strategy_name: str,
        ticker: str,
        breakeven_points: Optional[List[float]] = None,
        current_price: Optional[float] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        ترسیم دقیق نمودار سود و زیان منقطع و پیوسته با کالیبراسیون هوشمند محدوده سودآوری
        """
        if filename is None:
            filename = f"{strategy_name}_{ticker}_{int(time.time())}.png"

        filepath = self.output_dir / filename

        # اعمال امن استایل بدون دستکاری تنظیمات سراسری سیستم
        with plt.style.context(self._default_style):
            fig, ax = plt.subplots(figsize=(11, 7))

            # رسم خط اصلی سود و زیان ترکیب
            ax.plot(price_levels, profits, linewidth=2.5,
                    color='#136F8E', label='P&L at Expiry')

            # خط افقی مبدا (مرز سود و زیان)
            ax.axhline(y=0, color='black', linestyle='-',
                       linewidth=0.8, alpha=0.4)

            # خط نقطه‌چین قیمت فعلی سهم پایه
            if current_price is not None:
                ax.axvline(x=current_price, color='#2CA02C', linestyle=':', linewidth=2,
                           alpha=0.8, label=f'Underlying Price: {current_price:,.0f}')

            # رسم خطوط عمودی نقاط سر‌به‌سر (Breakeven)
            if breakeven_points:
                for i, be in enumerate(breakeven_points):
                    label = 'Breakeven Point' if i == 0 else ""
                    ax.axvline(x=be, color='#D62728', linestyle='--', linewidth=1.2,
                               alpha=0.7, label=label)
                    ax.text(be, ax.get_ylim()[1] * 0.75, f' {be:,.0f}',
                            color='#D62728', rotation=90, fontsize=8)

            # استفاده از fill_between برای هندل کردن دقیق استراتژی‌های غیرپیوسته
            ax.fill_between(
                price_levels, profits, 0,
                where=(profits > 0),
                interpolate=True,
                color='#2CA02C', alpha=0.15, label='Profitable Zone'
            )
            ax.fill_between(
                price_levels, profits, 0,
                where=(profits < 0),
                interpolate=True,
                color='#D62728', alpha=0.08, label='Loss Zone'
            )

            # تنظیمات ظاهری نمودار
            ax.set_title(f'{strategy_name.upper().replace("_", " ")} - {ticker}',
                         fontsize=14, fontweight='bold', pad=15)
            ax.set_xlabel('Underlying Price at Expiry',
                          fontsize=11, labelpad=10)
            ax.set_ylabel('Profit / Loss (Toman)', fontsize=11, labelpad=10)
            ax.grid(True, linestyle='--', alpha=0.5)

            # باکس اطلاعات مالی
            max_profit = np.max(profits)
            max_loss = np.min(profits)

            profit_text = f"{max_profit:,.0f}" if max_profit < float(
                'inf') else "Unlimited"
            loss_text = f"{max_loss:,.0f}" if max_loss > float(
                '-inf') else "Unlimited"

            box_content = f"Max Profit: {profit_text}\nMax Loss: {loss_text}"
            ax.text(0.97, 0.03, box_content, transform=ax.transAxes, fontsize=10,
                    horizontalalignment='right', verticalalignment='bottom',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#F8F9FA',
                              edgecolor='#DEE2E6', alpha=0.9))

            # تنظیم موقعیت راهنمای نمودار
            ax.legend(loc='upper left', frameon=True,
                      facecolor='white', edgecolor='#DEE2E6')

            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi,
                        bbox_inches='tight', facecolor='white')
            plt.close()

        logger.info(
            f"P&L Payoff chart successfully generated and saved: {filepath}")
        return str(filepath)

    def plot_comparison(
        self,
        data: List[Tuple[str, Any, Optional[str]]],
        ticker: str,
        top_n: int = 5,
        filename: Optional[str] = None
    ) -> str:
        """
        رسم همزمان منحنی چند ترکیب برتر جهت مقایسه بازدهی لایو کاندیداها
        """
        if filename is None:
            filename = f"comparison_{ticker}_{int(time.time())}.png"

        filepath = self.output_dir / filename

        if not data:
            logger.warning("No data provided for comparison chart")
            return str(filepath)

        with plt.style.context(self._default_style):
            fig, ax = plt.subplots(figsize=(13, 7.5))

            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            plotted_count = 0
            for i, item in enumerate(data[:top_n]):
                if len(item) == 2:
                    name, opp = item
                    color = colors[i % len(colors)]
                else:
                    name, opp, color = item[:3]
                    if color is None:
                        color = colors[i % len(colors)]

                price_levels = opp.metadata.get('price_levels', [])
                profits = opp.metadata.get('net_profits_closed', [])

                if not price_levels or not profits:
                    logger.warning(f"No P&L data for {name}, skipping")
                    continue

                try:
                    price_levels = np.array([float(p) for p in price_levels])
                    profits = np.array([float(p) for p in profits])
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Error converting data for {name}: {e}, skipping")
                    continue

                ax.plot(price_levels, profits, linewidth=2, color=color,
                        label=name.replace("_", " "))
                plotted_count += 1

            if plotted_count == 0:
                logger.warning("No valid data to plot in comparison chart")
                plt.close()
                return str(filepath)

            ax.axhline(y=0, color='black', linestyle='-',
                       linewidth=0.8, alpha=0.4)

            ax.set_title(f'Top {min(top_n, plotted_count)} Strategy Comparison - {ticker}',
                         fontsize=14, fontweight='bold', pad=15)
            ax.set_xlabel('Underlying Price at Expiry', fontsize=11)
            ax.set_ylabel('Profit / Loss (Toman)', fontsize=11)
            ax.grid(True, linestyle='--', alpha=0.5)

            ax.legend(loc='upper left', frameon=True, facecolor='white')
            plt.tight_layout()

            plt.savefig(filepath, dpi=self.dpi,
                        bbox_inches='tight', facecolor='white')
            plt.close()

        logger.info(f"Comparison chart for {ticker} saved: {filepath}")
        return str(filepath)

    def plot_heatmap(
        self,
        data: List[HeatmapData],
        ticker: str,
        filename: Optional[str] = None
    ) -> str:
        """
        ترسیم هیت‌مپ ماتریسی با ترازسازی خودکار ابعاد داده‌ها (Matrix Shape Alignment)
        """
        if filename is None:
            filename = f"heatmap_{ticker}_{int(time.time())}.png"

        filepath = self.output_dir / filename

        if not data:
            logger.warning("No data provided to plot heatmap.")
            return str(filepath)

        with plt.style.context(self._default_style):
            fig, ax = plt.subplots(figsize=(12, 7.5))

            target_data = data[:10]
            names = [item['name'].replace("_", " ") for item in target_data]

            # مهار عدم تقارن طول لیست‌های پروفایل (تضمین ساخت ماتریس دو بعدی مستطیلی)
            min_length = min(len(item['profits']) for item in target_data)
            aligned_profits = [item['profits'][:min_length]
                               for item in target_data]
            profits_matrix = np.array(aligned_profits)

            im = ax.imshow(profits_matrix, cmap='RdYlGn',
                           aspect='auto', interpolation='nearest')

            ax.set_yticks(range(len(names)))
            ax.set_yticklabels(names, fontsize=9, fontweight='medium')

            ax.set_xlabel(
                f'Price Index Levels (Aligned to {min_length} steps)', fontsize=11, labelpad=10)
            ax.set_ylabel('Generated Strategy Option Configuration',
                          fontsize=11, labelpad=10)
            ax.set_title(f'Strategy Profit Matrix Heatmap - {ticker}',
                         fontsize=14, fontweight='bold', pad=15)

            cbar = plt.colorbar(im, ax=ax, pad=0.02)
            cbar.set_label('Expected Profit / Loss (Toman)',
                           fontsize=10, labelpad=10)

            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi,
                        bbox_inches='tight', facecolor='white')
            plt.close()

        logger.info(f"Matrix Heatmap successfully outputted to {filepath}")
        return str(filepath)
