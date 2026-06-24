# reports/excel_exporter.py
# -*- coding: utf-8 -*-

"""
ماژول خروجی اکسل (Excel Exporter Module) - نسخه ارتقایافته سیستم تصمیم‌یار (DSS) همراه با امتیازهای موازی
"""

import os
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

from analytics.payoff_calculator import PayoffResult
from core.models import Opportunity
from config import get_price_steps


class ExcelExporter:
    """
    صادرکننده پیشرفته نتایج اسکنر به اکسل با پشتیبانی از شيت‌بندی ماتریسی و امتیازهای موازی پروفایل سرمایه‌گذار
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pct_steps = get_price_steps()
        self._initialize_styles()

    def _initialize_styles(self):
        """مقداردهی و کش کردن استایل‌های استاندارد جهت افزایش سرعت رندرینگ"""
        self.header_font = Font(name='Segoe UI', size=11,
                                bold=True, color='FFFFFF')
        self.header_fill = PatternFill(
            start_color='1F4E78', end_color='1F4E78', fill_type='solid')
        self.header_alignment = Alignment(
            horizontal='center', vertical='center', wrap_text=True)

        self.body_font = Font(name='Segoe UI', size=10)
        self.body_alignment_right = Alignment(
            horizontal='right', vertical='center')
        self.body_alignment_center = Alignment(
            horizontal='center', vertical='center')

        self.green_font = Font(color='006100', name='Segoe UI', size=10)
        self.green_fill = PatternFill(
            start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')

        self.red_font = Font(color='9C0006', name='Segoe UI', size=10)
        self.red_fill = PatternFill(
            start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')

        self.gold_font = Font(color='B25E00', bold=True,
                              name='Segoe UI', size=10)
        self.gold_fill = PatternFill(
            start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')

        self.gray_font = Font(color='808080', italic=True,
                              name='Segoe UI', size=10)

    def export_from_payoff(
        self,
        opportunities: List[Dict[str, Any]],
        filename: Optional[str] = None
    ) -> str:
        if not opportunities:
            return ""

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"option_opportunities_{timestamp}.xlsx"

        filepath = self.output_dir / filename
        self._export_to_excel(opportunities, str(filepath))
        return str(filepath)

    def export_from_ranked(
        self,
        opportunities: List[Opportunity],
        filename: Optional[str] = None) -> str:
        if not opportunities:
            return ""

        opp_dicts = []
        for opp in opportunities:
            meta = opp.metadata if isinstance(opp.metadata, dict) else {}

            net_closed = np.array(
                meta.get('net_profits_closed', meta.get('profits', [])))
            net_exercised = np.array(meta.get('net_profits_exercised', []))
            gross = np.array(
                meta.get('gross_profits', meta.get('profits', [])))
            price_levels = np.array(meta.get('price_levels', []))

            S0_stock = opp.S0_stock if hasattr(
                opp, 'S0_stock') and opp.S0_stock else meta.get('S0_stock')

            max_profit_val = opp.max_profit if hasattr(
                opp, 'max_profit') else meta.get('max_profit', 0.0)
            max_loss_val = opp.max_loss if hasattr(
                opp, 'max_loss') else meta.get('max_loss', 0.0)

            total_costs_closed = meta.get('total_costs_closed')
            total_costs_closed = float(
                total_costs_closed) if total_costs_closed is not None else 0.0

            total_costs_exercised = meta.get('total_costs_exercised')
            total_costs_exercised = float(
                total_costs_exercised) if total_costs_exercised is not None else 0.0

            breakeven = opp.break_even_points if hasattr(opp, 'break_even_points') and opp.break_even_points else meta.get(
                'break_even_points', meta.get('breakeven_points', []))

            payoff = PayoffResult(
                strategy_name=opp.strategy_name,
                underlying_ticker=opp.underlying_ticker,
                gross_profits=gross,
                net_profits_closed=net_closed,
                net_profits_exercised=net_exercised,
                price_levels=price_levels,
                max_profit=max_profit_val,
                max_loss=max_loss_val,
                breakeven_points=breakeven,
                total_costs_closed=total_costs_closed,
                total_costs_exercised=total_costs_exercised,
                is_profitable=meta.get('win_rate', 0) > 0,
                recommended_action=meta.get(
                    'recommended_action', 'بررسی سناریوها'),
                dynamic_range=meta.get('dynamic_range', []),
                profitable_indices=meta.get('profitable_indices', []),
                metadata=meta)

            cls_market = meta.get('market_type', 'Neutral')
            cls_profile = meta.get('investor_profile', 'Balanced')
            cls_risk = meta.get('risk_level', 'Medium')

            net_profit_if_closed = meta.get('net_profit_if_closed')
            if net_profit_if_closed is None:
                net_profit_if_closed = max_profit_val - total_costs_closed

            net_profit_if_exercised = meta.get('net_profit_if_exercised')
            if net_profit_if_exercised is None:
                net_profit_if_exercised = max_profit_val - total_costs_exercised

            opp_dict = {
                'payoff_result': payoff,
                'positions_desc': " | ".join([
                    f"{leg.contract.ticker if leg.contract else 'Stock'}"
                    for leg in opp.legs
                ]) if opp.legs else meta.get('positions_desc', 'Custom Leg'),
                'dte': opp.days_to_maturity,
                'S0_stock': S0_stock,
                'rank': opp.rank,
                'liquidity_score': opp.liquidity_score,
                'final_score': opp.final_score,
                'market_type': cls_market.value if isinstance(cls_market, Enum) else cls_market,
                'investor_profile': cls_profile.value if isinstance(cls_profile, Enum) else cls_profile,
                'risk_level': cls_risk.value if isinstance(cls_risk, Enum) else cls_risk,
                'description': meta.get('description', ''),

                'conservative_score': meta.get('conservative_score', 0.0),
                'aggressive_score': meta.get('aggressive_score', 0.0),
                'balanced_score': meta.get('balanced_score', 0.0),
                'income_score': meta.get('income_score', 0.0),
                'volatility_score': meta.get('volatility_score', 0.0),
                'confidence': meta.get('confidence', 0.80),

                'expected_value': meta.get('expected_value', 0.0),
                'area_ratio': meta.get('area_ratio', 0.0),
                'delta': meta.get('delta', 0.0),
                'gamma': meta.get('gamma', 0.0),
                'theta': meta.get('theta', 0.0),
                'vega': meta.get('vega', 0.0),
                'pop': meta.get('pop', 0.0),
                'sharpe': meta.get('sharpe', 0.0),
                'var_95': meta.get('var_95', 0.0),
                'net_profit_if_closed': net_profit_if_closed,
                'net_profit_if_exercised': net_profit_if_exercised,
            }
            opp_dicts.append(opp_dict)

        return self.export_from_payoff(opp_dicts, filename)

    def _export_to_excel(self, opportunities: List[Dict[str, Any]], file_path: str):
        rows_data = []

        for opp in opportunities:
            payoff: PayoffResult = opp.get('payoff_result')
            if not payoff:
                continue

            S0_stock = opp.get('S0_stock', 1.0)
            dynamic_range_str = self._format_dynamic_range(
                payoff.dynamic_range, S0_stock)

            # ✅ ایمن‌سازی پتانسیل None بودن دیتا
            pnl_data = payoff.metadata.get('returns_monthly_pct', [])
            if pnl_data is None:
                pnl_data = []
            price_levels = payoff.price_levels if payoff.price_levels is not None else []

            base_info = {
                "Rank": opp.get('rank', 0),
                "Strategy": payoff.strategy_name,
                "Positions": opp.get("positions_desc", ""),
                "DTE": opp.get("dte", 0),
                "Ticker": payoff.underlying_ticker,
                "Market Type": opp.get('market_type', 'Neutral'),
                "Investor Profile": opp.get('investor_profile', 'Balanced'),
                "Risk Level": opp.get('risk_level', 'Medium'),

                "Confidence": opp.get('confidence', 0.80),
                "Conservative Score": opp.get('conservative_score', 0.0),
                "Balanced Score": opp.get('balanced_score', 0.0),
                "Aggressive Score": opp.get('aggressive_score', 0.0),
                "Income Score": opp.get('income_score', 0.0),
                "Volatility Score": opp.get('volatility_score', 0.0),

                "Dynamic Range": dynamic_range_str,
                "Expected Value": opp.get('expected_value', 0.0),
                "Area Ratio": opp.get('area_ratio', 0.0),
                "POP %": opp.get('pop', 0.0),
                "Delta": opp.get('delta', 0.0),
                "Gamma": opp.get('gamma', 0.0),
                "Theta": opp.get('theta', 0.0),
                "Vega": opp.get('vega', 0.0),
                "Sharpe": opp.get('sharpe', 0.0),
                "VaR 95%": opp.get('var_95', 0.0),
                "Gross Max Profit": payoff.max_profit,
                "Gross Max Loss": payoff.max_loss,
                "Net Profit (Closed)": opp.get('net_profit_if_closed', 0.0),
                "Net Profit (Exercised)": opp.get('net_profit_if_exercised', 0.0),
                "TSE Commission": payoff.total_costs_closed,
                "Breakeven": ", ".join([f"{p:,.0f}" for p in payoff.breakeven_points]) if payoff.breakeven_points else "None",
                "Description": opp.get('description', ''),
                "Recommendation": payoff.recommended_action,
                "Liquidity": opp.get('liquidity_score', 0.0),
                "Score": opp.get('final_score', 0.0)
            }

            # ✅ درون‌یابی یا تخصیص گام‌های درصدی
            if len(price_levels) > 1 and len(pnl_data) == len(price_levels):
                target_prices = S0_stock * \
                    (1 + np.array(self.pct_steps) / 100.0)
                min_price, max_price = np.min(
                    price_levels), np.max(price_levels)

                interp_pnl = np.zeros(len(target_prices))
                for idx, target_price in enumerate(target_prices):
                    if target_price < min_price or target_price > max_price:
                        closest_idx = np.argmin(
                            np.abs(price_levels - target_price))
                        interp_pnl[idx] = pnl_data[closest_idx]
                    else:
                        interp_pnl[idx] = np.interp(
                            target_price, price_levels, pnl_data)

                for idx, pct in enumerate(self.pct_steps):
                    base_info[f"{pct}%"] = float(round(interp_pnl[idx], 4))
            else:
                for idx, pct in enumerate(self.pct_steps):
                    base_info[f"{pct}%"] = float(
                        pnl_data[idx]) if idx < len(pnl_data) else 0.0

            rows_data.append(base_info)

        df = pd.DataFrame(rows_data) if rows_data else pd.DataFrame()

        main_cols = [
            "Rank", "Strategy", "Positions", "DTE", "Ticker", "Market Type", "Investor Profile", "Risk Level",
            "Confidence", "Conservative Score", "Balanced Score", "Aggressive Score", "Income Score", "Volatility Score",
            "Dynamic Range", "Expected Value", "Area Ratio", "POP %", "Delta", "Gamma", "Theta", "Vega", "Sharpe", "VaR 95%",
            "Gross Max Profit", "Gross Max Loss", "Net Profit (Closed)", "Net Profit (Exercised)",
            "TSE Commission", "Breakeven", "Description", "Recommendation", "Liquidity", "Score"
        ]

        if not df.empty:
            main_cols = [col for col in main_cols if col in df.columns]
            pct_cols = [
                f"{pct}%" for pct in self.pct_steps if f"{pct}%" in df.columns]
            df = df[main_cols + pct_cols]
            self._write_to_styled_excel(df, file_path)

    def _format_dynamic_range(self, dynamic_range: List[float], S0_stock: float) -> str:
        if not dynamic_range or S0_stock <= 1.0:
            return "No Safe Range"
        formatted = []
        for price in dynamic_range:
            pct_deviation = ((price / S0_stock) - 1) * 100
            closest_pct = min(
                self.pct_steps, key=lambda x: abs(x - pct_deviation))
            formatted.append(f"{closest_pct:+.0f}%")
        unique_pcts = sorted(list(set(formatted)),
                             key=lambda x: float(x.replace('%', '')))
        return " | ".join(unique_pcts) if len(unique_pcts) <= 4 else f"[{unique_pcts[0]} ... {unique_pcts[-1]}]"

    def _write_to_styled_excel(self, df: pd.DataFrame, file_path: str):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Scanner_Results', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Scanner_Results']

            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=1, column=col_idx)
                cell.font = self.header_font
                cell.fill = self.header_fill
                cell.alignment = self.header_alignment

            numeric_cols = [
                "Confidence", "Conservative Score", "Balanced Score", "Aggressive Score", "Income Score", "Volatility Score",
                "Expected Value", "Area Ratio", "POP %", "Delta", "Gamma", "Theta", "Vega",
                "Sharpe", "VaR 95%", "Gross Max Profit", "Gross Max Loss",
                "Net Profit (Closed)", "Net Profit (Exercised)", "TSE Commission", "Liquidity", "Score"
            ]
            pct_cols = [
                f"{pct}%" for pct in self.pct_steps if f"{pct}%" in df.columns]

            columns_list = df.columns.tolist()

            for row_idx, row in enumerate(df.itertuples(index=False), start=2):
                for col_idx, col_name in enumerate(columns_list, start=1):
                    cell = worksheet.cell(row=row_idx, column=col_idx)
                    val = row[col_idx - 1]

                    if val is None or pd.isna(val):
                        cell.value = "-"
                        cell.font = self.gray_font
                        cell.alignment = self.body_alignment_center
                        continue

                    if col_name in numeric_cols:
                        if col_name == "Confidence":
                            cell.number_format = '0.0%'
                        else:
                            cell.number_format = '#,##0.00'
                        cell.alignment = self.body_alignment_right
                    elif col_name in pct_cols:
                        # ✅ اصلاح اساسی: استفاده از قالب سفارشی درصد بدون تغییر در ضریب پایه اکسل
                        cell.number_format = '0.00"%"'
                        cell.alignment = self.body_alignment_right
                    else:
                        cell.alignment = self.body_alignment_center

                    cell.font = self.body_font

            self._apply_conditional_formatting(worksheet, df)
            self._enable_autofilter(worksheet, df)

            # تنظیم خودکار عرض ستون‌ها
            for col in worksheet.columns:
                max_len = 0
                for cell in col:
                    val = str(cell.value or '')
                    actual_len = sum(2 if ord(c) > 128 else 1 for c in val)
                    if actual_len > max_len:
                        max_len = actual_len
                col_letter = get_column_letter(col[0].column)
                worksheet.column_dimensions[col_letter].width = min(
                    max(max_len + 4, 13), 50)

            self._add_summary_sheet(workbook, df)
            self._add_scores_sheet(workbook, df)

    def _apply_conditional_formatting(self, worksheet, df: pd.DataFrame):
        pct_cols = [
            f"{pct}%" for pct in self.pct_steps if f"{pct}%" in df.columns]
        target_cols = pct_cols + [
            "Gross Max Profit", "Expected Value", "Net Profit (Closed)", "Net Profit (Exercised)"]

        for col_name in target_cols:
            if col_name not in df.columns:
                continue
            col_idx = df.columns.get_loc(col_name) + 1
            col_letter = get_column_letter(col_idx)
            range_str = f"{col_letter}2:{col_letter}{len(df) + 1}"

            rule_pos = CellIsRule(operator='greaterThan',
                                  formula=['0'], stopIfTrue=False)
            rule_pos.fill = self.green_fill
            rule_pos.font = self.green_font
            worksheet.conditional_formatting.add(range_str, rule_pos)

            rule_neg = CellIsRule(operator='lessThan', formula=[
                                  '0'], stopIfTrue=False)
            rule_neg.fill = self.red_fill
            rule_neg.font = self.red_font
            worksheet.conditional_formatting.add(range_str, rule_neg)

        if 'Rank' in df.columns:
            col_letter = get_column_letter(df.columns.get_loc('Rank') + 1)
            rule_rank = CellIsRule(operator='equal', formula=[
                                   '1'], stopIfTrue=True)
            rule_rank.font = self.gold_font
            rule_rank.fill = self.gold_fill
            worksheet.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{len(df) + 1}", rule_rank)

    def _enable_autofilter(self, worksheet, df: pd.DataFrame):
        if len(df) > 0:
            worksheet.auto_filter.ref = f"A1:{get_column_letter(len(df.columns))}{len(df) + 1}"

    def _add_summary_sheet(self, workbook: Workbook, df: pd.DataFrame):
        if df.empty:
            return

        summary_ws = workbook.create_sheet(title='Summary')
        # ✅ بهبود پایدار: اعمال راست به چپ برای شیت فارسی خلاصه مدیریتی
        # summary_ws.views.sheetView[0].rightToLeft = True

        summary_ws.append(['شاخص یا سناریوی تحلیلی بازار اوراق اختیار',
                          'مقدار محاسباتی / فراوانی توزیع سیستم'])
        summary_ws.append(
            ['کل موقعیت‌های معاملاتی تحلیل‌شده (جامعه اسکن)', len(df)])

        numeric_cols = [
            ("Expected Value", "میانگین وزنی ارزش مورد انتظار (EV)"),
            ("POP %", "میانگین احتمال موفقیت پوزیشن‌ها (POP)"),
            ("Sharpe", "میانگین نسبت شارپ سبد فرصت‌ها"),
            ("Confidence", "میانگین ضریب اطمینان طبقه‌بندی مدل"),
            ("Net Profit (Closed)", "میانگین سود خالص در پوزیشن‌های بسته‌شده"),]

        for col_name, fa_label in numeric_cols:
            if col_name in df.columns:
                col_df = pd.to_numeric(df[col_name].replace(
                    '-', np.nan), errors='coerce')
                if not col_df.empty and col_df.notna().any():
                    summary_ws.append(
                        [fa_label, round(float(col_df.mean()), 2)])

        summary_ws.append(['', ''])
        summary_ws.append(
            ['تفکیک و توزیع موقعیت‌ها بر اساس وضعیت روند بازار', 'تعداد پوزیشن'])

        for col_target in ['Market Type', 'Risk Level', 'Investor Profile']:
            if col_target in df.columns:
                counts = df[col_target].value_counts()
                for category, count in counts.items():
                    summary_ws.append(
                        [f"تعداد پوزیشن در کلاس {category}", int(count)])

        for row in summary_ws.iter_rows(min_row=1, max_row=summary_ws.max_row, min_col=1, max_col=2):
            for cell in row:
                cell.font = self.body_font
                if cell.row in [1, 2 + len(numeric_cols) + 1]:
                    cell.font = self.header_font
                    cell.fill = self.header_fill
                    cell.alignment = self.header_alignment
                else:
                    cell.alignment = self.body_alignment_right if cell.column == 2 else self.body_alignment_center

        summary_ws.column_dimensions['A'].width = 45
        summary_ws.column_dimensions['B'].width = 35

    def _add_scores_sheet(self, workbook: Workbook, df: pd.DataFrame):
        if df.empty:
            return

        scores_ws = workbook.create_sheet(title='Profile_Scores')

        score_cols = [
            "Rank", "Strategy", "Positions", "Ticker", "Confidence",
            "Conservative Score", "Balanced Score", "Aggressive Score", "Income Score", "Volatility Score"]

        score_cols = [col for col in score_cols if col in df.columns]
        sub_df = df[score_cols]

        for r_idx, row in enumerate(sub_df.values, start=2):
            for c_idx, value in enumerate(row, start=1):
                cell = scores_ws.cell(row=r_idx, column=c_idx, value=value)
                cell.font = self.body_font

                col_name = score_cols[c_idx - 1]
                if col_name in ["Confidence", "Conservative Score", "Balanced Score", "Aggressive Score", "Income Score", "Volatility Score"]:
                    cell.number_format = '0.0%' if col_name == "Confidence" else '#,##0.00'
                    cell.alignment = self.body_alignment_right
                else:
                    cell.alignment = self.body_alignment_center

        for c_idx, col_name in enumerate(score_cols, start=1):
            cell = scores_ws.cell(row=1, column=c_idx, value=col_name)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.header_alignment

        score_fields = ["Conservative Score", "Balanced Score",
                        "Aggressive Score", "Income Score", "Volatility Score"]
        for field in score_fields:
            if field in score_cols:
                c_idx = score_cols.index(field) + 1
                c_letter = get_column_letter(c_idx)
                range_str = f"{c_letter}2:{c_letter}{len(df) + 1}"

                rule_high = CellIsRule(operator='greaterThan', formula=[
                                       '70.0'], stopIfTrue=False)
                rule_high.fill = self.green_fill
                rule_high.font = self.green_font
                scores_ws.conditional_formatting.add(range_str, rule_high)

        for col in scores_ws.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or '')
                actual_len = sum(2 if ord(c) > 128 else 1 for c in val)
                if actual_len > max_len:
                    max_len = actual_len
            col_letter = get_column_letter(col[0].column)
            scores_ws.column_dimensions[col_letter].width = max(
                max_len + 4, 15)

    def export(self, opportunities: List[Opportunity], filename: Optional[str] = None, *args, **kwargs) -> str:
        """متد اصلی ارکستراتور برای هماهنگی کامل با ماژول main.py"""
        return self.export_from_ranked(opportunities, filename)
