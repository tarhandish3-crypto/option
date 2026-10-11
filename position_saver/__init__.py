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

__version__ = "2.0.0"
__author__ = "Position Saver"
__description__ = "مدیریت، ثبت و ایمپورت موقعیت‌های استراتژی آپشن"


# ═══════════════════════════════════════════════════
# ۳. Importهای اصلی — همه lazy یا از ماژول‌های پایه
# ═══════════════════════════════════════════════════

# ⚠️ مهم: این importها را از main نگیرید چون main ممکن است
# در حال بارگذاری باشد. به‌جایش تابع wrapper تعریف کنید.


# ─── Providerها (بدون circular) ───
from position_saver.providers import (
    set_snapshot_provider,
    set_bale_provider,
    set_settings_provider,
    get_market_snapshot,
    get_bale_notifier,
    get_setting,
    get_commission_rate,
)


# ─── مدل‌های داده ───
from position_saver.models import (
    StrategyPosition,
    OptionLeg,
    LegType,
    PositionStatus,
)


# ─── ذخیره‌سازی ───
from position_saver.storage import (
    PositionStorage,
    normalize_symbol,
    clean_int,
    clean_float,
    today_jalali,
    infer_option_kind,
    infer_underlying_symbol,
    DATA_VERSION,
)


# ─── محاسبات ───
from position_saver.pnl_calculator import PositionPnLCalculator


# ─── State ───
from position_saver.reminder_state import ReminderState


# ─── ترد ───
from position_saver.live_monitor import (
    LivePositionMonitorThread,
    is_expired_date,
    BaleSendWorker,
)


# ─── تم ───
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
# ۴. ✅ Widget Factory — به‌صورت lazy (بدون import از main)
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
# ۵. UI — به‌صورت lazy (فقط در صورت نیاز)
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
        BROKER_NAMES,
        DEFAULT_BROKER,
    )
    return {
        "PositionEditDialog": PositionEditDialog,
        "CashSettlementDialog": CashSettlementDialog,
        "OffsetDialog": OffsetDialog,
        "ImportHistoryDialog": ImportHistoryDialog,
        "BROKER_NAMES": BROKER_NAMES,
        "DEFAULT_BROKER": DEFAULT_BROKER,
    }


# ─── ثابت‌های UI (بدون lazy — فقط از dialogs می‌آیند) ───
try:
    from position_saver.ui.dialogs import (
        BROKER_NAMES,
        DEFAULT_BROKER,
    )
except ImportError:
    BROKER_NAMES = ["مفید", "خبرگان سهام", "پیشرو", "پارسیان", "سایر"]
    DEFAULT_BROKER = "مفید"


# ═══════════════════════════════════════════════════
# ۶. ثابت‌های مشترک
# ═══════════════════════════════════════════════════

STANDARD_STRATEGIES = PositionPnLCalculator.STANDARD_STRATEGIES


# ═══════════════════════════════════════════════════
# ۷. Importer — با محافظت
# ═══════════════════════════════════════════════════

try:
    from position_saver.importer import (
        TradeRecord,
        MatchedLot,
        ImportSettings,
        ImportBatch,
        ImportResult,
        BrokerTemplate,
        ImportEngine,
        ExcelParser,
        FifoMatcher,
        SnapshotEnricher,
        suggest_strategy_name,
        get_default_template,
        get_all_templates,
        get_template_for_broker,
        list_broker_names,
        save_user_template,
    )
    _IMPORTER_AVAILABLE = True
except ImportError:
    _IMPORTER_AVAILABLE = False
    TradeRecord = None
    MatchedLot = None
    ImportSettings = None
    ImportBatch = None
    ImportResult = None
    BrokerTemplate = None
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
# ۸. Wizard — با محافظت
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
# ۹. __all__
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

    # ─── مدل‌ها ───
    "StrategyPosition",
    "OptionLeg",
    "LegType",
    "PositionStatus",

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
    "is_expired_date",
    "BaleSendWorker",

    # ─── UI ───
    "ImportWizardDialog",

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

    # ─── Importer ───
    "TradeRecord",
    "MatchedLot",
    "ImportSettings",
    "ImportBatch",
    "ImportResult",
    "BrokerTemplate",
    "ImportEngine",
    "ExcelParser",
    "FifoMatcher",
    "SnapshotEnricher",
    "suggest_strategy_name",
    "get_default_template",
    "get_all_templates",
    "get_template_for_broker",
    "list_broker_names",
    "save_user_template",

    # ─── پرچم‌ها ───
    "_IMPORTER_AVAILABLE",
    "_IMPORT_WIZARD_AVAILABLE",
]