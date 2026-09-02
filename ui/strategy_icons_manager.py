# -*- coding: utf-8 -*-
"""
مدیریت بارگذاری و کش تصاویر شماتیک استراتژی‌ها
"""

import logging
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

logger = logging.getLogger("OptionScanner.UI.StrategyIconsManager")


class StrategyIconsManager:
    """
    مدیریت بارگذاری، کش‌کردن و نمایش تصاویر PNG شماتیک استراتژی‌ها
    
    ویژگی‌ها:
    - کش‌کردن تصاویر در حافظه برای دسترسی سریع
    - مدیریت مسیرهای فایل
    - بازگرداندن icon پیش‌فرض برای فایل‌های مفقود
    """
    
    _icons_cache: Dict[str, QPixmap] = {}
    _icons_dir: Optional[Path] = None
    _default_icon: Optional[QPixmap] = None
    
    @classmethod
    def _get_icons_dir(cls) -> Path:
        """دریافت مسیر دایرکتوری تصاویر"""
        if cls._icons_dir is None:
            current_file = Path(__file__).parent
            cls._icons_dir = current_file / "assets" / "strategies"
            
            if not cls._icons_dir.exists():
                logger.warning(f"مسیر تصاویر وجود ندارد: {cls._icons_dir}")
                logger.info("لطفاً script generate_strategy_icons.py را اجرا کنید")
                cls._icons_dir = current_file / "assets" / "strategies"
        
        return cls._icons_dir
    
    @classmethod
    def _create_default_icon(cls, size: int = 48) -> QPixmap:
        """ایجاد icon پیش‌فرض برای فایل‌های مفقود"""
        if cls._default_icon is None:
            # ایجاد pixmap خالی
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.white)
            cls._default_icon = pixmap
        
        return cls._default_icon
    
    @classmethod
    def get_icon(
        cls, 
        strategy_key: str, 
        size: int = 48, 
        use_cache: bool = True
    ) -> QPixmap:
        """
        دریافت تصویر شماتیک استراتژی
        
        Arguments:
            strategy_key: کلید استراتژی (مثل "covered_call")
            size: اندازه pixmap (پیش‌فرض: 48x48)
            use_cache: استفاده از کش (پیش‌فرض: True)
        
        Returns:
            QPixmap: تصویر شماتیک یا icon پیش‌فرض
        """
        
        # بررسی کش
        cache_key = f"{strategy_key}_{size}"
        if use_cache and cache_key in cls._icons_cache:
            return cls._icons_cache[cache_key]
        
        # مسیر فایل تصویر
        icons_dir = cls._get_icons_dir()
        icon_path = icons_dir / f"{strategy_key}.png"
        
        # بارگذاری تصویر
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            
            # تغییر اندازه به صورت smooth
            if pixmap.width() != size or pixmap.height() != size:
                pixmap = pixmap.scaledToWidth(
                    size, 
                    Qt.TransformationMode.SmoothTransformation
                )
            
            logger.debug(f"تصویر بارگذاری شد: {strategy_key}.png ({size}x{size})")
        else:
            logger.warning(f"تصویر یافت نشد: {icon_path}")
            pixmap = cls._create_default_icon(size)
        
        # ذخیره در کش
        if use_cache:
            cls._icons_cache[cache_key] = pixmap
        
        return pixmap
    
    @classmethod
    def clear_cache(cls) -> None:
        """پاک کردن کش تصاویر"""
        cls._icons_cache.clear()
        logger.info("کش تصاویر پاک شد")
    
    @classmethod
    def get_cache_size(cls) -> int:
        """دریافت تعداد تصاویر در کش"""
        return len(cls._icons_cache)
    
    @classmethod
    def preload_all_icons(
        cls, 
        strategy_keys: list[str], 
        size: int = 48
    ) -> int:
        """
        پیش‌بارگذاری تمام تصاویر برای سرعت بیشتر
        
        Arguments:
            strategy_keys: لیست کلیدهای استراتژی
            size: اندازه pixmap
        
        Returns:
            تعداد تصاویر بارگذاری‌شده
        """
        loaded_count = 0
        for key in strategy_keys:
            try:
                cls.get_icon(key, size, use_cache=True)
                loaded_count += 1
            except Exception as e:
                logger.warning(f"خطا در بارگذاری {key}: {e}")
        
        logger.info(f"پیش‌بارگذاری {loaded_count} تصویر انجام شد")
        return loaded_count


# نمونه استفاده:
"""
from ui.strategy_icons_manager import StrategyIconsManager

# دریافت تصویر
icon = StrategyIconsManager.get_icon("covered_call", size=48)

# پیش‌بارگذاری تمام تصاویر
strategies = ["covered_call", "bull_call_spread", "long_put", ...]
StrategyIconsManager.preload_all_icons(strategies)

# پاک کردن کش
StrategyIconsManager.clear_cache()
"""
