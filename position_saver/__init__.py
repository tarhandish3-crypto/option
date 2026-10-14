# position_saver/__init__.py
# -*- coding: utf-8 -*-

"""
پکیج مدیریت، ثبت و ایمپورت موقعیت‌های استراتژی آپشن.

نحوه استفاده:
    # ۱. مستقل
    python -m position_saver.main

    # ۲. الحاق به برنامه‌ی مادر
    from position_saver import (
        create_position_saver_widget,
        set_snapshot_provider,
        set_bale_provider,
        set_settings_provider,
    )

    set_snapshot_provider(get_market_snapshot)
    widget = create_position_saver_widget(parent=self)
    main_tabs.addTab(widget, "مدیریت موقعیت‌ها")

معماری سه‌سطحی:
    - OptionLeg: معامله‌ی خام
    - StrategyPosition: واحد معاملاتی (Lot)
    - StrategyGroup: ماسک گروه‌بندی استراتژی
"""


# ═══════════════════════════════════════════════════
# ۱. sys.path
# ═══════════════════════════════════════════════════

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ═══════════════════════════════════════════════════
# ۲. متادیتا
# ═══════════════════════════════════════════════════

__version__ = "3.0.0"
__author__ = "Position Saver"
__description__ = (
    "مدیریت، ثبت و ایمپورت موقعیت‌های استراتژی آپشن — "
    "با معماری سه‌سطحی"
)


# ═══════════════════════════════════════════════════
# ۳. Integration Layer (از providers)
# ═══════════════════════════════════════════════════

from position_saver.providers import (
    set_snapshot_provider,
    set_bale_provider,
    set_settings_provider,
    get_market_snapshot,
    get_bale_notifier,
    get_setting,
    get_commission_rate,
)


# ═══════════════════════════════════════════════════
# ۴. مدل‌های داده (سه‌سطحی)
# ═══════════════════════════════════════════════════

from position_saver.models import (
    # Enumها
    LegType,
    PositionStatus,
    # سطح ۱
    OptionLeg,
    # سطح ۲
    StrategyPosition,
    # سطح ۳
    StrategyGroup,
)


# ═══════════════════════════════════════════════════
# ۵. ذخیره‌سازی
# ═══════════════════════════════════════════════════

from position_saver.storage import (
    PositionStorage,
    # توابع کمکی
    normalize_symbol,
    clean_int,
    clean_float,
    today_jalali,
    infer_option_kind,
    infer_underlying_symbol,
    # ثابت‌ها
    DATA_VERSION,
)


# ═══════════════════════════════════════════════════
# ۶. محاسبات
# ═══════════════════════════════════════════════════

from position_saver.pnl_calculator import PositionPnLCalculator


# ═══════════════════════════════════════════════════
# ۷. State یادآور
# ═══════════════════════════════════════════════════

from position_saver.reminder_state import ReminderState


# ═══════════════════════════════════════════════════
# ۸. ترد پس‌زمینه
# ═══════════════════════════════════════════════════

from position_saver.live_monitor import (
    LivePositionMonitorThread,
    BaleSendWorker,
    is_expired_date,
)


# ═══════════════════════════════════════════════════
# ۹. تم
# ═══════════════════════════════════════════════════

from position_saver.theme import (
    Theme,
    CURRENCY,
    QSS,
    apply_theme,
    fmt_money,
    fmt_pct,
    fmt_pnl,
    fmt_int,
    fmt_date,
    fmt_datetime,
    pnl_tone,
    days_tone,
    tone_color,
    set_kind,
    set_tone,
    set_invalid,
)


# ═══════════════════════════════════════════════════
# ۱۰. Widget Factory (lazy)
# ═══════════════════════════════════════════════════

def create_position_saver_widget(
    parent=None,
    storage_path=None,
    auto_start_monitor=True,
):
    """
    ساخت ویجت Position Saver.

    این تابع به‌صورت lazy import از position_saver.main استفاده می‌کند
    تا از circular import جلوگیری شود.
    """
    from position_saver.main import (
        create_position_saver_widget as _factory,
    )
    return _factory(
        parent=parent,
        storage_path=storage_path,
        auto_start_monitor=auto_start_monitor,
    )


# ═══════════════════════════════════════════════════
# ۱۱. دسترسی‌های lazy به UI
# ═══════════════════════════════════════════════════

def _get_widget_class():
    """دریافت PositionSaverWidget به‌صورت lazy"""
    from position_saver.ui.main_widget import PositionSaverWidget
    return PositionSaverWidget


def _get_dialogs():
    """دریافت دیالوگ‌ها به‌صورت lazy"""
    from position_saver.ui.dialogs import (
        PositionEditDialog,
        CashSettlementDialog,
        OffsetDialog,
        ImportHistoryDialog,
        ExerciseTypeDialog,
        BROKER_NAMES,
        DEFAULT_BROKER,
    )
    return {
        "PositionEditDialog": PositionEditDialog,
        "CashSettlementDialog": CashSettlementDialog,
        "OffsetDialog": OffsetDialog,
        "ImportHistoryDialog": ImportHistoryDialog,
        "ExerciseTypeDialog": ExerciseTypeDialog,
        "BROKER_NAMES": BROKER_NAMES,
        "DEFAULT_BROKER": DEFAULT_BROKER,
    }


# ─── ثابت‌های UI (با محافظت) ───
try:
    from position_saver.ui.dialogs import (
        BROKER_NAMES,
        DEFAULT_BROKER,
    )
except ImportError:
    BROKER_NAMES = [
        "مفید", "خبرگان سهام", "پیشرو", "پارسیان", "سایر"]
    DEFAULT_BROKER = "مفید"


# ═══════════════════════════════════════════════════
# ۱۲. ثابت‌های مشترک
# ═══════════════════════════════════════════════════

STANDARD_STRATEGIES = PositionPnLCalculator.STANDARD_STRATEGIES


# ═══════════════════════════════════════════════════
# ۱۳. Importer (با محافظت)
# ═══════════════════════════════════════════════════

try:
    from position_saver.importer import (
        # Schemas
        TradeRecord,
        MatchedLot,
        ImportSettings,
        ImportBatch,
        ImportResult,
        BrokerTemplate,
        # close_reason constants
        CLOSE_REASON_OPEN,
        CLOSE_REASON_OFFSET,
        CLOSE_REASON_EXERCISE,
        CLOSE_REASON_CASH_SETTLE,
        CLOSE_REASON_DEFAULTED,
        CLOSE_REASON_YOU_DEFAULTED,
        CLOSE_REASON_UNKNOWN,
        CLOSE_REASON_STOCK,
        CLOSE_REASON_INCOMPLETE,
        CLOSE_REASON_LABELS,
        # Symbol Map
        SYMBOL_MAP,
        CODE_TO_SYMBOL,
        is_known_underlying,
        get_underlying_ins_code,
        get_symbol_by_ins_code,
        is_option_symbol,
        infer_underlying_from_option,
        # Symbol Memory
        get_symbol_info,
        has_symbol,
        save_symbol_info,
        save_from_trade,
        save_bulk as save_symbols_bulk,
        get_all_symbol_memory,
        get_symbol_memory_count,
        clear_symbol_memory,
        clear_all_symbol_memory,
        export_symbol_memory,
        import_symbol_memory,
        # Net Position
        compute_net_position,
        group_by_symbol,
        MatchInfo,
        NetPositionResult,
        # Core
        ImportEngine,
        ExcelParser,
        FifoMatcher,
        SnapshotEnricher,
        suggest_strategy_name,
        # Templates
        get_default_template,
        get_all_templates,
        get_template_for_broker,
        list_broker_names,
        save_user_template,
    )
    _IMPORTER_AVAILABLE = True
except ImportError as _e:
    _IMPORTER_AVAILABLE = False

    # ─── placeholderها ───
    TradeRecord = None
    MatchedLot = None
    ImportSettings = None
    ImportBatch = None
    ImportResult = None
    BrokerTemplate = None

    CLOSE_REASON_OPEN = "open"
    CLOSE_REASON_OFFSET = "offset"
    CLOSE_REASON_EXERCISE = "exercise"
    CLOSE_REASON_CASH_SETTLE = "cash_settle"
    CLOSE_REASON_DEFAULTED = "defaulted"
    CLOSE_REASON_YOU_DEFAULTED = "you_defaulted"
    CLOSE_REASON_UNKNOWN = "unknown"
    CLOSE_REASON_STOCK = "stock"
    CLOSE_REASON_INCOMPLETE = "incomplete"
    CLOSE_REASON_LABELS = {}

    SYMBOL_MAP = {}
    CODE_TO_SYMBOL = {}
    is_known_underlying = None
    get_underlying_ins_code = None
    get_symbol_by_ins_code = None
    is_option_symbol = None
    infer_underlying_from_option = None

    get_symbol_info = None
    has_symbol = None
    save_symbol_info = None
    save_from_trade = None
    save_symbols_bulk = None
    get_all_symbol_memory = None
    get_symbol_memory_count = None
    clear_symbol_memory = None
    clear_all_symbol_memory = None
    export_symbol_memory = None
    import_symbol_memory = None

    compute_net_position = None
    group_by_symbol = None
    MatchInfo = None
    NetPositionResult = None

    ImportEngine = None
    ExcelParser = None
    FifoMatcher = None
    SnapshotEnricher = None
    suggest_strategy_name = None

    get_default_template = None
    get_all_templates = None
    get_template_for_broker = None
    list_broker_names = None
    save_user_template = None


# ═══════════════════════════════════════════════════
# ۱۴. Wizard ایمپورت (با محافظت)
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.import_wizard_dialog import (
        ImportWizardDialog,
    )
    _IMPORT_WIZARD_AVAILABLE = True
except ImportError:
    _IMPORT_WIZARD_AVAILABLE = False
    ImportWizardDialog = None


# ═══════════════════════════════════════════════════
# ۱۵. دیالوگ‌های تخصصی (با محافظت)
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.net_position_dialog import (
        NetPositionDialog,
    )
    _NET_POSITION_AVAILABLE = True
except ImportError:
    _NET_POSITION_AVAILABLE = False
    NetPositionDialog = None


try:
    from position_saver.ui.strategy_dialog import (
        StrategyDialog,
    )
    _STRATEGY_DIALOG_AVAILABLE = True
except ImportError:
    _STRATEGY_DIALOG_AVAILABLE = False
    StrategyDialog = None


# ═══════════════════════════════════════════════════
# ۱۶. __all__
# ═══════════════════════════════════════════════════

__all__ = [
    # ─── متادیتا ───
    "__version__",
    "__author__",
    "__description__",

    # ─── Integration ───
    "create_position_saver_widget",
    "set_snapshot_provider",
    "set_bale_provider",
    "set_settings_provider",
    "get_market_snapshot",
    "get_bale_notifier",
    "get_setting",
    "get_commission_rate",

    # ─── Enumها ───
    "LegType",
    "PositionStatus",

    # ─── مدل‌ها (سه‌سطحی) ───
    "OptionLeg",
    "StrategyPosition",
    "StrategyGroup",

    # ─── ذخیره‌سازی ───
    "PositionStorage",
    "normalize_symbol",
    "clean_int",
    "clean_float",
    "today_jalali",
    "infer_option_kind",
    "infer_underlying_symbol",
    "DATA_VERSION",

    # ─── محاسبات ───
    "PositionPnLCalculator",
    "STANDARD_STRATEGIES",

    # ─── State ───
    "ReminderState",

    # ─── ترد ───
    "LivePositionMonitorThread",
    "BaleSendWorker",
    "is_expired_date",

    # ─── UI — Widget ───
    "PositionSaverWidget",

    # ─── UI — دیالوگ‌ها ───
    "ImportWizardDialog",
    "NetPositionDialog",
    "StrategyDialog",

    # ─── ثابت‌های UI ───
    "BROKER_NAMES",
    "DEFAULT_BROKER",

    # ─── تم ───
    "Theme",
    "CURRENCY",
    "QSS",
    "apply_theme",

    # ─── قالب‌بندی ───
    "fmt_money",
    "fmt_pct",
    "fmt_pnl",
    "fmt_int",
    "fmt_date",
    "fmt_datetime",

    # ─── tone ───
    "pnl_tone",
    "days_tone",
    "tone_color",

    # ─── استایل ───
    "set_kind",
    "set_tone",
    "set_invalid",

    # ─── Importer — Schemas ───
    "TradeRecord",
    "MatchedLot",
    "ImportSettings",
    "ImportBatch",
    "ImportResult",
    "BrokerTemplate",

    # ─── close_reason ───
    "CLOSE_REASON_OPEN",
    "CLOSE_REASON_OFFSET",
    "CLOSE_REASON_EXERCISE",
    "CLOSE_REASON_CASH_SETTLE",
    "CLOSE_REASON_DEFAULTED",
    "CLOSE_REASON_YOU_DEFAULTED",
    "CLOSE_REASON_UNKNOWN",
    "CLOSE_REASON_STOCK",
    "CLOSE_REASON_INCOMPLETE",
    "CLOSE_REASON_LABELS",

    # ─── Symbol Map ───
    "SYMBOL_MAP",
    "CODE_TO_SYMBOL",
    "is_known_underlying",
    "get_underlying_ins_code",
    "get_symbol_by_ins_code",
    "is_option_symbol",
    "infer_underlying_from_option",

    # ─── Symbol Memory ───
    "get_symbol_info",
    "has_symbol",
    "save_symbol_info",
    "save_from_trade",
    "save_symbols_bulk",
    "get_all_symbol_memory",
    "get_symbol_memory_count",
    "clear_symbol_memory",
    "clear_all_symbol_memory",
    "export_symbol_memory",
    "import_symbol_memory",

    # ─── Net Position ───
    "compute_net_position",
    "group_by_symbol",
    "MatchInfo",
    "NetPositionResult",

    # ─── Importer — Core ───
    "ImportEngine",
    "ExcelParser",
    "FifoMatcher",
    "SnapshotEnricher",
    "suggest_strategy_name",

    # ─── Templates ───
    "get_default_template",
    "get_all_templates",
    "get_template_for_broker",
    "list_broker_names",
    "save_user_template",

    # ─── پرچم‌ها ───
    "_IMPORTER_AVAILABLE",
    "_IMPORT_WIZARD_AVAILABLE",
    "_NET_POSITION_AVAILABLE",
    "_STRATEGY_DIALOG_AVAILABLE",
]