# scoring/metrics.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from core.models import Opportunity

@dataclass
class StrategyMetrics:
    """معیارهای یک استراتژی"""
    win_rate: float = 0.0           # درصد سناریوهای سودآور
    risk_reward_ratio: float = 0.0  # نسبت ریسک به ریوارد
    rom: float = 0.0                # Return on Margin
    margin_efficiency: float = 0.0  # کارایی وجه تضمین
    max_profit: float = 0.0
    max_loss: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    total_scenarios: int = 0
    profitable_scenarios: int = 0


def calculate_win_rate(profits: List[float], threshold: float = 0) -> float:
    """
    محاسبه درصد سودآوری (Win Rate)
    
    Args:
        profits: لیست سود در سناریوهای مختلف
        threshold: آستانه سودآوری (پیش‌فرض 0)
        
    Returns:
        درصد سودآوری (۰ تا ۱۰۰)
    """
    if not profits:
        return 0.0
    
    profitable = sum(1 for p in profits if p > threshold)
    return (profitable / len(profits)) * 100


def calculate_risk_reward_ratio(profits: List[float]) -> float:
    """
    محاسبه نسبت ریسک به ریوارد
    
    فرمول: میانگین سود / میانگین ضرر (مطلق)
    
    Args:
        profits: لیست سود در سناریوهای مختلف
        
    Returns:
        نسبت ریسک به ریوارد
    """
    if not profits:
        return 0.0
    
    gains = [p for p in profits if p > 0]
    losses = [abs(p) for p in profits if p < 0]
    
    if not gains or not losses:
        return 0.0
    
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)
    
    if avg_loss == 0:
        return 0.0
    
    return avg_gain / avg_loss


def calculate_rom(
    expected_return_pct: float,
    required_margin: float,
    days_to_maturity: int) -> float:
    """
    محاسبه Return on Margin (بازده نسبت به وجه تضمین)
    
    فرمول: (بازده مورد انتظار / وجه تضمین) * (۳۰ / روز)
    
    Args:
        expected_return_pct: بازده مورد انتظار (درصد)
        required_margin: وجه تضمین مورد نیاز
        days_to_maturity: روزهای مانده تا سررسید
        
    Returns:
        ROM ماهانه (درصد)
    """
    if required_margin <= 0 or days_to_maturity <= 0:
        return 0.0
    
    monthly_factor = 30.0 / days_to_maturity
    return expected_return_pct * monthly_factor


def calculate_margin_efficiency(
    expected_return_pct: float,
    required_margin: float,
    days_to_maturity: int) -> float:
    """
    محاسبه کارایی وجه تضمین
    
    فرمول: بازده ماهانه / وجه تضمین
    
    Args:
        expected_return_pct: بازده مورد انتظار (درصد)
        required_margin: وجه تضمین مورد نیاز
        days_to_maturity: روزهای مانده تا سررسید
        
    Returns:
        کارایی وجه تضمین
    """
    rom = calculate_rom(expected_return_pct, required_margin, days_to_maturity)
    if required_margin <= 0:
        return 0.0
    return rom / required_margin


def calculate_all_metrics(
    profits: List[float],
    expected_return_pct: float,
    required_margin: float,
    days_to_maturity: int) -> StrategyMetrics:
    """
    محاسبه همه معیارهای یک استراتژی
    
    Args:
        profits: لیست سود در سناریوهای مختلف
        expected_return_pct: بازده مورد انتظار (درصد)
        required_margin: وجه تضمین مورد نیاز
        days_to_maturity: روزهای مانده تا سررسید
        
    Returns:
        StrategyMetrics: همه معیارها
    """
    if not profits:
        return StrategyMetrics()
    
    win_rate = calculate_win_rate(profits)
    risk_reward = calculate_risk_reward_ratio(profits)
    rom = calculate_rom(expected_return_pct, required_margin, days_to_maturity)
    margin_eff = calculate_margin_efficiency(expected_return_pct, required_margin, days_to_maturity)
    
    gains = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    
    return StrategyMetrics(
        win_rate=round(win_rate, 2),
        risk_reward_ratio=round(risk_reward, 2),
        rom=round(rom, 2),
        margin_efficiency=round(margin_eff, 4),
        max_profit=round(max(profits), 2),
        max_loss=round(min(profits), 2),
        avg_profit=round(sum(gains) / len(gains), 2) if gains else 0,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else 0,
        total_scenarios=len(profits),
        profitable_scenarios=len(gains))