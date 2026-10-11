# position_saver/importer/excel_parser.py
# -*- coding: utf-8 -*-

"""
پارسر فایل اکسل تاریخچه معاملات کارگزاری.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

import jdatetime

from position_saver.models import LegType
from position_saver.storage import normalize_symbol, clean_int, clean_float
from position_saver.importer.schemas import (
    TradeRecord, ImportSettings, BrokerTemplate,
)
from position_saver.importer.broker_templates import get_template_for_broker


logger = logging.getLogger("PositionSaver.Importer.Parser")


SIDE_BUY_TOKENS = {"خرید", "buy", "Buy", "BUY", "long", "Long"}
SIDE_SELL_TOKENS = {"فروش", "sell", "Sell", "SELL", "short", "Short"}


def _parse_side(raw: str) -> Optional[LegType]:
    """تشخیص سمت سفارش"""
    if not raw:
        return None
    s = str(raw).strip()
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


def _parse_jalali_datetime(
    date_str: str, time_str: str
) -> Optional[datetime]:
    """تبدیل تاریخ و ساعت شمسی به datetime میلادی"""
    if not date_str:
        return None
    try:
        ds = str(date_str).strip()
        ts = str(time_str).strip() if time_str else "00:00:00"

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


class ExcelParser:
    """
    پارسر فایل اکسل کارگزاری.

    استفاده:
        parser = ExcelParser()
        trades = parser.parse("path/to/file.xlsx", broker="مفید",
                              settings=ImportSettings())
    """

    def __init__(self, template: Optional[BrokerTemplate] = None):
        self.template = template

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

        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            logger.exception(f"Read excel failed: {e}")
            return []

        df.columns = [str(c).strip() for c in df.columns]
        logger.info(
            f"Loaded {len(df)} rows from {file_path} "
            f"(broker: {broker or template.broker_name})")

        # فیلتر وضعیت
        status_col = template.status_col
        valid_statuses = settings.valid_statuses or \
            template.valid_statuses

        if status_col in df.columns:
            before = len(df)
            mask = df[status_col].astype(str).str.strip().isin(
                valid_statuses)
            df = df[mask]
            after = len(df)
            if before != after:
                logger.info(
                    f"Filtered {before - after} rows by status "
                    f"(kept {after})")
        else:
            logger.warning(
                f"Status column '{status_col}' not found — "
                f"all rows kept")

        trades: List[TradeRecord] = []
        for idx, row in df.iterrows():
            try:
                trade = self._row_to_trade(row, idx, template, broker)
                if trade is not None:
                    trades.append(trade)
            except Exception as e:
                logger.debug(f"Row {idx} skipped: {e}")
                continue

        trades.sort(key=lambda t: (
            t.timestamp if t.timestamp else datetime.min))

        logger.info(f"Parsed {len(trades)} valid trades")
        return trades

    def _row_to_trade(
        self,
        row,
        idx: int,
        template: BrokerTemplate,
        broker: str,
    ) -> Optional[TradeRecord]:
        date_val = row.get(template.date_col, "")
        time_val = row.get(template.time_col, "")
        ts = _parse_jalali_datetime(str(date_val), str(time_val))

        side_raw = row.get(template.side_col, "")
        side = _parse_side(side_raw)
        if side is None:
            logger.debug(
                f"Row {idx}: unknown side '{side_raw}' — skipped")
            return None

        symbol_raw = row.get(template.symbol_col, "")
        symbol = normalize_symbol(symbol_raw)
        if not symbol:
            logger.debug(f"Row {idx}: empty symbol — skipped")
            return None

        qty_raw = row.get(template.qty_col, 0)
        qty = clean_int(qty_raw, 0)
        if qty <= 0:
            logger.debug(f"Row {idx}: zero quantity — skipped")
            return None

        price_raw = row.get(template.price_col, 0)
        price = clean_float(price_raw, 0.0)
        if price <= 0:
            logger.debug(f"Row {idx}: zero price — skipped")
            return None

        status_raw = str(row.get(template.status_col, "")).strip()

        return TradeRecord(
            trade_id=f"trade_{idx:04d}",
            timestamp=ts,
            raw_date=str(date_val).strip(),
            raw_time=str(time_val).strip(),
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            raw_status=status_raw,
            broker=broker,
        )


__all__ = ["ExcelParser"]