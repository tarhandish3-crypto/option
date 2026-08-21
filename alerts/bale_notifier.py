# alerts/bale_notifier.py
# -*- coding: utf-8 -*-

"""
ماژول ارسال اعلان به پیام‌رسان بله (Bale Messenger)
ارسال نتایج برتر اسکن به یک ربات یا کانال بله.
"""

import json
import logging
import threading
from datetime import datetime
from typing import List, Optional, Any

import requests

logger = logging.getLogger("OptionScanner.Alerts.Bale")


def send_message_to_bale(
    bot_token: str,
    chat_id: str,
    message_text: str,
    parse_mode: Optional[str] = "Markdown",
    timeout: int = 10
) -> Optional[dict]:
    """
    ارسال پیام متنی به ربات بله.

    Args:
        bot_token: توکن ربات (مثال: 123456789:ABCdefGHIjkl...)
        chat_id:   آیدی کانال، گروه یا کاربر (مثال: @mychannel یا عدد)
        message_text: متن پیام
        parse_mode: فرمت متن (Markdown یا None)
        timeout: مدت زمان انتظار درخواست به ثانیه

    Returns:
        dict پاسخ API در صورت موفقیت، None در صورت خطا
    """
    url = f'https://tapi.bale.ai/bot{bot_token}/sendMessage'
    payload = {
        "chat_id": chat_id,
        "text": message_text
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=timeout
        )
        if response.status_code == 200:
            logger.info("Bale message sent successfully.")
            return response.json()
        else:
            logger.warning(
                f"Failed to send Bale message: HTTP {response.status_code} - {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        logger.warning("Timeout occurred while sending Bale message.")
        return None
    except Exception as e:
        logger.error(f"Error communicating with Bale server: {e}")
        return None


class BaleNotifier:
    """
    مدیر ارسال اعلان‌های اسکنر به بله.
    ارسال در thread پس‌زمینه انجام می‌شود تا UI را block نکند.
    """

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        """آیا توکن و chat_id تنظیم شده‌اند؟"""
        with self._lock:
            return bool(self.bot_token) and bool(self.chat_id)

    def update_config(self, bot_token: str, chat_id: str) -> None:
        """به‌روزرسانی ایمن تنظیمات ربات حین اجرا"""
        with self._lock:
            self.bot_token = bot_token.strip()
            self.chat_id = chat_id.strip()

    def send_scan_results(self, opportunities: List[Any], top_n: int = 2) -> None:
        """
        ارسال خلاصه n استراتژی برتر به بله.
        ارسال در thread پس‌زمینه انجام می‌شود.

        Args:
            opportunities: لیست Opportunity فیلترشده و رتبه‌بندی‌شده
            top_n:         تعداد سطرهای اول برای ارسال (پیش‌فرض: ۲)
        """
        if not self.is_configured:
            logger.debug(
                "BaleNotifier: Bot token or chat_id is missing. Skipping execution.")
            return

        if not opportunities:
            logger.debug(
                "BaleNotifier: Opportunity list is empty. Skipping execution.")
            return

        # گرفتن اسنپ‌شات ایمن از کانفیگ فعلی
        with self._lock:
            token = self.bot_token
            c_id = self.chat_id

        message = self._build_message(opportunities[:top_n])

        # ارسال در Thread پس‌زمینه
        t = threading.Thread(
            target=send_message_to_bale,
            args=(token, c_id, message, "Markdown"),
            daemon=True,
            name="BaleNotifierThread"
        )
        t.start()

    def _build_message(self, opportunities: List[Any]) -> str:
        """
        ساخت متن پیام با فرمت Markdown
        """
        try:
            import jdatetime
            jnow = jdatetime.datetime.now()
            date_str = jnow.strftime("%Y/%m/%d")
            time_str = jnow.strftime("%H:%M")
        except ImportError:
            now = datetime.now()
            date_str = now.strftime("%Y/%m/%d")
            time_str = now.strftime("%H:%M")

        lines = [
            "🤖 *اسکن جدید بازار اختیار معامله*",
            f"⏱ *ساعت:* `{time_str}`  📅 *تاریخ:* `{date_str}`",
            "------------------------------------"
        ]

        for opp in opportunities:
            strategy_name = getattr(opp, 'strategy_name', 'N/A')
            # جایگزینی کاراکتر خط زیرین برای جلوگیری از خطای Markdown
            strategy_name_fmt = str(strategy_name).replace('_', ' ').title()

            score = getattr(opp, 'final_score', 0.0)
            legs = getattr(opp, 'legs', [])

            lines.append(f"🎯 *پیشنهاد:* `{strategy_name_fmt}`")

            for leg in legs:
                contract = getattr(leg, 'contract', None)
                if contract is None:
                    continue

                side_val = leg.side.value if hasattr(
                    leg.side, 'value') else str(leg.side)
                direction = "🟢 خرید" if side_val.upper() in ('BUY', 'LONG') else "🔴 فروش"

                ticker = getattr(contract, 'ticker', 'N/A')

                # پریمیوم: entry_price اولویت اول، بعد last_price
                premium = getattr(leg, 'entry_price', 0.0)
                if not premium or premium <= 0:
                    premium = getattr(contract, 'last_price', 0.0)

                lines.append(
                    f"  • {direction} *{ticker}* — پریمیوم: `{int(premium):,}`")

            lines.append(f"⭐ *امتیاز:* `{score:.1f}`")
            lines.append("------------------------------------")

        return "\n".join(lines)
