# position_saver/importer/broker_templates.py
# -*- coding: utf-8 -*-

"""
قالب‌های ستون‌های اکسل کارگزاری‌ها.

نکات:
    - قالب «مفید» بر اساس فایل واقعی این کارگزاری تنظیم شده است.
    - قالب‌های دیگر (خبرگان سهام، پیشرو، پارسیان) بر اساس نمونه‌ی واقعی
      تنظیم نشده‌اند — به‌عنوان حدس اولیه‌اند و در صورت نیاز اصلاح می‌شوند.
    - اگر کارگزاری ناشناخته باشد، از قالب «مفید» استفاده می‌شود.
    - فیلد valid_statuses حذف شد چون دیگر فیلتری روی وضعیت اعمال نمی‌شود.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

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
    # ⚠️ حدس اولیه — در صورت دریافت نمونه‌ی واقعی اصلاح شود
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
    # ⚠️ حدس اولیه — در صورت دریافت نمونه‌ی واقعی اصلاح شود
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
# مسیر فایل قالب‌های کاربر
# ═══════════════════════════════════════════════════

_TEMPLATES_FILE = Path(__file__).parent / "broker_templates.json"
_user_templates_cache: Optional[Dict[str, dict]] = None


# ═══════════════════════════════════════════════════
# توابع اصلی
# ═══════════════════════════════════════════════════

def get_all_templates() -> Dict[str, dict]:
    """همه‌ی قالب‌ها (پیش‌فرض + کاربر)"""
    result = dict(DEFAULT_TEMPLATES)
    result.update(_load_user_templates())
    return result


def get_default_template() -> BrokerTemplate:
    """قالب پیش‌فرض (مفید)"""
    return BrokerTemplate.from_dict(DEFAULT_TEMPLATES["مفید"])


def get_template_for_broker(broker_name: str) -> BrokerTemplate:
    """
    قالب مخصوص یک کارگزاری.

    اگر کارگزاری ناشناخته باشد، از قالب «مفید» استفاده می‌شود
    (چون ساختار فایل اکسل بورس ایران معمولاً مشابه است).
    """
    if not broker_name:
        return get_default_template()

    all_templates = get_all_templates()
    data = all_templates.get(broker_name)

    if data is None:
        logger.warning(
            f"No template for '{broker_name}' — using default (مفید)")
        template = get_default_template()
        template.broker_name = broker_name
        return template

    return BrokerTemplate.from_dict(data)


def list_broker_names() -> List[str]:
    """فهرست کارگزاری‌های شناخته‌شده"""
    return sorted(get_all_templates().keys())


def save_user_template(template: BrokerTemplate) -> bool:
    """ذخیره‌ی قالب کاربر در فایل"""
    try:
        user = _load_user_templates()
        user[template.broker_name] = template.to_dict()
        with open(_TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(user, f, ensure_ascii=False, indent=2)
        _invalidate_cache()
        logger.info(f"Template saved: {template.broker_name}")
        return True
    except Exception as e:
        logger.exception(f"Save template failed: {e}")
        return False


# ═══════════════════════════════════════════════════
# داخلی
# ═══════════════════════════════════════════════════

def _load_user_templates() -> Dict[str, dict]:
    global _user_templates_cache
    if _user_templates_cache is not None:
        return _user_templates_cache

    if not _TEMPLATES_FILE.exists():
        _user_templates_cache = {}
        return _user_templates_cache

    try:
        with open(_TEMPLATES_FILE, "r", encoding="utf-8") as f:
            _user_templates_cache = json.load(f)
        return _user_templates_cache
    except Exception as e:
        logger.warning(f"Load user templates failed: {e}")
        _user_templates_cache = {}
        return _user_templates_cache


def _invalidate_cache():
    global _user_templates_cache
    _user_templates_cache = None


__all__ = [
    "DEFAULT_TEMPLATES",
    "get_all_templates",
    "get_default_template",
    "get_template_for_broker",
    "list_broker_names",
    "save_user_template",
]