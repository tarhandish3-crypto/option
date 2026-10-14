# position_saver/importer/excel_parser.py
# -*- coding: utf-8 -*-

"""
پارسر فایل اکسل تاریخچه معاملات کارگزاری.

نکات:
    - تاریخ و ساعت شمسی به datetime میلادی تبدیل می‌شود
    - raw_date و raw_time به YYYY/MM/DD و HH:MM:SS نرمال می‌شوند
      (چون کلید تکراری بر همین دو فیلد استوار است)
    - ✅ هیچ فیلتر وضعیتی اعمال نمی‌شود — همه‌ی ردیف‌های اکسل
      به‌عنوان معاملات انجام‌شده در نظر گرفته می‌شوند
    - اگر «حجم انجام شده» صفر/خالی بود، از «حجم کل» fallback می‌کند
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

import jdatetime

from position_saver.models import LegType
from position_saver.storage import (
    normalize_symbol, clean_int, clean_float,
)
from position_saver.importer.schemas import (
    TradeRecord, ImportSettings, BrokerTemplate,
)
from position_saver.importer.broker_templates import get_template_for_broker


logger = logging.getLogger("PositionSaver.Importer.Parser")


# ═══════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════

SIDE_BUY_TOKENS = {"خرید", "buy", "Buy", "BUY", "long", "Long"}
SIDE_SELL_TOKENS = {"فروش", "sell", "Sell", "SELL", "short", "Short"}

# نام‌های جایگزین برای ستون حجم
QTY_FALLBACK_COLS = ("حجم کل", "تعداد", "حجم")


# ═══════════════════════════════════════════════════
# پارس سمت
# ═══════════════════════════════════════════════════

def _parse_side(raw) -> Optional[LegType]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s in SIDE_BUY_TOKENS:
        return LegType.BUY
    if s in SIDE_SELL_TOKENS:
        return LegType.SELL
    s_low = s.lower()
    if "خرید" in s or s_low == "buy":
        return LegType.BUY
    if "فروش" in s or s_low == "sell":
        return LegType.SELL
    return None


# ═══════════════════════════════════════════════════
# نرمال‌سازی تاریخ و زمان
# ═══════════════════════════════════════════════════

def _is_empty(val) -> bool:
    """آیا مقدار خالی یا NaN است؟"""
    if val is None:
        return True
    if isinstance(val, float) and val != val:  # NaN
        return True
    s = str(val).strip()
    return not s or s.lower() == "nan"


def _normalize_date(date_str) -> str:
    """نرمال‌سازی تاریخ شمسی به YYYY/MM/DD."""
    if _is_empty(date_str):
        return ""
    try:
        s = str(date_str).strip()
        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
        if not m:
            return s
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}/{mo:02d}/{d:02d}"
    except Exception:
        return str(date_str).strip()


def _normalize_time(time_str) -> str:
    """نرمال‌سازی زمان به HH:MM:SS."""
    if _is_empty(time_str):
        return ""
    try:
        s = str(time_str).strip()
        if '.' in s:
            s = s.split('.')[0]
        parts = s.split(':')
        if len(parts) < 2:
            return s
        h = int(parts[0])
        mi = int(parts[1])
        se = int(parts[2]) if len(parts) >= 3 else 0
        return f"{h:02d}:{mi:02d}:{se:02d}"
    except Exception:
        return str(time_str).strip()


def _parse_jalali_datetime(date_str, time_str) -> Optional[datetime]:
    """تبدیل تاریخ و ساعت شمسی به datetime میلادی."""
    if _is_empty(date_str):
        return None
    try:
        ds = str(date_str).strip()
        ts = str(time_str).strip() if not _is_empty(time_str) else "00:00:00"

        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', ds)
        if not m:
            return None
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))

        if '.' in ts:
            ts = ts.split('.')[0]
        parts = ts.split(':')
        h = int(parts[0]) if len(parts) >= 1 else 0
        mi = int(parts[1]) if len(parts) >= 2 else 0
        se = int(parts[2]) if len(parts) >= 3 else 0

        jdt = jdatetime.datetime(y, mo, d, h, mi, se)
        return jdt.togregorian()
    except Exception as e:
        logger.debug(f"Date parse failed: {date_str} {time_str} — {e}")
        return None


# ═══════════════════════════════════════════════════
# ExcelParser
# ═══════════════════════════════════════════════════

class ExcelParser:
    """
    پارسر فایل اکسل کارگزاری.

    استفاده:
        parser = ExcelParser()
        trades = parser.parse("path/to/file.xlsx", broker="مفید")
    """

    def __init__(self, template: Optional[BrokerTemplate] = None):
        self.template = template

    # ═══════════════════════════════════════════════
    # API اصلی
    # ═══════════════════════════════════════════════

    def parse(
        self,
        file_path: str,
        broker: str = "",
        settings: Optional[ImportSettings] = None,
    ) -> List[TradeRecord]:
        """خواندن فایل و بازگرداندن لیست TradeRecord"""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas is required for Excel import")
            return []

        if settings is None:
            settings = ImportSettings()

        template = self.template or get_template_for_broker(broker)

        # ─── خواندن فایل ───
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            logger.exception(f"Read excel failed: {e}")
            return []

        df.columns = [str(c).strip() for c in df.columns]
        logger.info(
            f"Loaded {len(df)} rows from {file_path} "
            f"(broker: {broker or template.broker_name})")

        # ✅ دیگر فیلتری روی وضعیت اعمال نمی‌شود.
        # دلیل: فایل خروجی کارگزاری فقط شامل معاملات انجام‌شده است.

        # ─── پارس ردیف‌ها ───
        trades: List[TradeRecord] = []
        skipped = 0
        for idx, row in df.iterrows():
            try:
                trade = self._row_to_trade(row, idx, template, broker)
                if trade is not None:
                    trades.append(trade)
                else:
                    skipped += 1
            except Exception as e:
                skipped += 1
                logger.debug(f"Row {idx} skipped: {e}")

        if skipped:
            logger.info(
                f"Skipped {skipped} rows (empty/invalid fields)")

        # ─── مرتب‌سازی ───
        trades.sort(key=lambda t: (
            t.timestamp if t.timestamp else datetime.min))

        logger.info(f"Parsed {len(trades)} valid trades")
        return trades

    # ═══════════════════════════════════════════════
    # داخلی
    # ═══════════════════════════════════════════════

    def _row_to_trade(
        self,
        row,
        idx: int,
        template: BrokerTemplate,
        broker: str,
    ) -> Optional[TradeRecord]:
        """تبدیل یک ردیف اکسل به TradeRecord"""

        # ─── تاریخ ───
        date_val = row.get(template.date_col, "")
        time_val = row.get(template.time_col, "")

        if _is_empty(date_val):
            logger.debug(f"Row {idx}: empty date — skipped")
            return None

        norm_date = _normalize_date(date_val)
        norm_time = _normalize_time(time_val)
        ts = _parse_jalali_datetime(date_val, time_val)

        if not norm_date:
            logger.debug(f"Row {idx}: invalid date — skipped")
            return None

        # ─── سمت ───
        side_raw = row.get(template.side_col, "")
        side = _parse_side(side_raw)
        if side is None:
            logger.debug(
                f"Row {idx}: unknown side '{side_raw}' — skipped")
            return None

        # ─── نماد ───
        symbol_raw = row.get(template.symbol_col, "")
        if _is_empty(symbol_raw):
            logger.debug(f"Row {idx}: empty symbol — skipped")
            return None

        symbol = normalize_symbol(symbol_raw)
        if not symbol:
            logger.debug(f"Row {idx}: empty symbol after normalize")
            return None

        # ─── تعداد ───
        qty = self._extract_quantity(row, template)
        if qty <= 0:
            logger.debug(f"Row {idx}: zero quantity — skipped")
            return None

        # ─── قیمت ───
        price_raw = row.get(template.price_col, 0)
        price = clean_float(price_raw, 0.0)
        if price <= 0:
            logger.debug(f"Row {idx}: zero price — skipped")
            return None

        # ─── وضعیت خام (فقط برای ذخیره) ───
        status_raw = ""
        if template.status_col in row.index:
            status_raw = str(row.get(template.status_col, "")).strip()

        # ─── ساخت TradeRecord ───
        return TradeRecord(
            trade_id=f"trade_{idx:04d}",
            timestamp=ts,
            raw_date=norm_date,
            raw_time=norm_time,
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            raw_status=status_raw,
            broker=broker,
        )

    # ─── استخراج تعداد با fallback ───
    @staticmethod
    def _extract_quantity(row, template: BrokerTemplate) -> int:
        """
        استخراج تعداد از ستون «حجم انجام شده».

        اگر خالی/صفر بود، از ستون‌های fallback (حجم کل، تعداد، حجم)
        استفاده می‌کند.
        """
        # اول ستون اصلی
        qty = clean_int(row.get(template.qty_col, 0), 0)
        if qty > 0:
            return qty

        # fallback
        for col in QTY_FALLBACK_COLS:
            if col in row.index:
                qty = clean_int(row.get(col, 0), 0)
                if qty > 0:
                    return qty

        return 0


__all__ = [
    "ExcelParser",
    "_normalize_date",
    "_normalize_time",
    "_parse_jalali_datetime",
    "_parse_side",
]