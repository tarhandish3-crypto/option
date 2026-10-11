# position_saver/live_monitor.py
# -*- coding: utf-8 -*-

import logging
import json
import re
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import jdatetime
from PySide6.QtCore import QThread, Signal, Slot

from position_saver.storage import PositionStorage
from position_saver.models import PositionStatus, LegType
from position_saver.reminder_state import ReminderState
from position_saver.pnl_calculator import PositionPnLCalculator
from position_saver.theme import fmt_money, fmt_pct, fmt_int
from position_saver.providers import get_market_snapshot, get_bale_notifier


logger = logging.getLogger("PositionSaver.LiveMonitor")


# =====================================================
# توابع کمکی: بررسی انقضای تاریخ شمسی
# =====================================================

def is_expired_date(expiry_date_str: str) -> bool:
    """
    بررسی منقضی شدن تاریخ شمسی.

    پشتیبانی از فرمت‌های متغیر:
        1403/06/24   → اسلش با صفر پیشرو
        1403-06-24   → خط تیره
        1403/6/24    → بدون صفر پیشرو
    """
    if not expiry_date_str:
        return False
    try:
        s = str(expiry_date_str).strip()
        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
        if not m:
            return False
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        expiry = jdatetime.date(year, month, day)
        return expiry < jdatetime.date.today()
    except Exception as e:
        logger.warning(f"Error parsing expiry_date '{expiry_date_str}': {e}")
        return False


def _parse_jalali_date(date_str: str):
    """تبدیل رشته تاریخ شمسی به jdatetime.date"""
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
        if not m:
            return None
        return jdatetime.date(
            int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


# =====================================================
# توابع کمکی: خواندن تنظیمات بله
# =====================================================

def _load_user_settings() -> dict:
    """بارگذاری user_settings.json"""
    try:
        from config import USER_SETTINGS_PATH
        if not USER_SETTINGS_PATH.exists():
            return {}
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[Settings] Load failed: {e}")
        return {}


def _extract_bale(bale_dict: dict) -> Tuple[str, str]:
    """استخراج bot_token و chat_id از دیکشنری bale"""
    if not isinstance(bale_dict, dict):
        return "", ""

    enabled = bale_dict.get("enabled", True)
    if enabled is False:
        return "", ""

    token = str(bale_dict.get("bot_token", "")).strip()
    chat = str(bale_dict.get("chat_id", "")).strip()

    if not token:
        token = str(bale_dict.get("bale_bot_token", "")).strip()
    if not chat:
        chat = str(bale_dict.get("bale_chat_id", "")).strip()

    return token, chat


def _is_bale_enabled() -> bool:
    """بررسی فعال بودن بله در تنظیمات"""
    try:
        data = _load_user_settings()
        profiles = data.get("profiles", {})
        active_profile = data.get("active_profile", "")

        if active_profile and active_profile in profiles:
            profile_data = profiles[active_profile]
            bale = profile_data.get("bale", {})
            if isinstance(bale, dict):
                return bool(bale.get("enabled", True))

        return True
    except Exception as e:
        logger.warning(f"[Bale] Error checking enabled: {e}")
        return True


def _get_bale_credentials() -> Tuple[str, str]:
    """خواندن bot_token و chat_id بله از user_settings.json"""
    try:
        data = _load_user_settings()
        profiles = data.get("profiles", {})
        active_profile = data.get("active_profile", "")

        # ۱. اول پروفایل فعال
        if active_profile and active_profile in profiles:
            profile_data = profiles[active_profile]
            bale = profile_data.get("bale", {})
            token, chat = _extract_bale(bale)
            if token and chat:
                logger.info(
                    f"[Bale] Credentials loaded from active profile "
                    f"'{active_profile}'")
                return token, chat

        # ۲. همه پروفایل‌ها
        for profile_name, profile_data in profiles.items():
            bale = profile_data.get("bale", {})
            token, chat = _extract_bale(bale)
            if token and chat:
                logger.info(
                    f"[Bale] Credentials loaded from profile "
                    f"'{profile_name}'")
                return token, chat

        # ۳. سطح بالا
        bale = data.get("bale", {})
        token, chat = _extract_bale(bale)
        if token and chat:
            logger.info("[Bale] Credentials loaded from top-level 'bale'")
            return token, chat

        logger.warning("[Bale] No valid bale credentials found")
        return "", ""

    except Exception as e:
        logger.exception(f"[Bale] Error reading credentials: {e}")
        return "", ""


# =====================================================
# ✅ Fallback Notifier — اگر برنامه‌ی مادر notifier نداشت
# =====================================================

class _FallbackBaleNotifier:
    """نسخه‌ی ساده اگر برنامه‌ی مادر notifier نداشت"""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, msg: str, parse_mode: str = "Markdown") -> bool:
        if not self.is_configured:
            return False
        try:
            from alerts.bale_notifier import send_message_to_bale
            result = send_message_to_bale(
                bot_token=self.bot_token,
                chat_id=self.chat_id,
                message_text=msg,
                parse_mode=parse_mode,
            )
            return result is not None
        except Exception as e:
            logger.exception(f"[Bale-Fallback] send failed: {e}")
            return False


# =====================================================
# ✅ Thread جداگانه برای ارسال به بله (جلوگیری از فریز UI)
# =====================================================

class BaleSendWorker(QThread):
    """
    ترد کوچک برای ارسال پیام به بله.
    جلوگیری از فریز شدن UI هنگام ارسال.
    """
    send_finished = Signal(bool, str)  # (success, position_id)

    def __init__(self, notifier, message: str, position_id: str = ""):
        super().__init__()
        self.notifier = notifier
        self.message = message
        self.position_id = position_id

    def run(self):
        try:
            ok = self.notifier.send_message(self.message)
            self.send_finished.emit(ok, self.position_id)
        except Exception as e:
            logger.exception(f"[BaleWorker] {e}")
            self.send_finished.emit(False, self.position_id)


# =====================================================
# ترد پس‌زمینه اصلی
# =====================================================

class LivePositionMonitorThread(QThread):
    """
    ترد پس‌زمینه برای دریافت قیمت‌های لایو از برنامه اصلی.

    ⚠️ این ترد فقط قیمت‌ها، هشدارها و وضعیت اتصال را emit می‌کند و
    هرگز روی لیست موقعیت‌های UI تغییر نمی‌دهد.
    """

    prices_updated = Signal(dict)
    alerts_found = Signal(list)
    expired_found = Signal(list)
    connection_status = Signal(dict)

    def __init__(self, storage: PositionStorage, check_interval: int = 10):
        super().__init__()
        self.storage = storage
        self.check_interval = max(5, check_interval)
        self.is_running = True
        self.auto_refresh_enabled = True
        self.force_refresh_flag = False
        self._wake_event = threading.Event()

        # راه‌اندازی notifier
        self._init_bale_notifier()

        # state یادآور سررسید
        self._reminder_state = ReminderState()

        # کارگرهای در حال اجرا
        self._workers: List[BaleSendWorker] = []

        # شمارنده‌ی حلقه برای پاکسازی دوره‌ای workers
        self._loop_count = 0

        logger.info(
            f"Monitor thread initialized (interval={self.check_interval}s)")

    def _init_bale_notifier(self):
        """
        راه‌اندازی BaleNotifier — از برنامه‌ی مادر یا fallback.
        """
        try:
            if not _is_bale_enabled():
                logger.info("[Bale] Disabled in settings — skipping init")
                self.notifier = _FallbackBaleNotifier()
                return

            # ✅ اول از برنامه‌ی مادر بگیر
            notifier = get_bale_notifier()
            if notifier is not None:
                self.notifier = notifier
                logger.info("[Bale] Notifier from integration layer")
                return

            # ✅ fallback: ساخت دستی از credentials
            bot_token, chat_id = _get_bale_credentials()
            self.notifier = _FallbackBaleNotifier(bot_token, chat_id)

            if bot_token and chat_id:
                logger.info("[Bale] Notifier configured via fallback")
            else:
                logger.warning(
                    "[Bale] Notifier NOT configured — "
                    "alerts won't be sent")

        except Exception as e:
            logger.exception(f"[Bale] Failed to init notifier: {e}")
            self.notifier = _FallbackBaleNotifier()

    # =====================================================
    # کنترل‌های خارجی
    # =====================================================

    def set_auto_refresh(self, enabled: bool):
        self.auto_refresh_enabled = enabled
        logger.info(f"auto_refresh set to {enabled}")
        if enabled:
            self._wake_event.set()

    def set_interval(self, seconds: int):
        if seconds >= 5:
            self.check_interval = seconds
            logger.info(f"interval set to {seconds}s")
            self._wake_event.set()

    def trigger_manual_refresh(self):
        """درخواست دریافت دستی"""
        self.force_refresh_flag = True
        self._wake_event.set()
        logger.info("Manual refresh triggered")

    def stop(self):
        self.is_running = False
        self._wake_event.set()
        # انتظار برای پایان کارگرها
        for w in self._workers:
            try:
                w.wait(2000)
            except Exception:
                pass
        logger.info("Monitor thread stop requested")

    # =====================================================
    # حلقه اصلی
    # =====================================================

    def run(self):
        logger.info("Monitor thread started")

        while self.is_running:
            self._loop_count += 1
            logger.debug(f"Loop iteration #{self._loop_count}")

            # ✅ پاکسازی دوره‌ای workers (هر ۱۰ حلقه)
            if self._loop_count % 10 == 0:
                self._cleanup_finished_workers()

            should_fetch = self.auto_refresh_enabled or self.force_refresh_flag

            if should_fetch:
                self.force_refresh_flag = False
                try:
                    self._fetch_and_emit()
                except Exception as e:
                    logger.exception(f"Fetch failed: {e}")
                    self._emit_status(
                        ok=False,
                        message=f"خطای غیرمنتظره: {type(e).__name__}",
                    )
            else:
                logger.debug("Skipped fetch (auto off)")

            self._wake_event.wait(timeout=self.check_interval)
            self._wake_event.clear()

        logger.info("Monitor thread exited")

    def _cleanup_finished_workers(self):
        """پاکسازی workerهای تمام‌شده"""
        before = len(self._workers)
        self._workers = [
            w for w in self._workers
            if w.isRunning() or not w.isFinished()
        ]
        after = len(self._workers)
        if before != after:
            logger.debug(
                f"Cleaned up {before - after} finished workers")

    # =====================================================
    # emit وضعیت اتصال
    # =====================================================

    def _emit_status(self, ok: bool, message: str):
        self.connection_status.emit({
            "ok": ok,
            "message": message,
            "timestamp": datetime.now(),
        })

    # =====================================================
    # دریافت و emit
    # =====================================================

    def _fetch_and_emit(self):
        # ✅ استفاده از get_market_snapshot از main
        snapshot_func = get_market_snapshot
        if snapshot_func is None:
            logger.warning("get_market_snapshot is None; skipping")
            self._emit_status(
                ok=False,
                message="ماژول دریافت داده در دسترس نیست")
            return

        # ─── ۱. استخراج نمادهای فعال ───
        positions = self.storage.load_positions()
        needed_symbols = set()
        open_positions = []
        expired_ids = []

        for pos in positions:
            if pos.status != PositionStatus.OPEN:
                continue

            if pos.expiry_date and is_expired_date(pos.expiry_date):
                expired_ids.append(pos.position_id)
                continue

            open_positions.append(pos)
            for leg in pos.legs:
                needed_symbols.add(leg.symbol)
                if not leg.is_option and pos.underlying_symbol:
                    needed_symbols.add(pos.underlying_symbol)

        # اطلاع به UI
        if expired_ids:
            self.expired_found.emit(expired_ids)

        # بررسی یادآورهای سررسید
        all_open = [p for p in positions
                    if p.status == PositionStatus.OPEN]
        self._check_expiry_reminders(all_open)

        if not needed_symbols:
            logger.info("No active symbols to fetch")
            self._emit_status(ok=True, message="بدون موقعیت فعال")
            return

        logger.info(f"Fetching {len(needed_symbols)} symbols")

        # ─── ۲. دریافت Snapshot ───
        try:
            snapshot = snapshot_func(
                use_cache=True, force_refresh=False)
        except Exception as e:
            logger.exception(f"get_market_snapshot raised: {e}")
            self._emit_status(
                ok=False,
                message=f"خطا در دریافت داده: {type(e).__name__}")
            return

        if snapshot is None:
            logger.warning("Snapshot returned None")
            self._emit_status(
                ok=False,
                message="Snapshot در دسترس نیست")
            return

        # ─── ۳. استخراج قیمت‌ها ───
        prices: Dict[str, float] = {}
        contract_sizes: Dict[str, int] = {}

        for sym in needed_symbols:
            try:
                contract = snapshot.get_options_by_symbol(sym)
            except Exception:
                contract = None

            if contract is not None:
                price = contract.close_price or contract.last_price
                if price > 0:
                    prices[sym] = float(price)
                if contract.contract_size and contract.contract_size > 0:
                    contract_sizes[sym] = int(contract.contract_size)
                continue

            try:
                underlying = snapshot.get_underlying_assets(sym)
            except Exception:
                underlying = None

            if underlying is not None:
                price = underlying.last_price
                if price > 0:
                    prices[sym] = float(price)

        logger.info(f"Extracted {len(prices)} prices, "
                    f"{len(contract_sizes)} contract_sizes")

        # ─── ۴. ارسال وضعیت ───
        if not prices:
            self._emit_status(ok=False, message="داده‌ای دریافت نشد")
        else:
            self._emit_status(
                ok=True, message=f"{len(prices)} نماد به‌روز شد")

        # ─── ۵. emit قیمت‌ها ───
        if prices:
            self.prices_updated.emit({
                "prices": prices,
                "contract_sizes": contract_sizes,
            })
            logger.info("prices_updated emitted")

        # ─── ۶. بررسی هشدارها ───
        self._check_and_emit_alerts(open_positions, prices)

    # =====================================================
    # بررسی هشدارها (✅ بدون Race Condition)
    # =====================================================

    def _check_and_emit_alerts(self, positions, prices: Dict[str, float]):
        """
        بررسی هشدارهای حد سود.

        ⚠️ نکته مهم:
            علامت‌گذاری alert_sent در این تابع انجام نمی‌شود.
            بلکه در _on_worker_finished بعد از تأیید موفقیت ارسال انجام می‌شود.
            این از Race Condition جلوگیری می‌کند.
        """
        triggered = []

        for pos in positions:
            if pos.alert_target_roi <= 0:
                continue

            # اعمال قیمت‌های جدید
            for leg in pos.legs:
                if leg.symbol in prices:
                    leg.current_price = prices[leg.symbol]

            live_pnl, live_roi = PositionPnLCalculator.calculate_live_pnl(pos)

            if live_roi >= pos.alert_target_roi and not pos.alert_sent:
                triggered.append({
                    "position_id": pos.position_id,
                    "live_pnl": live_pnl,
                    "live_roi": live_roi,
                    "target_roi_maturity": pos.target_roi_maturity,
                    "alert_target_roi": pos.alert_target_roi,
                    "underlying_symbol": pos.underlying_symbol,
                    "strategy_name": pos.strategy_name,
                })

        if triggered:
            logger.info(f"Emitting {len(triggered)} alerts")
            self.alerts_found.emit(triggered)

    # =====================================================
    # یادآورهای سررسید
    # =====================================================

    def _check_expiry_reminders(self, positions):
        """بررسی یادآورهای سررسید (۲ بار در روز، ≥ ۱ ساعت)"""
        if not positions:
            return

        allowed, reason = self._reminder_state.can_send()
        if not allowed:
            logger.debug(f"[Reminder] Skipped: {reason}")
            return

        today = jdatetime.date.today()
        tomorrow = today + jdatetime.timedelta(days=1)

        reminders = []
        for pos in positions:
            if not pos.expiry_date:
                continue
            expiry = _parse_jalali_date(pos.expiry_date)
            if expiry is None:
                continue

            if expiry == today:
                reminders.append({"position": pos, "kind": "physical"})
            elif expiry == tomorrow:
                reminders.append({"position": pos, "kind": "cash"})

        if not reminders:
            return

        message = self._build_expiry_message(reminders)
        if not message:
            return

        try:
            if self.notifier.is_configured:
                # ارسال async — از Worker استفاده می‌کنیم
                worker = BaleSendWorker(
                    self.notifier, message, "REMINDER")
                worker.send_finished.connect(self._on_worker_finished)
                self._workers.append(worker)
                worker.start()
                self._reminder_state.mark_sent()
                logger.info(
                    f"[Reminder] Sent for {len(reminders)} positions")
            else:
                logger.warning(
                    "[Reminder] Not configured — message not sent")
        except Exception as e:
            logger.exception(f"[Reminder] Send failed: {e}")

    def _build_expiry_message(self, reminders: List[Dict]) -> str:
        """ساخت پیام یادآور سررسید"""
        now = jdatetime.datetime.now()
        time_str = now.strftime("%Y/%m/%d, %H:%M:%S")

        lines = []
        lines.append("🔔 *یادآور سررسید موقعیت‌ها*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        physical_count = 0
        cash_count = 0

        for item in reminders:
            pos = item["position"]
            kind = item["kind"]

            if kind == "physical":
                header = "🏦 *تسویه فیزیکی*"
                physical_count += 1
            else:
                header = "📌 *آخرین فرصت معاملاتی (تسویه نقدی)*"
                cash_count += 1

            lines.append(header)
            lines.append(f"📊 *استراتژی:* {pos.strategy_name}")

            if pos.broker_name:
                lines.append(f"🏦 *کارگزاری:* {pos.broker_name}")

            lines.append(f"📅 *تاریخ سررسید:* {pos.expiry_date}")
            lines.append("")

            # لنگه‌ها
            lines.append("🔗 *لنگه‌ها:*")
            for i, leg in enumerate(pos.legs, 1):
                direction = "🟢 خرید" if leg.leg_type == LegType.BUY \
                    else "🔴 فروش"
                lines.append(
                    f"  {i}. {direction}: {leg.symbol} "
                    f"({leg.quantity} × {fmt_int(leg.entry_price)})")
            lines.append("")

            # سود/زیان لایو
            live_pnl, live_roi = \
                PositionPnLCalculator.calculate_live_pnl(pos)
            emoji = "🟢" if live_pnl > 0 else \
                ("🔴" if live_pnl < 0 else "⚪")

            lines.append(
                f"{emoji} *سود/زیان لایو:* {fmt_money(live_pnl)} "
                f"({fmt_pct(live_roi, digits=1)})")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("")

        # خلاصه
        summary = []
        if physical_count:
            summary.append(f"🏦 تسویه فیزیکی: {physical_count}")
        if cash_count:
            summary.append(f"📌 تسویه نقدی: {cash_count}")
        if summary:
            lines.append("📋 *خلاصه:* " + " | ".join(summary))
            lines.append("")

        lines.append(f"⏱️ *زمان ارسال:* {time_str}")
        return "\n".join(lines)

    # =====================================================
    # پیام هشدار حد سود
    # =====================================================

    def _build_alert_message(self, alert_info: dict) -> str:
        """ساخت پیام هشدار حد سود"""
        now = jdatetime.datetime.now()
        time_str = now.strftime("%Y/%m/%d, %H:%M:%S")

        lines = []
        lines.append("🎯 *هشدار حد سود استراتژی*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"📌 *شناسه:* {alert_info['position_id']}")
        lines.append(
            f"📈 *نماد پایه / استراتژی:* "
            f"{alert_info['underlying_symbol']} | "
            f"{alert_info['strategy_name']}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"💰 *سود فعلی:* {fmt_pct(alert_info['live_roi'], digits=1)}")
        lines.append(
            f"🎯 *حد هشدار:* {alert_info['alert_target_roi']}%")
        lines.append(
            f"📊 *سود مورد انتظار سررسید:* "
            f"{alert_info['target_roi_maturity']:.1f}%")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(
            f"💵 *مبلغ سود:* {fmt_money(alert_info['live_pnl'])}")
        lines.append("")
        lines.append("⏱️ *آماده برای بستن موقعیت*")
        lines.append(f"🕐 *زمان:* {time_str}")

        return "\n".join(lines)

    def send_bale_alert(self, alert_info: dict) -> bool:
        """
        ارسال پیام هشدار — Async.
        علامت‌گذاری alert_sent در _on_worker_finished انجام می‌شود.
        """
        if not self.notifier.is_configured:
            logger.warning("[Bale] Alert not sent — not configured")
            return False

        try:
            msg = self._build_alert_message(alert_info)
            position_id = alert_info.get("position_id", "")

            worker = BaleSendWorker(self.notifier, msg, position_id)
            worker.send_finished.connect(self._on_worker_finished)
            self._workers.append(worker)
            worker.start()
            return True
        except Exception as e:
            logger.exception(f"Bale alert failed: {e}")
            return False

    @Slot(bool, str)
    def _on_worker_finished(self, success: bool, position_id: str):
        """
        پاکسازی کارگر + به‌روزرسانی alert_sent روی دیسک فقط در صورت موفقیت.
        """
        # اگر position_id مربوط به alert است (نه reminder)
        if position_id and position_id != "REMINDER":
            if success:
                logger.info(
                    f"[Bale] Alert sent OK for {position_id}")
                self._mark_alert_sent_on_disk(position_id)
            else:
                logger.warning(
                    f"[Bale] Alert FAILED for {position_id} — "
                    f"alert_sent will remain False")

        # پاکسازی لیست
        self._workers = [
            w for w in self._workers
            if w.isRunning() or not w.isFinished()
        ]

    def _mark_alert_sent_on_disk(self, position_id: str):
        """ثبت موفقیت ارسال آلرت روی دیسک"""
        try:
            all_positions = self.storage.load_positions()
            changed = False
            for p in all_positions:
                if p.position_id == position_id and not p.alert_sent:
                    p.alert_sent = True
                    changed = True
                    break

            if changed:
                self.storage.save_positions(all_positions)
                logger.debug(f"alert_sent marked for {position_id}")
        except Exception as e:
            logger.exception(f"Failed to mark alert_sent: {e}")

    # =====================================================
    # گزارش موقعیت (ارسال دستی)
    # =====================================================

    def send_position_report(self, position) -> bool:
        """ارسال گزارش موقعیت به بله (Async)"""
        if not self.notifier.is_configured:
            logger.warning("[Bale] Not configured — cannot send report")
            return False

        try:
            msg = self._build_position_report(position)
            worker = BaleSendWorker(
                self.notifier, msg, position.position_id)
            worker.send_finished.connect(self._on_worker_finished)
            self._workers.append(worker)
            worker.start()
            return True
        except Exception as e:
            logger.exception(f"[Bale] Position report failed: {e}")
            return False

    def _build_position_report(self, pos) -> str:
        """ساخت پیام گزارش موقعیت برای ارسال دستی"""
        now = jdatetime.datetime.now()
        time_str = now.strftime("%Y/%m/%d, %H:%M:%S")

        net_cost = PositionPnLCalculator.calculate_net_entry_cost(pos)
        live_pnl, live_roi = PositionPnLCalculator.calculate_live_pnl(pos)
        realized_pnl, realized_roi = \
            PositionPnLCalculator.calculate_realized_pnl(pos)

        lines = []
        lines.append("📋 *گزارش موقعیت استراتژی*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"🏷 *شناسه:* {pos.position_id}")
        lines.append(f"📊 *استراتژی:* {pos.strategy_name}")

        if pos.broker_name:
            lines.append(f"🏦 *کارگزاری:* {pos.broker_name}")

        lines.append(f"📌 *نماد پایه:* {pos.underlying_symbol}")
        lines.append(f"📅 *تاریخ اجرا:* {pos.execution_date}")
        lines.append(f"📅 *تاریخ سررسید:* {pos.expiry_date}")

        days = pos.days_to_expiry()
        if days is not None:
            lines.append(f"⏳ *روز مانده:* {days}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔗 *لنگه‌ها:*")

        for i, leg in enumerate(pos.legs, 1):
            direction = "🟢 خرید" if leg.leg_type == LegType.BUY \
                else "🔴 فروش"
            kind = ""
            if leg.is_call:
                kind = " (کال)"
            elif leg.is_put:
                kind = " (پوت)"
            elif leg.is_stock:
                kind = " (سهام)"

            lines.append(f"  {i}. {direction}: {leg.symbol}{kind}")
            lines.append(
                f"      تعداد: {leg.quantity} × "
                f"قیمت ورود: {fmt_int(leg.entry_price)}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 *هزینه خالص ورود:* {fmt_money(net_cost)}")

        if pos.status == PositionStatus.OPEN:
            emoji = "🟢" if live_pnl > 0 else \
                ("🔴" if live_pnl < 0 else "⚪")
            lines.append(
                f"{emoji} *سود/زیان لایو:* {fmt_money(live_pnl)} "
                f"({fmt_pct(live_roi, digits=1)})")
        else:
            emoji = "🟢" if realized_pnl > 0 else \
                ("🔴" if realized_pnl < 0 else "⚪")
            lines.append(
                f"{emoji} *سود/زیان محقق‌شده:* {fmt_money(realized_pnl)} "
                f"({fmt_pct(realized_roi, digits=1)})")

        lines.append(f"📈 *وضعیت:* {pos.status.label_fa}")
        lines.append("")
        lines.append(f"⏱️ *زمان ارسال:* {time_str}")

        return "\n".join(lines)