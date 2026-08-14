# alerts/bale_notifier.py
# -*- coding: utf-8 -*-

"""
ماژول ارسال اعلان به پیام‌رسان بله (Bale Messenger)
ارسال نتایج برتر اسکن به یک ربات یا کانال بله.

تنظیمات (BOT_TOKEN و CHAT_ID) از user_settings.json خوانده می‌شوند.
"""

import json
import logging
import threading
from datetime import datetime
from typing import List, Optional, Any

import requests

logger = logging.getLogger("OptionScanner.Alerts.Bale")

# آدرس پایه API بله
_BALE_API_BASE = "https://tapi.bale.ai"


def send_message_to_bale(bot_token: str, chat_id: str, message_text: str) -> Optional[dict]:
    """
    ارسال پیام متنی به ربات بله.

    Args:
        bot_token: توکن ربات (مثال: 123456789:ABCdefGHIjkl...)
        chat_id:   آیدی کانال، گروه یا کاربر (مثال: @mychannel یا عدد)
        message_text: متن پیام

    Returns:
        dict پاسخ API در صورت موفقیت، None در صورت خطا
    """
    url = f"{_BALE_API_BASE}/{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message_text}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            logger.info("✅ پیام بله با موفقیت ارسال شد")
            return response.json()
        else:
            logger.warning(f"⚠️ خطا در ارسال پیام بله: HTTP {response.status_code} — {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        logger.warning("⏱️ timeout در ارسال پیام بله")
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ارتباط با سرور بله: {e}")
        return None


class BaleNotifier:
    """
    مدیر ارسال اعلان‌های اسکنر به بله.
    ارسال در thread جداگانه انجام می‌شود تا UI را block نکند.
    """

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def is_configured(self) -> bool:
        """آیا توکن و chat_id تنظیم شده‌اند؟"""
        return bool(self.bot_token.strip()) and bool(self.chat_id.strip())

    def update_config(self, bot_token: str, chat_id: str) -> None:
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
            logger.debug("BaleNotifier: توکن یا chat_id تنظیم نشده — ارسال رد شد")
            return

        if not opportunities:
            logger.debug("BaleNotifier: لیست نتایج خالی است")
            return

        message = self._build_message(opportunities[:top_n])
        # ارسال در thread جداگانه تا UI بلاک نشود
        t = threading.Thread(
            target=self._send_async,
            args=(message,),
            daemon=True,
            name="BaleNotifierThread"
        )
        t.start()

    def _send_async(self, message: str) -> None:
        send_message_to_bale(self.bot_token, self.chat_id, message)

    def _build_message(self, opportunities: List[Any]) -> str:
        """
        ساخت متن پیام از استراتژی‌های برتر.
        """
        now = datetime.now().strftime("%Y/%m/%d  %H:%M")
        lines = [
            "📊 اسکنر اختیار معامله",
            f"🕐 {now}",
            "─" * 30,
        ]

        for i, opp in enumerate(opportunities, 1):
            strategy_name = getattr(opp, 'strategy_name', 'N/A')
            underlying  = getattr(opp, 'underlying_ticker', 'N/A')
            dte         = getattr(opp, 'days_to_maturity', 0)
            score       = getattr(opp, 'final_score', 0.0)
            max_profit  = getattr(opp, 'max_profit', 0.0)

            # ساخت خلاصه Positions از legs
            legs = getattr(opp, 'legs', [])
            positions_parts = []
            for leg in legs:
                contract = getattr(leg, 'contract', None)
                ticker = contract.ticker if contract else 'N/A'
                side   = leg.side.value if hasattr(leg.side, 'value') else str(leg.side)
                ratio  = leg.ratio
                positions_parts.append(f"{ticker} ({ratio}x{side})")
            positions_text = " | ".join(positions_parts) if positions_parts else "N/A"

            lines += [
                f"#{i}  {strategy_name}  [{underlying}]",
                f"📌 {positions_text}",
                f"📅 DTE: {dte}  |  🏆 Score: {score:.1f}  |  💰 MaxProfit: {max_profit:,.0f}",
                "─" * 30,
            ]

        return "\n".join(lines)
