# data/__init__.py

"""
بسته مدیریت داده (Data Package)
ارائه درگاه‌های دسترسی به دانلودر، پاکساز، محاسبه‌گر و مدیر یکپارچه تصویر بازار
"""

from data.manager import DataManager, get_market_snapshot, Options
from data.downloader import MarketDownloader
from data.cleaner import DataCleaner
from data.calculator import FinancialCalculator

__all__ = [
    "DataManager",
    "get_market_snapshot",
    "Options",
    "MarketDownloader",
    "DataCleaner",
    "FinancialCalculator",
]