# position_saver/importer/schemas.py
# -*- coding: utf-8 -*-

"""
ساختار داده‌های موقت برای ایمپورت اکسل کارگزاری.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core.enums import OptionType
from position_saver.models import LegType


# ═══════════════════════════════════════════════════
# مقادیر close_reason
# ═══════════════════════════════════════════════════

CLOSE_REASON_OPEN = "open"
CLOSE_REASON_OFFSET = "offset"
CLOSE_REASON_EXERCISE = "exercise"
CLOSE_REASON_CASH_SETTLE = "cash_settle"
CLOSE_REASON_DEFAULTED = "defaulted"
CLOSE_REASON_YOU_DEFAULTED = "you_defaulted"
CLOSE_REASON_UNKNOWN = "unknown"
CLOSE_REASON_STOCK = "stock"
CLOSE_REASON_INCOMPLETE = "incomplete"

CLOSE_REASON_LABELS = {
    CLOSE_REASON_OPEN: "🟢 باز",
    CLOSE_REASON_OFFSET: "🟢 آفست شده",
    CLOSE_REASON_EXERCISE: "🏦 اعمال فیزیکی",
    CLOSE_REASON_CASH_SETTLE: "💵 تسویه نقدی",
    CLOSE_REASON_DEFAULTED: "⚖️ نکول طرف مقابل",
    CLOSE_REASON_YOU_DEFAULTED: "❌ نکول خودم",
    CLOSE_REASON_UNKNOWN: "⚫ نیازمند تصمیم",
    CLOSE_REASON_STOCK: "🏢 سهم پایه",
    CLOSE_REASON_INCOMPLETE: "⚠️ ناقص",
}


# ═══════════════════════════════════════════════════
# TradeRecord
# ═══════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """یک ردیف معامله پارس‌شده از اکسل."""

    trade_id: str = field(
        default_factory=lambda: f"trade_{str(uuid.uuid4())[:6]}")
    timestamp: Optional[datetime] = None
    raw_date: str = ""
    raw_time: str = ""
    symbol: str = ""
    side: LegType = LegType.BUY
    quantity: int = 0
    price: float = 0.0
    raw_status: str = ""

    broker: str = ""

    strike_price: Optional[float] = None
    expiry_date: str = ""
    contract_size: int = 0
    option_kind: Optional[OptionType] = None
    underlying_symbol: str = ""
    ins_code: str = ""
    ins_code_ua: str = ""

    is_selected: bool = False
    auto_selected: bool = False
    needs_review: bool = False
    user_edited: bool = False
    warnings: List[str] = field(default_factory=list)

    close_reason: str = ""
    close_price: Optional[float] = None
    close_date: str = ""
    close_trade_ref: str = ""
    user_chosen_reason: bool = False
    details: str = ""

    # ─── Propertyها ───

    @property
    def is_option(self) -> bool:
        if self.option_kind is None:
            return self.symbol.startswith(("ض", "ط"))
        return self.option_kind != OptionType.STOCK

    @property
    def is_call(self) -> bool:
        return self.option_kind == OptionType.CALL

    @property
    def is_put(self) -> bool:
        return self.option_kind == OptionType.PUT

    @property
    def is_stock(self) -> bool:
        return self.option_kind == OptionType.STOCK

    @property
    def is_buy(self) -> bool:
        return self.side == LegType.BUY

    @property
    def is_sell(self) -> bool:
        return self.side == LegType.SELL

    @property
    def is_stock_underlying(self) -> bool:
        return self.is_stock and bool(self.underlying_symbol)

    @property
    def is_unknown(self) -> bool:
        return (not self.is_option
                and not self.is_stock
                and self.option_kind is None)

    @property
    def effective_contract_size(self) -> int:
        if not self.is_option:
            return 1
        return self.contract_size if self.contract_size > 0 else 1000

    @property
    def is_complete(self) -> bool:
        if not self.symbol:
            return False
        if self.option_kind is None:
            return False
        if self.option_kind == OptionType.STOCK:
            return True
        return (
            self.strike_price is not None
            and self.strike_price > 0
            and bool(self.expiry_date)
        )

    @property
    def is_incomplete(self) -> bool:
        return not self.is_complete

    @property
    def is_expired(self) -> bool:
        if not self.is_option or not self.expiry_date:
            return False
        from position_saver.live_monitor import is_expired_date
        return is_expired_date(self.expiry_date)

    @property
    def needs_close_decision(self) -> bool:
        return (
            self.is_option
            and self.is_expired
            and self.close_reason == CLOSE_REASON_UNKNOWN
            and not self.user_chosen_reason
        )

    @property
    def is_ready_for_import(self) -> bool:
        """
        ✅ آماده برای انتقال به تکمیل‌شده.

        فقط اطلاعات پایه کافی است (symbol + strike + expiry برای آپشن).
        نوع بستن در تب تکمیل‌شده توسط کاربر تعیین می‌شود.
        """
        return self.is_complete

    @property
    def close_reason_label(self) -> str:
        return CLOSE_REASON_LABELS.get(
            self.close_reason, self.close_reason or "—")

    @property
    def datetime_str(self) -> str:
        if self.timestamp is None:
            return f"{self.raw_date} {self.raw_time}".strip()
        try:
            return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return f"{self.raw_date} {self.raw_time}".strip()

    @property
    def side_label_fa(self) -> str:
        return self.side.label_fa

    @property
    def duplicate_key(self) -> tuple:
        return (self.symbol, self.raw_date, self.raw_time,
                self.side.value)

    # ─── محاسبات ───

    def value(self) -> float:
        return self.quantity * self.price * self.effective_contract_size

    def signed_quantity(self) -> int:
        return self.quantity * self.side.side_sign

    def signed_value(self) -> float:
        if self.side == LegType.BUY:
            return -self.value()
        return self.value()

    # ─── Serialization ───

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "timestamp": (self.timestamp.isoformat()
                          if self.timestamp else None),
            "raw_date": self.raw_date,
            "raw_time": self.raw_time,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "raw_status": self.raw_status,
            "broker": self.broker,
            "strike_price": self.strike_price,
            "expiry_date": self.expiry_date,
            "contract_size": self.contract_size,
            "option_kind": (self.option_kind.name
                            if self.option_kind else None),
            "underlying_symbol": self.underlying_symbol,
            "ins_code": self.ins_code,
            "ins_code_ua": self.ins_code_ua,
            "is_selected": self.is_selected,
            "auto_selected": self.auto_selected,
            "needs_review": self.needs_review,
            "user_edited": self.user_edited,
            "warnings": list(self.warnings),
            "close_reason": self.close_reason,
            "close_price": self.close_price,
            "close_date": self.close_date,
            "close_trade_ref": self.close_trade_ref,
            "user_chosen_reason": self.user_chosen_reason,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRecord":
        ts_raw = data.get("timestamp")
        ts = None
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw)
            except Exception:
                ts = None

        ok_raw = data.get("option_kind")
        option_kind = None
        if ok_raw:
            try:
                option_kind = OptionType[ok_raw]
            except KeyError:
                option_kind = None

        try:
            side = LegType.from_value(data.get("side", "buy"))
        except ValueError:
            side = LegType.BUY

        cp_raw = data.get("close_price")
        close_price = None
        if cp_raw is not None:
            try:
                close_price = float(cp_raw)
            except (TypeError, ValueError):
                close_price = None

        return cls(
            trade_id=data.get("trade_id", ""),
            timestamp=ts,
            raw_date=data.get("raw_date", ""),
            raw_time=data.get("raw_time", ""),
            symbol=data.get("symbol", ""),
            side=side,
            quantity=int(data.get("quantity", 0)),
            price=float(data.get("price", 0.0)),
            raw_status=data.get("raw_status", ""),
            broker=data.get("broker", ""),
            strike_price=(float(data["strike_price"])
                          if data.get("strike_price") is not None
                          else None),
            expiry_date=data.get("expiry_date", ""),
            contract_size=int(data.get("contract_size", 0)),
            option_kind=option_kind,
            underlying_symbol=data.get("underlying_symbol", ""),
            ins_code=data.get("ins_code", ""),
            ins_code_ua=data.get("ins_code_ua", ""),
            is_selected=bool(data.get("is_selected", False)),
            auto_selected=bool(data.get("auto_selected", False)),
            needs_review=bool(data.get("needs_review", False)),
            user_edited=bool(data.get("user_edited", False)),
            warnings=list(data.get("warnings", [])),
            close_reason=data.get("close_reason", ""),
            close_price=close_price,
            close_date=data.get("close_date", ""),
            close_trade_ref=data.get("close_trade_ref", ""),
            user_chosen_reason=bool(
                data.get("user_chosen_reason", False)),
            details=data.get("details", ""),
        )

    def copy(self) -> "TradeRecord":
        return TradeRecord.from_dict(self.to_dict())

    def copy_with_quantity(self, new_qty: int) -> "TradeRecord":
        new_t = self.copy()
        new_t.quantity = new_qty
        new_t.trade_id = f"{self.trade_id}_q{new_qty}"
        return new_t


# ═══════════════════════════════════════════════════
# MatchedLot
# ═══════════════════════════════════════════════════

@dataclass
class MatchedLot:
    lot_id: str = field(
        default_factory=lambda: f"lot_{str(uuid.uuid4())[:6]}")
    symbol: str = ""
    open_trade: Optional[TradeRecord] = None
    close_trade: Optional[TradeRecord] = None
    realized_pnl: Optional[float] = None

    @property
    def is_closed(self) -> bool:
        return self.close_trade is not None

    @property
    def is_open(self) -> bool:
        return self.close_trade is None

    @property
    def quantity(self) -> int:
        return self.open_trade.quantity if self.open_trade else 0

    @property
    def entry_price(self) -> float:
        return self.open_trade.price if self.open_trade else 0.0

    @property
    def close_price(self) -> Optional[float]:
        return self.close_trade.price if self.close_trade else None

    @property
    def entry_value(self) -> float:
        return self.open_trade.value() if self.open_trade else 0.0

    @property
    def close_value(self) -> float:
        return self.close_trade.value() if self.close_trade else 0.0

    @property
    def open_timestamp(self) -> Optional[datetime]:
        return self.open_trade.timestamp if self.open_trade else None

    @property
    def close_timestamp(self) -> Optional[datetime]:
        return self.close_trade.timestamp if self.close_trade else None

    @property
    def entry_date_jalali(self) -> str:
        return self.open_trade.raw_date if self.open_trade else ""

    @property
    def close_date_jalali(self) -> str:
        return self.close_trade.raw_date if self.close_trade else ""

    @property
    def option_kind(self):
        return self.open_trade.option_kind if self.open_trade else None

    @property
    def underlying_symbol(self) -> str:
        return (self.open_trade.underlying_symbol
                if self.open_trade else "")

    def holding_days(self) -> Optional[int]:
        if not self.open_timestamp or not self.close_timestamp:
            return None
        return (self.close_timestamp - self.open_timestamp).days

    def gross_pnl(self) -> Optional[float]:
        if not self.is_closed:
            return None
        return self.close_value - self.entry_value

    def to_dict(self) -> dict:
        return {
            "lot_id": self.lot_id,
            "symbol": self.symbol,
            "open_trade": (self.open_trade.to_dict()
                           if self.open_trade else None),
            "close_trade": (self.close_trade.to_dict()
                            if self.close_trade else None),
            "realized_pnl": self.realized_pnl,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MatchedLot":
        open_raw = data.get("open_trade")
        close_raw = data.get("close_trade")
        realized = data.get("realized_pnl")
        if realized is not None:
            try:
                realized = float(realized)
            except (TypeError, ValueError):
                realized = None
        return cls(
            lot_id=data.get("lot_id", ""),
            symbol=data.get("symbol", ""),
            open_trade=(TradeRecord.from_dict(open_raw)
                        if open_raw else None),
            close_trade=(TradeRecord.from_dict(close_raw)
                         if close_raw else None),
            realized_pnl=realized,
        )

    def copy(self) -> "MatchedLot":
        return MatchedLot.from_dict(self.to_dict())


# ═══════════════════════════════════════════════════
# ImportSettings / ImportBatch / ImportResult / BrokerTemplate
# ═══════════════════════════════════════════════════

@dataclass
class ImportSettings:
    match_method: str = "fifo"
    time_window_seconds: int = 60
    group_by_underlying: bool = True
    skip_duplicates: bool = True
    valid_statuses: List[str] = field(default_factory=list)
    default_alert_roi: float = 10.0

    def to_dict(self) -> dict:
        return {
            "match_method": self.match_method,
            "time_window_seconds": self.time_window_seconds,
            "group_by_underlying": self.group_by_underlying,
            "skip_duplicates": self.skip_duplicates,
            "valid_statuses": list(self.valid_statuses),
            "default_alert_roi": self.default_alert_roi,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImportSettings":
        return cls(
            match_method=data.get("match_method", "fifo"),
            time_window_seconds=int(
                data.get("time_window_seconds", 60)),
            group_by_underlying=bool(
                data.get("group_by_underlying", True)),
            skip_duplicates=bool(data.get("skip_duplicates", True)),
            valid_statuses=list(data.get("valid_statuses", [])),
            default_alert_roi=float(
                data.get("default_alert_roi", 10.0)),
        )


@dataclass
class ImportBatch:
    batch_id: str = field(
        default_factory=lambda: (
            datetime.now().strftime("%Y%m%d-%H%M%S-")
            + str(uuid.uuid4())[:4]))
    broker: str = ""
    source_file: str = ""
    created_at: str = ""
    import_date_jalali: str = ""
    n_trades: int = 0
    n_positions_open: int = 0
    n_positions_closed: int = 0
    n_needs_review: int = 0
    n_duplicates: int = 0
    position_ids: List[str] = field(default_factory=list)

    @property
    def n_positions_total(self) -> int:
        return self.n_positions_open + self.n_positions_closed

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "broker": self.broker,
            "source_file": self.source_file,
            "created_at": self.created_at,
            "import_date_jalali": self.import_date_jalali,
            "n_trades": self.n_trades,
            "n_positions_open": self.n_positions_open,
            "n_positions_closed": self.n_positions_closed,
            "n_needs_review": self.n_needs_review,
            "n_duplicates": self.n_duplicates,
            "position_ids": list(self.position_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImportBatch":
        return cls(
            batch_id=data.get("batch_id", ""),
            broker=data.get("broker", ""),
            source_file=data.get("source_file", ""),
            created_at=data.get("created_at", ""),
            import_date_jalali=data.get("import_date_jalali", ""),
            n_trades=int(data.get("n_trades", 0)),
            n_positions_open=int(data.get("n_positions_open", 0)),
            n_positions_closed=int(data.get("n_positions_closed", 0)),
            n_needs_review=int(data.get("n_needs_review", 0)),
            n_duplicates=int(data.get("n_duplicates", 0)),
            position_ids=list(data.get("position_ids", [])),
        )


@dataclass
class ImportResult:
    trades: List[TradeRecord] = field(default_factory=list)
    complete_trades: List[TradeRecord] = field(default_factory=list)
    incomplete_trades: List[TradeRecord] = field(default_factory=list)
    lots: List[MatchedLot] = field(default_factory=list)
    open_lots: List[MatchedLot] = field(default_factory=list)
    closed_lots: List[MatchedLot] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_incomplete(self) -> bool:
        return len(self.incomplete_trades) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def n_complete(self) -> int:
        return len(self.complete_trades)

    @property
    def n_incomplete(self) -> int:
        return len(self.incomplete_trades)

    @property
    def n_open_lots(self) -> int:
        return len(self.open_lots)

    @property
    def n_closed_lots(self) -> int:
        return len(self.closed_lots)

    def summary_text(self) -> str:
        parts = [
            f"کل: {self.n_trades}",
            f"کامل: {self.n_complete}",
        ]
        if self.n_incomplete:
            parts.append(f"ناقص: {self.n_incomplete}")
        parts.append(f"بسته: {self.n_closed_lots}")
        parts.append(f"باز: {self.n_open_lots}")
        return " | ".join(parts)


@dataclass
class BrokerTemplate:
    broker_name: str = ""
    date_col: str = "تاریخ"
    time_col: str = "ساعت"
    side_col: str = "سمت سفارش"
    symbol_col: str = "نماد"
    qty_col: str = "حجم انجام شده"
    price_col: str = "قیمت"
    status_col: str = "وضعیت"
    valid_statuses: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "broker_name": self.broker_name,
            "date_col": self.date_col,
            "time_col": self.time_col,
            "side_col": self.side_col,
            "symbol_col": self.symbol_col,
            "qty_col": self.qty_col,
            "price_col": self.price_col,
            "status_col": self.status_col,
            "valid_statuses": list(self.valid_statuses),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrokerTemplate":
        return cls(
            broker_name=data.get("broker_name", ""),
            date_col=data.get("date_col", "تاریخ"),
            time_col=data.get("time_col", "ساعت"),
            side_col=data.get("side_col", "سمت سفارش"),
            symbol_col=data.get("symbol_col", "نماد"),
            qty_col=data.get("qty_col", "حجم انجام شده"),
            price_col=data.get("price_col", "قیمت"),
            status_col=data.get("status_col", "وضعیت"),
            valid_statuses=list(data.get("valid_statuses", [])),
        )

    def copy(self) -> "BrokerTemplate":
        return BrokerTemplate.from_dict(self.to_dict())


__all__ = [
    "TradeRecord",
    "MatchedLot",
    "ImportSettings",
    "ImportBatch",
    "ImportResult",
    "BrokerTemplate",
    "CLOSE_REASON_OPEN",
    "CLOSE_REASON_OFFSET",
    "CLOSE_REASON_EXERCISE",
    "CLOSE_REASON_CASH_SETTLE",
    "CLOSE_REASON_DEFAULTED",
    "CLOSE_REASON_YOU_DEFAULTED",
    "CLOSE_REASON_UNKNOWN",
    "CLOSE_REASON_STOCK",
    "CLOSE_REASON_INCOMPLETE",
    "CLOSE_REASON_LABELS",
]