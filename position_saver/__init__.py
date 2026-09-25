# position_saver/__init__.py
# -*- coding: utf-8 -*-


from position_saver.reminder_state import ReminderState
from position_saver.ui.dialogs import PositionEditDialog
from position_saver.ui.main_widget import PositionSaverWidget
from position_saver.live_monitor import LivePositionMonitorThread
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.storage import PositionStorage
from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,)
import os
import sys

# افزودن مسیر ریشه پروژه اصلی به sys.path
# تا ماژول‌های config, core, data, alerts قابل import باشند
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# صادرکننده‌های اصلی

__all__ = [
    "StrategyPosition",
    "OptionLeg",
    "LegType",
    "PositionStatus",
    "PositionStorage",
    "PositionPnLCalculator",
    "LivePositionMonitorThread",
    "PositionSaverWidget",
    "PositionEditDialog",
    "ReminderState",
]
