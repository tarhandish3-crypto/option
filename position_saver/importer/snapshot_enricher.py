# position_saver/importer/snapshot_enricher.py
# -*- coding: utf-8 -*-

"""
پر کردن فیلدهای ناقص از Snapshot + SYMBOL_MAP + Symbol Memory.

منطق (ساده‌شده):
    ۱. تشخیص نوع نماد (آپشن / سهم / ناشناخته)
    ۲. اگر آپشن → lookup در Snapshot با fallback
    ۳. اگر سهم پایه → ins_code_ua از SYMBOL_MAP
    ۴. اگر هنوز ناقص است → lookup در Symbol Memory
    ۵. تعیین close_reason پیش‌فرض ساده:
        - سهم → STOCK
        - ناقص → INCOMPLETE
        - کامل → UNKNOWN (کاربر در تب تکمیل‌شده تعیین می‌کند)

هیچ تصمیم خودکاری درباره‌ی OFFSET/EXERCISE/... گرفته نمی‌شود.
"""

import logging
import re
from typing import List, Optional

from core.enums import OptionType
from position_saver.storage import normalize_symbol
from position_saver.importer.schemas import (
    TradeRecord,
    CLOSE_REASON_UNKNOWN,
    CLOSE_REASON_STOCK,
    CLOSE_REASON_INCOMPLETE,
)
from position_saver.importer.symbol_map import (
    is_known_underlying,
    get_underlying_ins_code,
    is_option_symbol,
    infer_underlying_from_option,
)
from position_saver.importer.symbol_memory import get_symbol_info


logger = logging.getLogger("PositionSaver.Importer.Enricher")


# ═══════════════════════════════════════════════════
# SnapshotEnricher
# ═══════════════════════════════════════════════════

class SnapshotEnricher:
    """
    پر کردن فیلدهای ناقص با استفاده از:
        - Snapshot زنده
        - SYMBOL_MAP (لیست نمادهای پایه)
        - Symbol Memory (حافظه‌ی ذخیره‌شده)
    """

    def enrich(
        self,
        trades: List[TradeRecord],
        snapshot,
    ) -> List[TradeRecord]:
        """پر کردن همه‌ی trades"""
        for trade in trades:
            try:
                self._enrich_one(trade, snapshot)
            except Exception as e:
                logger.exception(
                    f"Enrich failed for {trade.trade_id}: {e}")
                trade.needs_review = True
                trade.warnings.append(f"خطا در Enrichment: {e}")

        n_complete = sum(1 for t in trades if t.is_complete)
        n_incomplete = len(trades) - n_complete
        logger.info(
            f"Enriched {len(trades)} trades "
            f"(complete: {n_complete}, incomplete: {n_incomplete})")

        return trades

    # ═══════════════════════════════════════════════
    # داخلی
    # ═══════════════════════════════════════════════

    def _enrich_one(self, trade: TradeRecord, snapshot):
        """پر کردن یک trade"""
        # ─── تشخیص نوع نماد ───
        if trade.option_kind is None:
            if is_option_symbol(trade.symbol):
                trade.option_kind = (
                    OptionType.CALL
                    if trade.symbol.startswith("ض")
                    else OptionType.PUT
                )
            elif is_known_underlying(trade.symbol):
                trade.option_kind = OptionType.STOCK
            else:
                self._try_detect_from_snapshot(trade, snapshot)

        # ─── مسیر بر اساس نوع ───
        if trade.is_option:
            self._enrich_option(trade, snapshot)
        elif trade.is_stock:
            self._enrich_stock(trade, snapshot)
        else:
            self._enrich_unknown(trade)

        # ─── اگر هنوز ناقص است → حافظه ───
        if trade.is_incomplete and not trade.is_stock:
            self._try_fill_from_memory(trade)

        # ─── نهایی‌سازی close_reason ───
        self._finalize_close_reason(trade)

    # ═══════════════════════════════════════════════
    # نهایی‌سازی close_reason (ساده)
    # ═══════════════════════════════════════════════

    def _finalize_close_reason(self, trade: TradeRecord):
        """
        تعیین close_reason پیش‌فرض ساده.

        قاعده:
            - سهم پایه → STOCK
            - ناقص → INCOMPLETE
            - آپشن کامل → UNKNOWN (کاربر در تب تکمیل‌شده تصمیم می‌گیرد)
        """
        if trade.is_stock:
            trade.close_reason = CLOSE_REASON_STOCK
            return

        if not trade.is_complete:
            trade.close_reason = CLOSE_REASON_INCOMPLETE
            return

        # آپشن کامل — کاربر تصمیم می‌گیرد
        if trade.close_reason in ("", CLOSE_REASON_INCOMPLETE):
            trade.close_reason = CLOSE_REASON_UNKNOWN

    # ═══════════════════════════════════════════════
    # آپشن
    # ═══════════════════════════════════════════════

    def _enrich_option(self, trade: TradeRecord, snapshot):
        """Enrich یک آپشن"""
        # نام سهم پایه از پیشوند
        if not trade.underlying_symbol:
            trade.underlying_symbol = infer_underlying_from_option(
                trade.symbol)

        # ins_code_ua از SYMBOL_MAP
        if not trade.ins_code_ua and trade.underlying_symbol:
            trade.ins_code_ua = get_underlying_ins_code(
                trade.underlying_symbol)

        # lookup در Snapshot
        if snapshot is not None:
            contract = None
            try:
                contract = snapshot.get_options_by_symbol(trade.symbol)
            except Exception as e:
                logger.debug(f"get_options_by_symbol failed: {e}")

            if contract is not None:
                self._fill_from_contract(trade, contract)

        # اگر بعد از Snapshot هنوز ناقص است → حافظه
        if not trade.is_complete:
            self._try_fill_from_memory(trade)

        # به‌روزرسانی وضعیت
        trade.needs_review = not trade.is_complete

        if trade.needs_review:
            if ("قرارداد در Snapshot و حافظه پیدا نشد"
                    not in trade.warnings):
                trade.warnings.append(
                    "قرارداد در Snapshot و حافظه پیدا نشد")

    def _fill_from_contract(self, trade: TradeRecord, contract):
        """
        پر کردن از قرارداد Snapshot با fallback روی نام‌های محتمل.
        """
        try:
            # ─── strike_price ───
            if not trade.strike_price or trade.strike_price <= 0:
                for attr in ("strike_price", "strike",
                             "exercise_price", "k"):
                    sp = getattr(contract, attr, None)
                    if sp is None:
                        continue
                    try:
                        spv = float(sp)
                        if spv > 0:
                            trade.strike_price = spv
                            break
                    except (TypeError, ValueError):
                        continue

            # ─── expiry_date ───
            if not trade.expiry_date:
                for attr in ("expiry_date", "expiry",
                             "maturity_date", "expire_date",
                             "expiration", "expiry_jalali"):
                    ed = getattr(contract, attr, None)
                    if ed:
                        trade.expiry_date = self._normalize_date(
                            str(ed))
                        break

            # ─── contract_size ───
            if trade.contract_size <= 0:
                for attr in ("contract_size", "size",
                             "lot_size", "multiplier"):
                    cs = getattr(contract, attr, None)
                    if cs is None:
                        continue
                    try:
                        csv = int(cs)
                        if csv > 0:
                            trade.contract_size = csv
                            break
                    except (TypeError, ValueError):
                        continue
                if trade.contract_size <= 0:
                    trade.contract_size = 1000

            # ─── ins_code ───
            if not trade.ins_code:
                for attr in ("instrument_code", "ins_code",
                             "instrument_id", "code"):
                    ic = getattr(contract, attr, None)
                    if ic:
                        trade.ins_code = str(ic)
                        break

            # ─── underlying_symbol ───
            if not trade.underlying_symbol:
                for attr in ("underlying_ticker",
                             "underlying_symbol",
                             "base_symbol", "symbol_ua",
                             "underlying"):
                    ut = getattr(contract, attr, None)
                    if ut:
                        trade.underlying_symbol = normalize_symbol(
                            str(ut))
                        break

            # ─── ins_code_ua ───
            if not trade.ins_code_ua:
                for attr in ("underlying_ins_code", "ins_code_ua",
                             "instrument_code_ua", "ua_code"):
                    icu = getattr(contract, attr, None)
                    if icu:
                        trade.ins_code_ua = str(icu)
                        break
                if not trade.ins_code_ua and trade.underlying_symbol:
                    trade.ins_code_ua = get_underlying_ins_code(
                        trade.underlying_symbol)

            # ─── option_kind ───
            if trade.option_kind is None:
                for attr in ("option_type", "kind", "type",
                             "option_kind"):
                    ot = getattr(contract, attr, None)
                    if ot is None:
                        continue
                    if isinstance(ot, str):
                        ot_upper = ot.upper()
                        if ("CALL" in ot_upper
                                or "خرید" in ot_upper):
                            trade.option_kind = OptionType.CALL
                        elif ("PUT" in ot_upper
                                or "فروش" in ot_upper):
                            trade.option_kind = OptionType.PUT
                    else:
                        trade.option_kind = ot
                    break

        except Exception as e:
            logger.debug(f"Fill from contract failed: {e}")

    # ═══════════════════════════════════════════════
    # Symbol Memory
    # ═══════════════════════════════════════════════

    def _try_fill_from_memory(self, trade: TradeRecord) -> bool:
        """
        تلاش برای پر کردن فیلدهای ناقص از حافظه‌ی نماد.

        Returns:
            True اگر حداقل یک فیلد پر شد
        """
        try:
            info = get_symbol_info(trade.symbol)
        except Exception as e:
            logger.debug(f"get_symbol_info failed: {e}")
            return False

        if not info:
            return False

        filled = False

        # ─── strike ───
        if not trade.strike_price and info.get("strike_price"):
            try:
                trade.strike_price = float(info["strike_price"])
                filled = True
            except (TypeError, ValueError):
                pass

        # ─── expiry ───
        if not trade.expiry_date and info.get("expiry_date"):
            trade.expiry_date = self._normalize_date(
                str(info["expiry_date"]))
            filled = True

        # ─── contract_size ───
        if trade.contract_size <= 0 and info.get("contract_size"):
            try:
                trade.contract_size = int(info["contract_size"])
                filled = True
            except (TypeError, ValueError):
                pass

        # ─── underlying_symbol ───
        if not trade.underlying_symbol and info.get("underlying_symbol"):
            trade.underlying_symbol = str(info["underlying_symbol"])
            filled = True

        # ─── ins_code ───
        if not trade.ins_code and info.get("ins_code"):
            trade.ins_code = str(info["ins_code"])
            filled = True

        # ─── ins_code_ua ───
        if not trade.ins_code_ua and info.get("ins_code_ua"):
            trade.ins_code_ua = str(info["ins_code_ua"])
            filled = True

        # ─── option_kind ───
        if trade.option_kind is None and info.get("option_kind"):
            try:
                trade.option_kind = OptionType[info["option_kind"]]
                filled = True
            except KeyError:
                pass

        if filled:
            msg = "اطلاعات از حافظه‌ی نماد پر شد"
            if msg not in trade.warnings:
                trade.warnings.append(msg)
            trade.needs_review = not trade.is_complete

            logger.debug(
                f"Filled {trade.symbol} from memory: "
                f"strike={trade.strike_price}, "
                f"expiry={trade.expiry_date}")

        return filled

    # ═══════════════════════════════════════════════
    # سهم پایه
    # ═══════════════════════════════════════════════

    def _enrich_stock(self, trade: TradeRecord, snapshot):
        """Enrich یک سهم پایه"""
        if not trade.underlying_symbol:
            trade.underlying_symbol = trade.symbol

        if not trade.ins_code_ua:
            trade.ins_code_ua = get_underlying_ins_code(trade.symbol)

        # سهم نیازی به strike/expiry ندارد
        trade.strike_price = None
        trade.expiry_date = ""
        trade.contract_size = 1

        trade.needs_review = False

    # ═══════════════════════════════════════════════
    # ناشناخته
    # ═══════════════════════════════════════════════

    def _enrich_unknown(self, trade: TradeRecord):
        """نماد ناشناخته — قبل از علامت‌گذاری، حافظه را چک کن"""
        if self._try_fill_from_memory(trade):
            if trade.is_complete:
                trade.needs_review = False
                return

        trade.needs_review = True
        if "نماد ناشناخته — نیازمند تعیین دستی" not in trade.warnings:
            trade.warnings.append(
                "نماد ناشناخته — نیازمند تعیین دستی")

    def _try_detect_from_snapshot(self, trade: TradeRecord, snapshot):
        """تلاش برای تشخیص نوع نماد از Snapshot"""
        if snapshot is None:
            return

        # آیا سهم پایه است؟
        try:
            ua = snapshot.get_underlying_assets(trade.symbol)
            if ua is not None:
                trade.option_kind = OptionType.STOCK
                return
        except Exception:
            pass

        # آیا آپشن است؟
        try:
            opt = snapshot.get_options_by_symbol(trade.symbol)
            if opt is not None:
                ot = getattr(opt, "option_type", None)
                if ot is not None:
                    trade.option_kind = ot
                else:
                    trade.option_kind = (
                        OptionType.CALL
                        if trade.symbol.startswith("ض")
                        else OptionType.PUT)
                return
        except Exception:
            pass

    # ═══════════════════════════════════════════════
    # کمکی
    # ═══════════════════════════════════════════════

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """نرمال‌سازی تاریخ شمسی به YYYY/MM/DD"""
        if not date_str:
            return ""
        s = str(date_str).strip()
        m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
        if not m:
            return s
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        return f"{y:04d}/{mo:02d}/{d:02d}"


# ═══════════════════════════════════════════════════
# توابع کمکی قدیمی (برای backward compatibility)
# ═══════════════════════════════════════════════════

def infer_option_kind_from_symbol(symbol: str) -> Optional[OptionType]:
    """حدس نوع اختیار از پیشوند نماد"""
    if not symbol:
        return None
    s = str(symbol).strip()
    if s.startswith("ض"):
        return OptionType.CALL
    if s.startswith("ط"):
        return OptionType.PUT
    if is_known_underlying(s):
        return OptionType.STOCK
    return None


def infer_underlying_from_symbol(symbol: str) -> str:
    """حدس نماد پایه از نماد اختیار"""
    return infer_underlying_from_option(symbol)


__all__ = [
    "SnapshotEnricher",
    "infer_option_kind_from_symbol",
    "infer_underlying_from_symbol",
]