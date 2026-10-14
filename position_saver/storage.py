# position_saver/storage.py
# -*- coding: utf-8 -*-

"""
ذخیره‌سازی و بارگذاری موقعیت‌ها، گروه‌ها و batch های ایمپورت.

ساختار فایل‌ها:
    positions_data.json   → موقعیت‌ها (StrategyPosition)
    groups_data.json      → گروه‌های استراتژی (StrategyGroup)
    import_batches.json   → batch های ایمپورت

نسخه‌ی داده: 3
"""

import json
import os
import re
import shutil
import threading
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

import jdatetime

from position_saver.models import (
    StrategyPosition, StrategyGroup, OptionLeg,
    LegType, PositionStatus,
)
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.Storage")


# ═══════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════

# نسخه‌ی فرمت داده — برای مهاجرت خودکار
DATA_VERSION = 3

# نسخه‌های قدیمی
DATA_VERSION_V1 = 1     # آرایه‌ی ساده
DATA_VERSION_V2 = 2     # {version, positions}
DATA_VERSION_V3 = 3     # {version, positions, groups}


# ═══════════════════════════════════════════════════
# توابع کمکی (عمومی)
# ═══════════════════════════════════════════════════

def normalize_symbol(s: str) -> str:
    """نرمال‌سازی نام نماد (تبدیل ی/ک عربی به فارسی)"""
    if not s:
        return ""
    s = str(s).strip()
    s = s.replace('ي', 'ی').replace('ك', 'ک')
    s = s.replace("\u200c", " ")
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def clean_int(value, default: int = 0) -> int:
    """تبدیل ایمن به int"""
    try:
        if value is None:
            return default
        s = str(value).strip()
        s = s.replace(",", "").replace("،", "")
        return abs(int(float(s)))
    except (ValueError, TypeError):
        return default


def clean_float(value, default: float = 0.0) -> float:
    """تبدیل ایمن به float"""
    try:
        if value is None:
            return default
        s = str(value).strip()
        s = s.replace(",", "").replace("،", "")
        return float(s)
    except (ValueError, TypeError):
        return default


def today_jalali() -> str:
    """تاریخ امروز شمسی به فرمت YYYY/MM/DD"""
    try:
        return jdatetime.date.today().strftime("%Y/%m/%d")
    except Exception:
        return ""


def infer_option_kind(symbol: str) -> OptionType:
    """تشخیص نوع نماد از حرف اول"""
    if not symbol:
        return OptionType.STOCK
    s = str(symbol).strip()
    if s.startswith("ض"):
        return OptionType.CALL
    if s.startswith("ط"):
        return OptionType.PUT
    return OptionType.STOCK


def infer_underlying_symbol(symbol: str) -> str:
    """حدس نماد پایه از نام نماد"""
    if not symbol:
        return ""
    s = str(symbol).strip()
    if s.startswith(("ض", "ط")):
        s = s[1:]
    m = re.match(r'([^\d]+)', s)
    if m:
        return m.group(1).strip()
    return s[:4] if len(s) >= 4 else s


# نگه‌داشتن نام‌های قدیمی برای سازگاری
_normalize_symbol = normalize_symbol
_clean_int = clean_int
_clean_float = clean_float
_today_jalali = today_jalali
_infer_option_kind = infer_option_kind
_infer_underlying_symbol = infer_underlying_symbol


# ═══════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════

class PositionStorage:
    """
    ذخیره‌سازی و بارگذاری موقعیت‌ها، گروه‌ها و batch ها.

    ویژگی‌ها:
        - مسیر پیش‌فرض: پوشه‌ی position_saver/
        - ذخیره اتمیک با os.replace
        - قفل threading
        - پشتیبان‌گیری خودکار (.bak)
        - مهاجرت خودکار نسخه‌ها (v1 → v2 → v3)
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    DEFAULT_FILE = os.path.join(BASE_DIR, "positions_data.json")
    DEFAULT_GROUPS_FILE = os.path.join(BASE_DIR, "groups_data.json")
    DEFAULT_BATCHES_FILE = os.path.join(BASE_DIR, "import_batches.json")

    BACKUP_SUFFIX = ".bak"

    def __init__(
        self,
        filepath: Optional[str] = None,
        batches_filepath: Optional[str] = None,
        groups_filepath: Optional[str] = None,
    ):
        self.filepath = filepath if filepath else self.DEFAULT_FILE
        self.groups_filepath = (
            groups_filepath if groups_filepath
            else self.DEFAULT_GROUPS_FILE
        )
        self.batches_filepath = (
            batches_filepath if batches_filepath
            else self.DEFAULT_BATCHES_FILE
        )
        self._lock = threading.Lock()

    # ═══════════════════════════════════════════════
    # ذخیره و بارگذاری موقعیت‌ها
    # ═══════════════════════════════════════════════

    def save_positions(
        self, positions: List[StrategyPosition]
    ) -> bool:
        """
        ذخیره اتمیک لیست موقعیت‌ها.

        ساختار جدید (v3):
            {
                "version": 3,
                "positions": [...]
            }
        """
        with self._lock:
            try:
                payload = {
                    "version": DATA_VERSION,
                    "positions": [
                        pos.to_dict() for pos in positions
                    ],
                }

                temp_path = self.filepath + ".tmp"

                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):
                        pass

                # پشتیبان‌گیری
                if os.path.exists(self.filepath):
                    try:
                        shutil.copy2(
                            self.filepath,
                            self.filepath + self.BACKUP_SUFFIX)
                    except Exception as e:
                        logger.warning(f"Backup failed: {e}")

                os.replace(temp_path, self.filepath)
                logger.info(
                    f"Saved {len(positions)} positions")
                return True

            except Exception as e:
                logger.exception(f"Save failed: {e}")
                temp_path = self.filepath + ".tmp"
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return False

    def load_positions(self) -> List[StrategyPosition]:
        """
        بارگذاری موقعیت‌ها با مهاجرت خودکار.

        پشتیبانی از:
            - v1: آرایه‌ی ساده
            - v2: {version, positions}
            - v3: {version, positions}
        """
        with self._lock:
            if not os.path.exists(self.filepath):
                return []

            try:
                with open(self.filepath, "r",
                          encoding="utf-8") as f:
                    raw = json.load(f)

                items = self._extract_positions(raw)
                result = []
                for item in items:
                    try:
                        result.append(
                            StrategyPosition.from_dict(item))
                    except Exception as e:
                        logger.warning(
                            f"Skipping invalid position: {e}")
                        continue

                logger.info(f"Loaded {len(result)} positions")
                return result

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                return self._try_recover_from_backup()
            except Exception as e:
                logger.exception(f"Load failed: {e}")
                return []

    @staticmethod
    def _extract_positions(raw) -> list:
        """استخراج لیست موقعیت‌ها از هر فرمت"""
        if isinstance(raw, list):
            # v1 — آرایه ساده
            return raw
        if isinstance(raw, dict):
            # v2/v3 — {version, positions}
            return raw.get("positions", [])
        return []

    def _try_recover_from_backup(self) -> List[StrategyPosition]:
        """تلاش برای بازیابی از پشتیبان"""
        backup_path = self.filepath + self.BACKUP_SUFFIX
        if not os.path.exists(backup_path):
            return []

        try:
            logger.info("Attempting recovery from backup...")
            with open(backup_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            items = self._extract_positions(raw)
            return [StrategyPosition.from_dict(item)
                    for item in items]
        except Exception as e:
            logger.exception(f"Recovery failed: {e}")
            return []

    # ═══════════════════════════════════════════════
    # ✅ ذخیره و بارگذاری گروه‌ها
    # ═══════════════════════════════════════════════

    def save_groups(self, groups: List[StrategyGroup]) -> bool:
        """ذخیره‌ی لیست گروه‌های استراتژی"""
        with self._lock:
            try:
                payload = {
                    "version": DATA_VERSION,
                    "groups": [g.to_dict() for g in groups],
                }

                temp_path = self.groups_filepath + ".tmp"

                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):
                        pass

                if os.path.exists(self.groups_filepath):
                    try:
                        shutil.copy2(
                            self.groups_filepath,
                            self.groups_filepath + self.BACKUP_SUFFIX)
                    except Exception as e:
                        logger.warning(f"Backup failed: {e}")

                os.replace(temp_path, self.groups_filepath)
                logger.info(f"Saved {len(groups)} groups")
                return True

            except Exception as e:
                logger.exception(f"Save groups failed: {e}")
                temp_path = self.groups_filepath + ".tmp"
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return False

    def load_groups(self) -> List[StrategyGroup]:
        """بارگذاری لیست گروه‌ها"""
        with self._lock:
            if not os.path.exists(self.groups_filepath):
                return []

            try:
                with open(self.groups_filepath, "r",
                          encoding="utf-8") as f:
                    raw = json.load(f)

                if isinstance(raw, dict):
                    items = raw.get("groups", [])
                elif isinstance(raw, list):
                    items = raw
                else:
                    return []

                result = []
                for item in items:
                    try:
                        result.append(
                            StrategyGroup.from_dict(item))
                    except Exception as e:
                        logger.warning(
                            f"Skipping invalid group: {e}")
                        continue

                logger.info(f"Loaded {len(result)} groups")
                return result

            except Exception as e:
                logger.exception(f"Load groups failed: {e}")
                return []

    def delete_group(self, group_id: str) -> bool:
        """حذف یک گروه"""
        with self._lock:
            try:
                groups = self.load_groups()
                new_groups = [
                    g for g in groups if g.group_id != group_id]
                if len(new_groups) == len(groups):
                    return False
                return self.save_groups(new_groups)
            except Exception as e:
                logger.exception(f"Delete group failed: {e}")
                return False

    # ═══════════════════════════════════════════════
    # پشتیبان‌گیری و بازیابی
    # ═══════════════════════════════════════════════

    def create_backup(self) -> bool:
        """ساخت پشتیبان دستی با timestamp"""
        if not os.path.exists(self.filepath):
            return False
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.filepath}.{timestamp}.bak"
            shutil.copy2(self.filepath, backup_path)
            logger.info(f"Backup created: {backup_path}")
            return True
        except Exception as e:
            logger.exception(f"Backup failed: {e}")
            return False

    def restore_from_backup(self) -> bool:
        """بازیابی از آخرین پشتیبان"""
        backup_path = self.filepath + self.BACKUP_SUFFIX
        if not os.path.exists(backup_path):
            return False
        try:
            shutil.copy2(backup_path, self.filepath)
            logger.info(f"Restored from {backup_path}")
            return True
        except Exception as e:
            logger.exception(f"Restore failed: {e}")
            return False

    def clear_all(self) -> bool:
        """پاکسازی کامل همه‌ی داده‌ها"""
        try:
            self.create_backup()
            payload = {
                "version": DATA_VERSION,
                "positions": [],
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            # پاکسازی گروه‌ها
            with open(self.groups_filepath, "w",
                      encoding="utf-8") as f:
                json.dump(
                    {"version": DATA_VERSION, "groups": []},
                    f, ensure_ascii=False)

            return True
        except Exception as e:
            logger.exception(f"Clear failed: {e}")
            return False

    # ═══════════════════════════════════════════════
    # Import Batch Management
    # ═══════════════════════════════════════════════

    def save_import_batch(self, batch_dict: dict) -> bool:
        """ذخیره‌ی یک Import Batch"""
        with self._lock:
            try:
                batches = self._load_batches_raw()
                batch_id = batch_dict.get("batch_id", "")

                batches = [
                    b for b in batches
                    if b.get("batch_id") != batch_id
                ]
                batches.append(batch_dict)

                batches.sort(
                    key=lambda b: b.get("created_at", ""),
                    reverse=True,
                )

                temp_path = self.batches_filepath + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(batches, f,
                              ensure_ascii=False, indent=2)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):
                        pass

                if os.path.exists(self.batches_filepath):
                    try:
                        shutil.copy2(
                            self.batches_filepath,
                            self.batches_filepath
                            + self.BACKUP_SUFFIX)
                    except Exception:
                        pass

                os.replace(temp_path, self.batches_filepath)
                logger.info(f"Batch saved: {batch_id}")
                return True

            except Exception as e:
                logger.exception(f"Save batch failed: {e}")
                return False

    def load_import_batches(self) -> List[dict]:
        """بارگذاری همه‌ی Import Batch ها"""
        with self._lock:
            return self._load_batches_raw()

    def _load_batches_raw(self) -> List[dict]:
        """بارگذاری خام batch ها (بدون قفل مجدد)"""
        if not os.path.exists(self.batches_filepath):
            return []
        try:
            with open(self.batches_filepath, "r",
                      encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.warning(f"Load batches failed: {e}")
            return []

    def delete_import_batch(self, batch_id: str) -> bool:
        """حذف یک Import Batch"""
        with self._lock:
            try:
                batches = self._load_batches_raw()
                new_batches = [
                    b for b in batches
                    if b.get("batch_id") != batch_id
                ]

                if len(new_batches) == len(batches):
                    return False

                temp_path = self.batches_filepath + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(new_batches, f,
                              ensure_ascii=False, indent=2)

                os.replace(temp_path, self.batches_filepath)
                logger.info(f"Batch deleted: {batch_id}")
                return True

            except Exception as e:
                logger.exception(f"Delete batch failed: {e}")
                return False

    # ═══════════════════════════════════════════════
    # Export به DataFrame
    # ═══════════════════════════════════════════════

    @staticmethod
    def positions_to_dataframe(positions: List[StrategyPosition]):
        """تبدیل لیست موقعیت‌ها به DataFrame"""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas is required")
            return None

        # import داخل تابع برای جلوگیری از circular
        from position_saver.pnl_calculator import (
            PositionPnLCalculator)

        rows = []
        for pos in positions:
            net_cost = (
                PositionPnLCalculator.calculate_net_entry_cost(pos)
            )
            live_pnl, live_roi = (
                PositionPnLCalculator.calculate_live_pnl(pos)
            )
            realized_pnl, realized_roi = (
                PositionPnLCalculator.calculate_realized_pnl(pos)
            )

            legs_str = " | ".join([
                f"{l.leg_type.label_fa}: {l.symbol} "
                f"(تعداد: {l.quantity}, "
                f"ورود: {int(l.entry_price):,})"
                for l in pos.legs
            ])

            if pos.status == PositionStatus.OPEN:
                pnl_value = live_pnl
                pnl_roi = live_roi
            else:
                pnl_value = realized_pnl
                pnl_roi = realized_roi

            rows.append({
                "Position_ID": pos.position_id,
                "Strategy_Name": pos.strategy_name,
                "Strategy_Type": pos.strategy_type,
                "Group_ID": pos.group_id,
                "Broker": pos.broker_name or "—",
                "Underlying": pos.underlying_symbol,
                "Execution_Date": pos.execution_date,
                "Expiry_Date": pos.expiry_date,
                "Days_To_Expiry": pos.days_to_expiry(),
                "Legs": legs_str,
                "Legs_Count": len(pos.legs),
                "Net_Entry_Cost": int(net_cost),
                "Target_ROI_Pct": pos.target_roi_maturity,
                "PnL": int(pnl_value),
                "PnL_ROI_Pct": round(pnl_roi, 2),
                "Alert_Target_ROI_Pct": pos.alert_target_roi,
                "Status": pos.status.value,
                "Source": pos.source,
                "Close_Date": pos.close_date or "",
                "Notes": pos.notes or "",
            })

        return pd.DataFrame(rows)

    @staticmethod
    def groups_to_dataframe(groups: List[StrategyGroup],
                             positions: List[StrategyPosition]):
        """تبدیل لیست گروه‌ها به DataFrame"""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas is required")
            return None

        rows = []
        for g in groups:
            live_pnl = g.total_live_pnl(positions)
            realized = g.total_realized_pnl(positions)
            open_cost = g.total_open_cost(positions)
            is_closed = g.is_fully_closed(positions)

            rows.append({
                "Group_ID": g.group_id,
                "Strategy_Type": g.strategy_type,
                "Display_Name": g.display_name,
                "Num_Positions": g.num_positions,
                "Live_PnL": int(live_pnl),
                "Realized_PnL": int(realized),
                "Open_Cost": int(open_cost),
                "Is_Fully_Closed": is_closed,
                "Created_At": g.created_at,
                "Notes": g.notes or "",
            })

        return pd.DataFrame(rows)


__all__ = [
    "PositionStorage",
    "normalize_symbol",
    "clean_int",
    "clean_float",
    "today_jalali",
    "infer_option_kind",
    "infer_underlying_symbol",
    "DATA_VERSION",
]