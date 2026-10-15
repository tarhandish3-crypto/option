# position_saver/importer/__init__.py
# -*- coding: utf-8 -*-

"""پکیج ایمپورت اکسل تاریخچه معاملات کارگزاری."""

# ─── Symbol Map ───
from position_saver.importer.symbol_map import (
    SYMBOL_MAP, CODE_TO_SYMBOL,
    is_known_underlying, get_underlying_ins_code,
    is_option_symbol, infer_underlying_from_option,
)

# ─── Symbol Memory ───
from position_saver.importer.symbol_memory import (
    get_symbol_info, has_symbol,
    save_symbol_info, save_from_trade, save_bulk,
    get_all as get_all_symbol_memory,
    get_count as get_symbol_memory_count,
    clear_symbol as clear_symbol_memory,
    clear_all as clear_all_symbol_memory,
    export_to_dict as export_symbol_memory,
    import_from_dict as import_symbol_memory,
)

# ─── Schemas ───
from position_saver.importer.schemas import (
    TradeRecord, MatchedLot, ImportSettings,
    ImportBatch, ImportResult, BrokerTemplate,
    CLOSE_REASON_OPEN, CLOSE_REASON_OFFSET,
    CLOSE_REASON_EXERCISE, CLOSE_REASON_CASH_SETTLE,
    CLOSE_REASON_DEFAULTED, CLOSE_REASON_YOU_DEFAULTED,
    CLOSE_REASON_UNKNOWN, CLOSE_REASON_STOCK,
    CLOSE_REASON_INCOMPLETE, CLOSE_REASON_LABELS,
)

# ─── Net Position ───
from position_saver.importer.net_position import (
    compute_net_position,
    MatchInfo, NetPositionResult,
)

# ─── Templates ───
from position_saver.importer.broker_templates import (
    get_default_template, get_all_templates,
    get_template_for_broker, list_broker_names,
    DEFAULT_TEMPLATES,
)

# ─── Parser / Matcher / Enricher ───
from position_saver.importer.excel_parser import ExcelParser
from position_saver.importer.matcher import FifoMatcher
from position_saver.importer.snapshot_enricher import SnapshotEnricher

# ─── Suggest / Engine ───
from position_saver.importer.suggest import suggest_strategy_name
from position_saver.importer.engine import ImportEngine


__all__ = [
    # Symbol Map
    "SYMBOL_MAP", "CODE_TO_SYMBOL",
    "is_known_underlying", "get_underlying_ins_code",
    "is_option_symbol", "infer_underlying_from_option",
    # Symbol Memory
    "get_symbol_info", "has_symbol",
    "save_symbol_info", "save_from_trade", "save_bulk",
    "get_all_symbol_memory", "get_symbol_memory_count",
    "clear_symbol_memory", "clear_all_symbol_memory",
    "export_symbol_memory", "import_symbol_memory",
    # Schemas
    "TradeRecord", "MatchedLot", "ImportSettings",
    "ImportBatch", "ImportResult", "BrokerTemplate",
    # close_reason
    "CLOSE_REASON_OPEN", "CLOSE_REASON_OFFSET",
    "CLOSE_REASON_EXERCISE", "CLOSE_REASON_CASH_SETTLE",
    "CLOSE_REASON_DEFAULTED", "CLOSE_REASON_YOU_DEFAULTED",
    "CLOSE_REASON_UNKNOWN", "CLOSE_REASON_STOCK",
    "CLOSE_REASON_INCOMPLETE", "CLOSE_REASON_LABELS",
    # Net Position
    "compute_net_position",
    "MatchInfo", "NetPositionResult",
    # Templates
    "get_default_template", "get_all_templates",
    "get_template_for_broker", "list_broker_names",
    "DEFAULT_TEMPLATES",
    # Core
    "ExcelParser", "FifoMatcher", "SnapshotEnricher",
    "suggest_strategy_name", "ImportEngine",
]