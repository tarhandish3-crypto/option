# position_saver/reminder_state.py
# -*- coding: utf-8 -*-

"""
مدیریت state ارسال یادآورهای سررسید.
- حداکثر ۲ یادآور در روز
- فاصله حداقل ۱ ساعت بین یادآورها
- ذخیره در فایل JSON ماندگار
"""

import os
import json
import logging
from datetime import datetime, timedelta

import jdatetime

logger = logging.getLogger("PositionSaver.ReminderState")


class ReminderState:
    """مدیریت state یادآورهای ارسال‌شده"""

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATE_FILE = os.path.join(BASE_DIR, "reminder_state.json")

    MAX_PER_DAY = 2
    MIN_INTERVAL_MINUTES = 60

    def __init__(self, filepath: str = None):
        self.filepath = filepath if filepath else self.STATE_FILE
        self._state = self._load()

    def _load(self) -> dict:
        """بارگذاری state از فایل JSON"""
        if not os.path.exists(self.filepath):
            return self._empty_state()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "last_date": data.get("last_date", ""),
                "count_today": int(data.get("count_today", 0)),
                "last_time_iso": data.get("last_time_iso", ""),
            }
        except Exception as e:
            logger.warning(f"Failed to load reminder state: {e}")
            return self._empty_state()

    def _save(self):
        """ذخیره state در فایل JSON"""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save reminder state: {e}")

    @staticmethod
    def _empty_state() -> dict:
        return {
            "last_date": "",
            "count_today": 0,
            "last_time_iso": "",
        }

    # =====================================================
    # منطق اصلی
    # =====================================================

    def _today_key(self) -> str:
        return jdatetime.date.today().strftime("%Y/%m/%d")

    def _reset_if_new_day(self):
        today = self._today_key()
        if self._state["last_date"] != today:
            self._state["last_date"] = today
            self._state["count_today"] = 0
            self._state["last_time_iso"] = ""
            self._save()

    def can_send(self) -> tuple:
        """
        آیا اجازه ارسال داریم؟
        Returns: (allowed: bool, reason: str)
        """
        self._reset_if_new_day()

        if self._state["count_today"] >= self.MAX_PER_DAY:
            return (
                False,
                f"حداکثر {self.MAX_PER_DAY} یادآور در روز ارسال شده"
            )

        last_iso = self._state.get("last_time_iso", "")
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
                elapsed = datetime.now() - last_dt
                min_interval = timedelta(minutes=self.MIN_INTERVAL_MINUTES)
                if elapsed < min_interval:
                    remaining = min_interval - elapsed
                    mins = int(remaining.total_seconds() / 60)
                    return (
                        False,
                        f"حداقل {self.MIN_INTERVAL_MINUTES} دقیقه فاصله "
                        f"لازم است ({mins} دقیقه مانده)"
                    )
            except Exception:
                pass

        return (True, "OK")

    def mark_sent(self):
        """ثبت ارسال موفق"""
        self._reset_if_new_day()
        self._state["count_today"] += 1
        self._state["last_time_iso"] = datetime.now().isoformat()
        self._save()

    def get_status(self) -> dict:
        """وضعیت فعلی"""
        self._reset_if_new_day()
        return {
            "date": self._state["last_date"],
            "count_today": self._state["count_today"],
            "max_per_day": self.MAX_PER_DAY,
            "last_time": self._state["last_time_iso"],
        }
