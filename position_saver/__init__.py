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

معماری دوسطحی:
    - OptionLeg: معامله‌ی خام
    - StrategyPosition: واحد معاملاتی (Lot) — چند-لگ
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

__version__ = "4.0.0"
__author__ = "Position Saver"
__description__ = (
    "مدیریت، ثبت و ایمپورت موقعیت‌های استراتژی آپشن — "
    "با معماری دوسطحی + آلرت پویا"
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
# ۴. مدل‌های داده (دوسطحی — بدون StrategyGroup)
# ═══════════════════════════════════════════════════

from position_saver.models import (
    # Enumها
    LegType,
    PositionStatus,
    # سطح ۱
    OptionLeg,
    # سطح ۲
    StrategyPosition,
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

from position_saver.pnl_calculator import (
    PositionPnLCalculator,
    STRATEGY_REQUIREMENTS,
)

from position_saver.shared_analytics import SharedAnalytics


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
    pnl_tone,
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
# ۱۱. ثابت‌های مشترک
# ═══════════════════════════════════════════════════

STANDARD_STRATEGIES = PositionPnLCalculator.STANDARD_STRATEGIES


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
# ۱۲. Importer (با محافظت)
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


# ═══════════════════════════════════════════════════
# ۱۳. UI — Widget و دیالوگ‌ها (با محافظت)
# ═══════════════════════════════════════════════════

# ─── Widget اصلی ───
try:
    from position_saver.ui.main_widget import PositionSaverWidget
    _WIDGET_AVAILABLE = True
except ImportError:
    PositionSaverWidget = None
    _WIDGET_AVAILABLE = False


# ─── Wizard ایمپورت ───
try:
    from position_saver.ui.import_wizard_dialog import (
        ImportWizardDialog,
    )
    _IMPORT_WIZARD_AVAILABLE = True
except ImportError:
    _IMPORT_WIZARD_AVAILABLE = False
    ImportWizardDialog = None


# ─── دیالوگ Net Position ───
try:
    from position_saver.ui.net_position_dialog import (
        NetPositionDialog,
    )
    _NET_POSITION_AVAILABLE = True
except ImportError:
    _NET_POSITION_AVAILABLE = False
    NetPositionDialog = None


# ─── دیالوگ Strategy ───
try:
    from position_saver.ui.strategy_dialog import (
        StrategyDialog,
    )
    _STRATEGY_DIALOG_AVAILABLE = True
except ImportError:
    _STRATEGY_DIALOG_AVAILABLE = False
    StrategyDialog = None


# ─── دیالوگ چک استراتژی ───
try:
    from position_saver.ui.strategy_check_dialog import (
        StrategyCheckDialog,
    )
    _STRATEGY_CHECK_AVAILABLE = True
except ImportError:
    _STRATEGY_CHECK_AVAILABLE = False
    StrategyCheckDialog = None


# ─── دیالوگ گزارش ───
try:
    from position_saver.ui.report_dialog import (
        ReportDialog,
        ReportFilter,
        ReportRow,
        ReportResult,
        BaseReportExporter,
        ExcelReportExporter,
    )
    _REPORT_AVAILABLE = True
except ImportError:
    _REPORT_AVAILABLE = False
    ReportDialog = None
    ReportFilter = None
    ReportRow = None
    ReportResult = None
    BaseReportExporter = None
    ExcelReportExporter = None


# ─── دیالوگ Split ───
try:
    from position_saver.ui.split_position_dialog import (
        SplitPositionDialog,
    )
    _SPLIT_AVAILABLE = True
except ImportError:
    _SPLIT_AVAILABLE = False
    SplitPositionDialog = None


# ─── دیالوگ Symbol Fill ───
try:
    from position_saver.ui.symbol_fill_dialog import (
        SymbolFillDialog,
    )
    _SYMBOL_FILL_AVAILABLE = True
except ImportError:
    _SYMBOL_FILL_AVAILABLE = False
    SymbolFillDialog = None


# ═══════════════════════════════════════════════════
# ۱۴. __all__
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

    # ─── مدل‌ها ───
    "OptionLeg",
    "StrategyPosition",

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
    "STRATEGY_REQUIREMENTS",
    "SharedAnalytics",
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
    "StrategyCheckDialog",
    "ReportDialog",
    "SplitPositionDialog",
    "SymbolFillDialog",

    # ─── UI — Report Classes ───
    "ReportFilter",
    "ReportRow",
    "ReportResult",
    "BaseReportExporter",
    "ExcelReportExporter",

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

    # ─── tone ───
    "pnl_tone",

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

    # ─── پرچم‌ها ───
    "_IMPORTER_AVAILABLE",
    "_WIDGET_AVAILABLE",
    "_IMPORT_WIZARD_AVAILABLE",
    "_NET_POSITION_AVAILABLE",
    "_STRATEGY_DIALOG_AVAILABLE",
    "_STRATEGY_CHECK_AVAILABLE",
    "_REPORT_AVAILABLE",
    "_SPLIT_AVAILABLE",
    "_SYMBOL_FILL_AVAILABLE",
]