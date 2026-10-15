# position_saver/importer/broker_templates.py
# -*- coding: utf-8 -*-

"""
قالب‌های ستون‌های اکسل کارگزاری‌ها.

نکات:
    - قالب «مفید» بر اساس فایل واقعی این کارگزاری تنظیم شده است.
    - قالب‌های دیگر (خبرگان سهام، پیشرو، پارسیان) بر اساس نمونه‌ی واقعی
      تنظیم نشده‌اند — به‌عنوان حدس اولیه‌اند و در صورت نیاز اصلاح می‌شوند.
    - اگر کارگزاری ناشناخته باشد، از قالب «مفید» استفاده می‌شود.
"""

import logging
from typing import Dict, List

from position_saver.importer.schemas import BrokerTemplate


logger = logging.getLogger("PositionSaver.Importer.Templates")


# ═══════════════════════════════════════════════════
# قالب‌های پیش‌فرض
# ═══════════════════════════════════════════════════

DEFAULT_TEMPLATES: Dict[str, dict] = {
    # ✅ تأییدشده با فایل واقعی کارگزاری مفید
    "مفید": {
        "broker_name": "مفید",
        "date_col": "تاریخ",
        "time_col": "ساعت",
        "side_col": "سمت سفارش",
        "symbol_col": "نماد",
        "qty_col": "حجم انجام شده",
        "price_col": "قیمت",
        "status_col": "وضعیت",
    },
    # ⚠️ حدس اولیه — در صورت دریافت نمونه‌ی واقعی اصلاح شود
    "خبرگان سهام": {
        "broker_name": "خبرگان سهام",
        "date_col": "تاریخ",
        "time_col": "ساعت",
        "side_col": "سمت",
        "symbol_col": "نماد",
        "qty_col": "حجم انجام شده",
        "price_col": "قیمت",
        "status_col": "وضعیت",
    },
    "پیشرو": {
        "broker_name": "پیشرو",
        "date_col": "تاریخ",
        "time_col": "ساعت",
        "side_col": "نوع معامله",
        "symbol_col": "نماد",
        "qty_col": "تعداد",
        "price_col": "قیمت",
        "status_col": "وضعیت",
    },
    "پارسیان": {
        "broker_name": "پارسیان",
        "date_col": "تاریخ",
        "time_col": "ساعت",
        "side_col": "سمت سفارش",
        "symbol_col": "نماد",
        "qty_col": "حجم انجام شده",
        "price_col": "قیمت",
        "status_col": "وضعیت",
    },
}


# ═══════════════════════════════════════════════════
# توابع اصلی
# ═══════════════════════════════════════════════════

def get_all_templates() -> Dict[str, dict]:
    """همه‌ی قالب‌ها"""
    return dict(DEFAULT_TEMPLATES)


def get_default_template() -> BrokerTemplate:
    """قالب پیش‌فرض (مفید)"""
    return BrokerTemplate.from_dict(DEFAULT_TEMPLATES["مفید"])


def get_template_for_broker(broker_name: str) -> BrokerTemplate:
    """
    قالب مخصوص یک کارگزاری.

    اگر کارگزاری ناشناخته باشد، از قالب «مفید» استفاده می‌شود.
    """
    if not broker_name:
        return get_default_template()

    data = DEFAULT_TEMPLATES.get(broker_name)

    if data is None:
        logger.warning(
            f"No template for '{broker_name}' — using default (مفید)")
        template = get_default_template()
        template.broker_name = broker_name
        return template

    return BrokerTemplate.from_dict(data)


def list_broker_names() -> List[str]:
    """فهرست کارگزاری‌های شناخته‌شده"""
    return sorted(DEFAULT_TEMPLATES.keys())


__all__ = [
    "DEFAULT_TEMPLATES",
    "get_all_templates",
    "get_default_template",
    "get_template_for_broker",
    "list_broker_names",
]