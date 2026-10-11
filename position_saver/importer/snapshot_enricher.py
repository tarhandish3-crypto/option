# position_saver/importer/snapshot_enricher.py
# -*- coding: utf-8 -*-

"""
پر کردن فیلدهای ناقص از Snapshot بازار.
"""

import logging
import re
from typing import List, Optional

from core.enums import OptionType
from position_saver.storage import normalize_symbol
from position_saver.importer.schemas import TradeRecord


logger = logging.getLogger("PositionSaver.Importer.Enricher")


# =====================================================
# تشخیص پیشوند نماد
# =====================================================

def infer_option_kind_from_symbol(symbol: str) -> Optional[OptionType]:
    """حدس نوع اختیار از پیشوند نماد"""
    if not symbol:
        return None
    s = str(symbol).strip()
    if s.startswith("ض"):
        return OptionType.CALL
    if s.startswith("ط"):
        return OptionType.PUT
    return OptionType.STOCK


def infer_underlying_from_symbol(symbol: str) -> str:
    """حدس نماد پایه از نماد اختیار"""
    if not symbol:
        return ""
    s = str(symbol).strip()
    if s.startswith(("ض", "ط")):
        s = s[1:]
    m = re.match(r'([^\d]+)', s)
    if m:
        return m.group(1).strip()
    return s[:4] if len(s) >= 4 else s


# =====================================================
# SnapshotEnricher
# =====================================================

class SnapshotEnricher:
    """
    پر کردن فیلدهای ناقص از Snapshot.

    الگوریتم:
        برای هر TradeRecord:
            ۱. option_kind از پیشوند نماد
            ۲. option_kind از Snapshot (اگر موجود)
            ۳. strike_price, expiry_date, contract_size, ins_code
               از Snapshot
            ۴. اگر هیچ‌کدام پیدا نشد، needs_review=True
    """

    def enrich(
        self,
        trades: List[TradeRecord],
        snapshot,
    ) -> List[TradeRecord]:
        """پر کردن همه‌ی trades با اطلاعات Snapshot"""
        if snapshot is None:
            logger.warning("Snapshot is None — marking all as needs_review")
            for t in trades:
                self._enrich_without_snapshot(t)
            return trades

        for trade in trades:
            self._enrich_one(trade, snapshot)

        n_complete = sum(1 for t in trades if t.is_complete)
        n_incomplete = len(trades) - n_complete
        logger.info(
            f"Enriched {len(trades)} trades "
            f"(complete: {n_complete}, incomplete: {n_incomplete})")

        return trades

    def _enrich_one(self, trade: TradeRecord, snapshot):
        """پر کردن یک trade"""
        # ۱. تشخیص نوع از پیشوند
        if trade.option_kind is None:
            trade.option_kind = infer_option_kind_from_symbol(
                trade.symbol)

        # ۲. اگر سهم پایه است، کافی است
        if trade.option_kind == OptionType.STOCK:
            if not trade.underlying_symbol:
                trade.underlying_symbol = trade.symbol
            trade.needs_review = False
            return

        # ۳. جستجو در Snapshot
        contract = None
        try:
            contract = snapshot.get_options_by_symbol(trade.symbol)
        except Exception as e:
            logger.debug(f"get_options_by_symbol failed: {e}")

        if contract is not None:
            self._fill_from_contract(trade, contract)
            trade.needs_review = not trade.is_complete
            return

        # ۴. پیدا نشد — تلاش با نام پایه
        underlying = infer_underlying_from_symbol(trade.symbol)
        if underlying and not trade.underlying_symbol:
            trade.underlying_symbol = underlying

        trade.needs_review = True
        if "قرارداد در Snapshot پیدا نشد" not in trade.warnings:
            trade.warnings.append("قرارداد در Snapshot پیدا نشد")

    def _fill_from_contract(self, trade: TradeRecord, contract):
        """پر کردن از یک قرارداد Snapshot"""
        try:
            if trade.strike_price is None:
                sp = getattr(contract, "strike_price", None)
                if sp and sp > 0:
                    trade.strike_price = float(sp)

            if not trade.expiry_date:
                ed = getattr(contract, "expiry_date", "")
                if ed:
                    trade.expiry_date = str(ed)

            if trade.contract_size <= 0:
                cs = getattr(contract, "contract_size", 0)
                if cs and cs > 0:
                    trade.contract_size = int(cs)
                else:
                    trade.contract_size = 1000

            if not trade.ins_code:
                ic = getattr(contract, "instrument_code", "")
                if ic:
                    trade.ins_code = str(ic)

            if not trade.underlying_symbol:
                ut = getattr(contract, "underlying_ticker", "")
                if ut:
                    trade.underlying_symbol = normalize_symbol(ut)

            if trade.option_kind is None:
                ot = getattr(contract, "option_type", None)
                if ot is not None:
                    trade.option_kind = ot
        except Exception as e:
            logger.debug(f"Fill from contract failed: {e}")

    def _enrich_without_snapshot(self, trade: TradeRecord):
        """وقتی Snapshot در دسترس نیست"""
        if trade.option_kind is None:
            trade.option_kind = infer_option_kind_from_symbol(
                trade.symbol)

        if trade.option_kind == OptionType.STOCK:
            trade.underlying_symbol = trade.symbol
            trade.needs_review = False
            return

        # آپشن بدون Snapshot
        trade.needs_review = True
        if not trade.underlying_symbol:
            trade.underlying_symbol = infer_underlying_from_symbol(
                trade.symbol)


__all__ = [
    "SnapshotEnricher",
    "infer_option_kind_from_symbol",
    "infer_underlying_from_symbol",
]