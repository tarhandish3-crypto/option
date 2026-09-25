# position_saver/live_monitor.py
# -*- coding: utf-8 -*-

import logging
import json
import re
import threading
from datetime import datetime
from typing import Dict, List, Tuple

import jdatetime
from PySide6.QtCore import QThread, Signal

from position_saver.storage import PositionStorage
from position_saver.models import PositionStatus, LegType
from position_saver.reminder_state import ReminderState
from position_saver.pnl_calculator import PositionPnLCalculator

logger = logging.getLogger("PositionSaver.LiveMonitor")


# =====================================================
# import مقاوم get_market_snapshot
# =====================================================

from data.manager import get_market_snapshot



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
    """
    استخراج bot_token و chat_id از دیکشنری bale.
    اگر enabled صریحاً False باشد، رشته خالی برمی‌گرداند.
    """
    if not isinstance(bale_dict, dict):
        return "", ""

    enabled = bale_dict.get("enabled", True)
    if enabled is False:
        return "", ""

    token = str(bale_dict.get("bot_token", "")).strip()
    chat = str(bale_dict.get("chat_id", "")).strip()

    # گزینه‌های جایگزین (اگر نام‌ها فرق داشتند)
    if not token:
        token = str(bale_dict.get("bale_bot_token", "")).strip()
    if not chat:
        chat = str(bale_dict.get("bale_chat_id", "")).strip()

    return token, chat


def _is_bale_enabled() -> bool:
    """
    بررسی فعال بودن بله در تنظیمات.
    فقط به bale.enabled نگاه می‌کند (نه bale_enabled قدیمی).
    """
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

        # ۲. اگر پروفایل فعال پیدا نشد، همه پروفایل‌ها را چک کن
        for profile_name, profile_data in profiles.items():
            bale = profile_data.get("bale", {})
            token, chat = _extract_bale(bale)
            if token and chat:
                logger.info(
                    f"[Bale] Credentials loaded from profile "
                    f"'{profile_name}'")
                return token, chat

        # ۳. جستجوی مستقیم در سطح بالا
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
# بارگذاری BaleNotifier با آداپتور send_message
# =====================================================

def _load_bale_notifier_class():
    """
    بارگذاری BaleNotifier از برنامه اصلی + افزودن متد send_message.

    مشکل: BaleNotifier در برنامه اصلی متد send_message ندارد
           (فقط send_scan_results دارد).
    راه‌حل: یک زیرکلاس با متد send_message می‌سازیم که از
            تابع آزاد send_message_to_bale استفاده می‌کند.
    """
    try:
        from alerts.bale_notifier import (
            BaleNotifier as _BaseBaleNotifier,
            send_message_to_bale,
        )
    except ImportError:
        logger.warning("[Bale] bale_notifier module not found")
        return None

    class BaleNotifierAdapter(_BaseBaleNotifier):
        """آداپتور BaleNotifier با متد send_message"""

        def send_message(self, msg: str, parse_mode: str = "Markdown") -> bool:
            """ارسال پیام متنی با send_message_to_bale"""
            if not self.is_configured:
                logger.warning(
                    "[Bale] Not configured (bot_token or chat_id missing)")
                return False

            with self._lock:
                token = self.bot_token
                c_id = self.chat_id

            try:
                result = send_message_to_bale(
                    bot_token=token,
                    chat_id=c_id,
                    message_text=msg,
                    parse_mode=parse_mode,
                )
                if result is not None:
                    logger.info("[Bale] Message sent successfully")
                    return True
                logger.warning("[Bale] send_message_to_bale returned None")
                return False
            except Exception as e:
                logger.exception(f"[Bale] send_message failed: {e}")
                return False

    return BaleNotifierAdapter


_BaleNotifierClass = _load_bale_notifier_class()


if _BaleNotifierClass is None:
    # Fallback اگر ماژول اصلی نیست
    class BaleNotifier:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def is_configured(self):
            return False

        def send_message(self, msg, parse_mode="Markdown"):
            print(f"[BaleNotifier-Mock] {msg}")
            return False
else:
    BaleNotifier = _BaleNotifierClass


# =====================================================
# ترد پس‌زمینه
# =====================================================

class LivePositionMonitorThread(QThread):
    """
    ترد پس‌زمینه برای دریافت قیمت‌های لایو از برنامه اصلی.

    ⚠️ این ترد فقط قیمت‌ها، هشدارها و وضعیت اتصال را emit می‌کند و
    هرگز روی لیست موقعیت‌های UI تغییر نمی‌دهد.

    موقعیت‌های منقضی (expiry_date < today) از دریافت قیمت حذف می‌شوند.
    """

    prices_updated = Signal(dict)
    alerts_found = Signal(list)
    expired_found = Signal(list)
    connection_status = Signal(dict)

    def __init__(self, storage: PositionStorage, check_interval: int = 60):
        super().__init__()
        self.storage = storage
        self.check_interval = check_interval
        self.is_running = True
        self.auto_refresh_enabled = True
        self.force_refresh_flag = False
        self._wake_event = threading.Event()

        # ✅ راه‌اندازی notifier با توکن واقعی
        self._init_bale_notifier()

        # ✅ state یادآور سررسید (ماندگار در JSON)
        self._reminder_state = ReminderState()

        logger.info(f"Monitor thread initialized (interval={check_interval}s)")

    def _init_bale_notifier(self):
        """راه‌اندازی BaleNotifier با بررسی enabled و خواندن credentials"""
        try:
            if not _is_bale_enabled():
                logger.info("[Bale] Disabled in settings — skipping init")
                self.notifier = BaleNotifier()
                return

            bot_token, chat_id = _get_bale_credentials()
            self.notifier = BaleNotifier(
                bot_token=bot_token, chat_id=chat_id)

            if bot_token and chat_id:
                logger.info("[Bale] Notifier configured successfully")
            else:
                logger.warning(
                    "[Bale] Notifier NOT configured — "
                    "alerts won't be sent to Bale")
        except Exception as e:
            logger.exception(f"[Bale] Failed to init notifier: {e}")
            self.notifier = BaleNotifier()

    # =====================================================
    # کنترل‌های خارجی
    # =====================================================

    def set_auto_refresh(self, enabled: bool):
        self.auto_refresh_enabled = enabled
        logger.info(f"auto_refresh set to {enabled}")
        if enabled:
            self._wake_event.set()

    def set_interval(self, seconds: int):
        if seconds > 0:
            self.check_interval = seconds
            logger.info(f"interval set to {seconds}s")
            self._wake_event.set()

    def trigger_manual_refresh(self):
        """درخواست دریافت دستی — حتی اگر auto_refresh خاموش باشد"""
        self.force_refresh_flag = True
        self._wake_event.set()
        logger.info("Manual refresh triggered")

    def stop(self):
        self.is_running = False
        self._wake_event.set()
        logger.info("Monitor thread stop requested")

    # =====================================================
    # حلقه اصلی
    # =====================================================

    def run(self):
        logger.info("Monitor thread started (run entered)")
        loop_count = 0

        while self.is_running:
            loop_count += 1
            logger.debug(f"Loop iteration #{loop_count}")

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
                logger.debug("Skipped fetch (auto off, no manual request)")

            self._wake_event.wait(timeout=self.check_interval)
            self._wake_event.clear()

        logger.info("Monitor thread exited")

    # =====================================================
    # emit وضعیت اتصال
    # =====================================================

    def _emit_status(self, ok: bool, message: str):
        """ارسال وضعیت اتصال به UI"""
        self.connection_status.emit({
            "ok": ok,
            "message": message,
            "timestamp": datetime.now(),
        })

    # =====================================================
    # دریافت و emit
    # =====================================================

    def _fetch_and_emit(self):
        if get_market_snapshot is None:
            logger.warning("get_market_snapshot is None; skipping")
            self._emit_status(
                ok=False,
                message="ماژول دریافت داده در دسترس نیست",)
            return

        # ─── ۱. استخراج نمادهای فعال (فیلتر انقضا) ───
        positions = self.storage.load_positions()
        needed_symbols = set()
        open_positions = []
        expired_ids = []

        for pos in positions:
            if pos.status != PositionStatus.OPEN:
                continue

            # فیلتر موقعیت‌های منقضی
            if pos.expiry_date and is_expired_date(pos.expiry_date):
                expired_ids.append(pos.position_id)
                continue

            open_positions.append(pos)
            for leg in pos.legs:
                needed_symbols.add(leg.symbol)
                if not leg.is_option and pos.underlying_symbol:
                    needed_symbols.add(pos.underlying_symbol)

        # اطلاع به UI درباره موقعیت‌های منقضی
        if expired_ids:
            self.expired_found.emit(expired_ids)

        # ✅ بررسی یادآورهای سررسید (حتی اگر نماد فعالی نیست)
        all_open_positions = [
            p for p in positions if p.status == PositionStatus.OPEN]
        self._check_expiry_reminders(all_open_positions)

        # اگر موقعیت فعالی وجود ندارد، خطا نیست
        if not needed_symbols:
            logger.info("No active symbols to fetch")
            self._emit_status(
                ok=True,
                message="بدون موقعیت فعال",)
            return

        logger.info(f"Fetching {len(needed_symbols)} symbols")

        # ─── ۲. دریافت Snapshot ───
        try:
            snapshot = get_market_snapshot(
                use_cache=False, force_refresh=False)
        except Exception as e:
            logger.exception(f"get_market_snapshot raised: {e}")
            self._emit_status(
                ok=False,
                message=f"خطا در دریافت داده: {type(e).__name__}",)
            return

        # ─── ۳. استخراج قیمت‌ها و contract_sizes ───
        prices: Dict[str, float] = {}
        contract_sizes: Dict[str, int] = {}

        for sym in needed_symbols:
            contract = snapshot.get_options_by_symbol(sym)
            if contract is not None:
                price = contract.close_price or contract.last_price
                if price > 0:
                    prices[sym] = float(price)
                if contract.contract_size and contract.contract_size > 0:
                    contract_sizes[sym] = int(contract.contract_size)
                continue

            underlying = snapshot.get_underlying_assets(sym)
            if underlying is not None:
                price = underlying.last_price
                if price > 0:
                    prices[sym] = float(price)

        logger.info(f"Extracted {len(prices)} prices, "
                    f"{len(contract_sizes)} contract_sizes")

        # ─── ۴. ارسال وضعیت اتصال ───
        if not prices:
            self._emit_status(
                ok=False,
                message="داده‌ای از بازار دریافت نشد",
            )
        else:
            self._emit_status(
                ok=True,
                message=f"{len(prices)} نماد به‌روز شد",
            )

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
    # بررسی هشدارها
    # =====================================================

    def _check_and_emit_alerts(self, positions, prices: Dict[str, float]):

        triggered = []
        for pos in positions:
            if pos.alert_target_roi <= 0:
                continue

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
            elif live_roi < pos.alert_target_roi * 0.9 and pos.alert_sent:
                pos.alert_sent = False

        if triggered:
            logger.info(f"Emitting {len(triggered)} alerts")
            self.alerts_found.emit(triggered)

    # =====================================================
    # یادآورهای سررسید
    # =====================================================

    def _check_expiry_reminders(self, positions):
        """
        بررسی موقعیت‌هایی که:
            - امروز = روز سررسید (تسویه فیزیکی)
            - فردا = روز سررسید (تسویه نقدی — آخرین فرصت معاملاتی)
        با محدودیت ۲ بار در روز و ≥ ۱ ساعت فاصله
        """
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
                ok = self.notifier.send_message(message)
                if ok:
                    self._reminder_state.mark_sent()
                    logger.info(
                        f"[Reminder] Sent for {len(reminders)} positions")
                else:
                    logger.warning("[Reminder] Failed to send")
            else:
                logger.warning(
                    "[Reminder] Not configured — message not sent")
        except Exception as e:
            logger.exception(f"[Reminder] Send failed: {e}")

    def _build_expiry_message(self, reminders: List[Dict]) -> str:
        """ساخت پیام یادآور سررسید (نام استراتژی + تاریخ + لگ‌ها + سود/زیان)"""
        from position_saver.pnl_calculator import PositionPnLCalculator

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
                    f"({leg.quantity} × {int(leg.entry_price):,})")
            lines.append("")

            # سود/زیان لایو
            live_pnl, live_roi = \
                PositionPnLCalculator.calculate_live_pnl(pos)
            pnl_sign = "+" if live_pnl >= 0 else ""
            emoji = "🟢" if live_pnl > 0 else \
                ("🔴" if live_pnl < 0 else "⚪")

            lines.append(
                f"{emoji} *سود/زیان لایو:* {pnl_sign}{int(live_pnl):,} تومان "
                f"({pnl_sign}{live_roi:.1f}%)")
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
    # پیام هشدار حد سود (زیبا)
    # =====================================================

    def _build_alert_message(self, alert_info: dict) -> str:
        """ساخت پیام هشدار حد سود زیبا"""
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
        lines.append(f"💰 *سود فعلی:* +{alert_info['live_roi']:.1f}%")
        lines.append(
            f"🎯 *حد هشدار:* {alert_info['alert_target_roi']}%")
        lines.append(
            f"📊 *سود مورد انتظار سررسید:* "
            f"{alert_info['target_roi_maturity']:.1f}%")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(
            f"💵 *مبلغ سود:* {int(alert_info['live_pnl']):,} تومان")
        lines.append("")
        lines.append("⏱️ *آماده برای بستن موقعیت*")
        lines.append(f"🕐 *زمان:* {time_str}")

        return "\n".join(lines)

    def send_bale_alert(self, alert_info: dict) -> bool:
        """ارسال پیام هشدار حد سود به بله"""
        if not self.notifier.is_configured:
            logger.warning(
                "[Bale] Alert not sent — notifier not configured.")
            return False

        try:
            msg = self._build_alert_message(alert_info)
            return self.notifier.send_message(msg)
        except Exception as e:
            logger.exception(f"Bale alert failed: {e}")
            return False

    # =====================================================
    # گزارش موقعیت (ارسال دستی)
    # =====================================================

    def send_position_report(self, position) -> bool:
        """
        ارسال گزارش یک موقعیت به بله (از UI صدا زده می‌شود).
        شامل نام استراتژی، لگ‌ها، سود/زیان و تاریخ ارسال.
        """
        if not self.notifier.is_configured:
            logger.warning("[Bale] Not configured — cannot send report")
            return False
        try:
            msg = self._build_position_report(position)
            return self.notifier.send_message(msg)
        except Exception as e:
            logger.exception(f"[Bale] Position report failed: {e}")
            return False

    def _build_position_report(self, pos) -> str:
        """ساخت پیام گزارش موقعیت برای ارسال دستی"""
        from position_saver.pnl_calculator import PositionPnLCalculator

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
                f"قیمت ورود: {int(leg.entry_price):,}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 *هزینه خالص ورود:* {int(net_cost):,} تومان")

        if pos.status == PositionStatus.OPEN:
            pnl_sign = "+" if live_pnl >= 0 else ""
            emoji = "🟢" if live_pnl > 0 else \
                ("🔴" if live_pnl < 0 else "⚪")
            lines.append(
                f"{emoji} *سود/زیان لایو:* "
                f"{pnl_sign}{int(live_pnl):,} تومان "
                f"({pnl_sign}{live_roi:.1f}%)")
        else:
            pnl_sign = "+" if realized_pnl >= 0 else ""
            emoji = "🟢" if realized_pnl > 0 else \
                ("🔴" if realized_pnl < 0 else "⚪")
            lines.append(
                f"{emoji} *سود/زیان محقق‌شده:* "
                f"{pnl_sign}{int(realized_pnl):,} تومان "
                f"({pnl_sign}{realized_roi:.1f}%)")

        lines.append(f"📈 *وضعیت:* {pos.status.label_fa}")
        lines.append("")
        lines.append(f"⏱️ *زمان ارسال:* {time_str}")

        return "\n".join(lines)
