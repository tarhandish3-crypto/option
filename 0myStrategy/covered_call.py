# 0myStrategy/covered_call.py
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from data.manager import DataManager

data_manager = DataManager()
snapshot = data_manager.get_market_snapshot(force_refresh=False, calc_advanced=False)
print(snapshot)