# position_saver/importer/__init__.py
# -*- coding: utf-8 -*-

"""
پکیج ایمپورت اکسل تاریخچه معاملات کارگزاری.

اجزای اصلی:
    - schemas:      مدل‌های داده‌ای موقت (TradeRecord, MatchedLot, ...)
    - broker_templates: قالب ستون‌های هر کارگزاری
    - excel_parser: پارسر فایل اکسل
    - matcher:      تطبیق FIFO بین BUY و SELL
    - snapshot_enricher: پر کردن فیلدها از Snapshot
    - suggest:      پیشنهاد نام استراتژی
    - engine:       ارکستراتور کل فرایند
"""

# ═══════════════════════════════════════════════════
# ۱. Schemas
# ═══════════════════════════════════════════════════

from position_saver.importer.schemas import (
    TradeRecord,
    MatchedLot,
    ImportSettings,
    ImportBatch,
    ImportResult,
    BrokerTemplate,
)


# ═══════════════════════════════════════════════════
# ۲. Templates
# ═══════════════════════════════════════════════════

from position_saver.importer.broker_templates import (
    get_default_template,
    get_all_templates,
    get_template_for_broker,
    list_broker_names,
    save_user_template,
    DEFAULT_TEMPLATES,
)


# ═══════════════════════════════════════════════════
# ۳. Parser
# ═══════════════════════════════════════════════════

from position_saver.importer.excel_parser import ExcelParser


# ═══════════════════════════════════════════════════
# ۴. Matcher
# ═══════════════════════════════════════════════════

from position_saver.importer.matcher import FifoMatcher


# ═══════════════════════════════════════════════════
# ۵. Enricher
# ═══════════════════════════════════════════════════

from position_saver.importer.snapshot_enricher import (
    SnapshotEnricher,
    infer_option_kind_from_symbol,
    infer_underlying_from_symbol,
)


# ═══════════════════════════════════════════════════
# ۶. Suggest
# ═══════════════════════════════════════════════════

from position_saver.importer.suggest import suggest_strategy_name


# ═══════════════════════════════════════════════════
# ۷. Engine
# ═══════════════════════════════════════════════════

from position_saver.importer.engine import ImportEngine


# ═══════════════════════════════════════════════════
# ۸. صادرکننده‌ها
# ═══════════════════════════════════════════════════

__all__ = [
    # ─── Schemas ───
    "TradeRecord",
    "MatchedLot",
    "ImportSettings",
    "ImportBatch",
    "ImportResult",
    "BrokerTemplate",

    # ─── Templates ───
    "get_default_template",
    "get_all_templates",
    "get_template_for_broker",
    "list_broker_names",
    "save_user_template",
    "DEFAULT_TEMPLATES",

    # ─── Parser ───
    "ExcelParser",

    # ─── Matcher ───
    "FifoMatcher",

    # ─── Enricher ───
    "SnapshotEnricher",
    "infer_option_kind_from_symbol",
    "infer_underlying_from_symbol",

    # ─── Suggest ───
    "suggest_strategy_name",

    # ─── Engine ───
    "ImportEngine",
]