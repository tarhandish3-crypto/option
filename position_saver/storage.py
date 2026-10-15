# position_saver/storage.py
# -*- coding: utf-8 -*-

"""
ذخیره‌سازی و بارگذاری موقعیت‌ها و batch های ایمپورت.

ساختار فایل‌ها:
    positions_data.json   → موقعیت‌ها (StrategyPosition)
    import_batches.json   → batch های ایمپورت

نسخه‌ی داده: 4 (بدون groups)
"""

import json
import os
import re
import shutil
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path

import jdatetime

from position_saver.models import (
    StrategyPosition, OptionLeg,
    LegType, PositionStatus,
)
from core.enums import OptionType


logger = logging.getLogger("PositionSaver.Storage")


# ═══════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════

DATA_VERSION = 4  # بدون groups


# ═══════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════

def normalize_symbol(s: str) -> str:
    """نرمال‌سازی نام نماد (تبدیل ی/ک عربی به فارسی)."""
    if not s:
        return ""
    s = str(s).strip()
    s = s.replace('ي', 'ی').replace('ك', 'ک')
    s = s.replace("\u200c", " ")
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def clean_int(value, default: int = 0) -> int:
    """تبدیل ایمن به int."""
    try:
        if value is None:
            return default
        s = str(value).strip()
        s = s.replace(",", "").replace("،", "")
        return abs(int(float(s)))
    except (ValueError, TypeError):
        return default


def clean_float(value, default: float = 0.0) -> float:
    """تبدیل ایمن به float."""
    try:
        if value is None:
            return default
        s = str(value).strip()
        s = s.replace(",", "").replace("،", "")
        return float(s)
    except (ValueError, TypeError):
        return default


def today_jalali() -> str:
    """تاریخ امروز شمسی."""
    try:
        return jdatetime.date.today().strftime("%Y/%m/%d")
    except Exception:
        return ""


def infer_option_kind(symbol: str) -> OptionType:
    """تشخیص نوع نماد از حرف اول."""
    if not symbol:
        return OptionType.STOCK
    s = str(symbol).strip()
    if s.startswith("ض"):
        return OptionType.CALL
    if s.startswith("ط"):
        return OptionType.PUT
    return OptionType.STOCK


def infer_underlying_symbol(symbol: str) -> str:
    """حدس نماد پایه از نام نماد."""
    if not symbol:
        return ""
    s = str(symbol).strip()
    if s.startswith(("ض", "ط")):
        s = s[1:]
    m = re.match(r'([^\d]+)', s)
    if m:
        return m.group(1).strip()
    return s[:4] if len(s) >= 4 else s


# ═══════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════

class PositionStorage:
    """
    ذخیره‌سازی و بارگذاری موقعیت‌ها و batch ها.
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    DEFAULT_FILE = os.path.join(BASE_DIR, "positions_data.json")
    DEFAULT_BATCHES_FILE = os.path.join(BASE_DIR, "import_batches.json")

    BACKUP_SUFFIX = ".bak"

    # ✅ محدودیت زمانی بین پشتیبان‌گیری‌ها
    BACKUP_MIN_INTERVAL_SECONDS = 60

    def __init__(
        self,
        filepath: Optional[str] = None,
        batches_filepath: Optional[str] = None,
    ):
        self.filepath = filepath if filepath else self.DEFAULT_FILE
        self.batches_filepath = (
            batches_filepath if batches_filepath
            else self.DEFAULT_BATCHES_FILE
        )
        self._lock = threading.Lock()
        self._last_backup_time: Optional[datetime] = None

    # ═══════════════════════════════════════════════
    # پشتیبان‌گیری
    # ═══════════════════════════════════════════════

    def _should_backup(self) -> bool:
        """آیا الان باید پشتیبان‌گیری کنیم؟"""
        if self._last_backup_time is None:
            return True
        elapsed = datetime.now() - self._last_backup_time
        return elapsed >= timedelta(
            seconds=self.BACKUP_MIN_INTERVAL_SECONDS)

    def _do_backup(self):
        """پشتیبان‌گیری با محدودیت زمانی."""
        if not os.path.exists(self.filepath):
            return
        if not self._should_backup():
            return
        try:
            shutil.copy2(
                self.filepath,
                self.filepath + self.BACKUP_SUFFIX)
            self._last_backup_time = datetime.now()
        except Exception as e:
            logger.warning(f"Backup failed: {e}")

    # ═══════════════════════════════════════════════
    # ذخیره و بارگذاری موقعیت‌ها
    # ═══════════════════════════════════════════════

    def save_positions(
        self, positions: List[StrategyPosition]
    ) -> bool:
        """ذخیره اتمیک لیست موقعیت‌ها."""
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

                self._do_backup()
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
        """بارگذاری موقعیت‌ها با مهاجرت خودکار."""
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
        """استخراج لیست موقعیت‌ها از هر فرمت."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            positions = raw.get("positions", [])
            if not isinstance(positions, list):
                logger.error(
                    f"Invalid positions type: "
                    f"{type(positions).__name__}")
                return []
            return positions
        return []

    def _try_recover_from_backup(self) -> List[StrategyPosition]:
        """تلاش برای بازیابی از پشتیبان."""
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
    # پشتیبان‌گیری دستی
    # ═══════════════════════════════════════════════

    def create_backup(self) -> bool:
        """ساخت پشتیبان دستی با timestamp."""
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
        """بازیابی از آخرین پشتیبان."""
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
        """پاکسازی کامل همه‌ی داده‌ها."""
        try:
            self.create_backup()
            payload = {
                "version": DATA_VERSION,
                "positions": [],
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            return True
        except Exception as e:
            logger.exception(f"Clear failed: {e}")
            return False

    # ═══════════════════════════════════════════════
    # Import Batch
    # ═══════════════════════════════════════════════

    def save_import_batch(self, batch_dict: dict) -> bool:
        """ذخیره‌ی یک Import Batch."""
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

                os.replace(temp_path, self.batches_filepath)
                logger.info(f"Batch saved: {batch_id}")
                return True

            except Exception as e:
                logger.exception(f"Save batch failed: {e}")
                return False

    def load_import_batches(self) -> List[dict]:
        """بارگذاری همه‌ی Import Batch ها."""
        with self._lock:
            return self._load_batches_raw()

    def _load_batches_raw(self) -> List[dict]:
        """بارگذاری خام batch ها (بدون قفل مجدد)."""
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
        """حذف یک Import Batch."""
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
        """تبدیل لیست موقعیت‌ها به DataFrame."""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas is required")
            return None

        from position_saver.pnl_calculator import (
            PositionPnLCalculator)
        from position_saver.shared_analytics import SharedAnalytics

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

            # اطلاعات آلرت پویا
            days_elapsed = pos.days_elapsed()
            days_total = pos.total_days()
            threshold = SharedAnalytics.calculate_dynamic_threshold(
                pos.target_roi_maturity, days_elapsed)

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
                "Broker": pos.broker_name or "—",
                "Underlying": pos.underlying_symbol,
                "Execution_Date": pos.execution_date,
                "Expiry_Date": pos.expiry_date,
                "Days_Elapsed": days_elapsed,
                "Days_Total": days_total,
                "Days_To_Expiry": pos.days_to_expiry(),
                "Legs": legs_str,
                "Legs_Count": len(pos.legs),
                "Net_Entry_Cost": int(net_cost),
                "Target_ROI_Monthly": pos.target_roi_maturity,
                "Dynamic_Threshold": round(threshold, 3),
                "PnL": int(pnl_value),
                "PnL_ROI_Pct": round(pnl_roi, 2),
                "Alert_Enabled": pos.alert_enabled,
                "Alert_Sent": pos.alert_sent,
                "Price_Target": pos.price_target,
                "Status": pos.status.value,
                "Source": pos.source,
                "Close_Date": pos.close_date or "",
                "Notes": pos.notes or "",
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