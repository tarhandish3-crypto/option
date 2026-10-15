# position_saver/models.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import uuid
import re
import jdatetime
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

from core.enums import OptionType


# ═══════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════

def _parse_jalali_date(date_str: str) -> Optional[jdatetime.date]:
    """تبدیل رشته تاریخ شمسی به jdatetime.date."""
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


# ═══════════════════════════════════════════════════
# Enumها
# ═══════════════════════════════════════════════════

class LegType(Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def label_fa(self) -> str:
        return "خرید" if self == LegType.BUY else "فروش"

    @property
    def side_sign(self) -> int:
        return 1 if self == LegType.BUY else -1

    @classmethod
    def from_value(cls, value) -> "LegType":
        if isinstance(value, cls):
            return value
        v = str(value).strip().lower()
        if v in ("buy", "خرید", "long"):
            return cls.BUY
        if v in ("sell", "فروش", "short"):
            return cls.SELL
        raise ValueError(f"Unknown leg_type: {value}")


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXERCISED = "exercised"
    CASH_SETTLED = "cash_settled"
    DEFAULTED = "defaulted"
    YOU_DEFAULTED = "you_defaulted"

    @property
    def label_fa(self) -> str:
        return {
            PositionStatus.OPEN: "باز",
            PositionStatus.CLOSED: "بسته‌شده",
            PositionStatus.EXERCISED: "اعمال‌شده",
            PositionStatus.CASH_SETTLED: "تسویه نقدی",
            PositionStatus.DEFAULTED: "نکول طرف مقابل",
            PositionStatus.YOU_DEFAULTED: "نکول خودم",
        }[self]

    @property
    def is_final(self) -> bool:
        return self != PositionStatus.OPEN

    @property
    def is_default(self) -> bool:
        return self in (
            PositionStatus.DEFAULTED,
            PositionStatus.YOU_DEFAULTED,
        )

    @classmethod
    def from_value(cls, value) -> "PositionStatus":
        if isinstance(value, cls):
            return value
        v = str(value).strip().lower()
        for status in cls:
            if status.value == v or status.name.lower() == v:
                return status
        legacy = {
            "باز": cls.OPEN,
            "بسته‌شده": cls.CLOSED,
            "بسته شده": cls.CLOSED,
            "اعمال‌شده": cls.EXERCISED,
            "اعمال شده": cls.EXERCISED,
            "تسویه نقدی": cls.CASH_SETTLED,
            "نکول طرف مقابل": cls.DEFAULTED,
            "نکول خودم": cls.YOU_DEFAULTED,
        }
        if v in legacy:
            return legacy[v]
        raise ValueError(f"Unknown position status: {value}")


# ═══════════════════════════════════════════════════
# OptionLeg
# ═══════════════════════════════════════════════════

@dataclass
class OptionLeg:
    """یک لنگه معاملاتی."""

    # ─── اصلی ───
    leg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    is_option: bool = True
    option_kind: OptionType = OptionType.CALL
    leg_type: LegType = LegType.BUY
    strike_price: float = 0.0
    contract_size: int = 1000
    quantity: int = 0
    entry_price: float = 0.0
    entry_fee: float = 0.0
    current_price: float = 0.0
    close_price: Optional[float] = None
    close_fee: float = 0.0
    expiry_date: str = ""
    ins_code: str = ""
    ins_code_ua: str = ""

    # ─── تاریخ/زمان ───
    open_date: str = ""
    open_time: str = ""
    close_date: str = ""
    close_time: str = ""
    trade_time: str = ""

    # ─── نکول ───
    is_defaulted: bool = False
    default_penalty: float = 0.0
    default_payment: float = 0.0
    settlement_price: float = 0.0

    # ─── Import ───
    source: str = "manual"
    needs_review: bool = False
    trade_ref: str = ""
    close_trade_ref: str = ""
    realized_pnl: Optional[float] = None
    close_reason: str = ""

    # ─── Propertyها ───

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
    def effective_contract_size(self) -> int:
        if not self.is_option:
            return 1
        return self.contract_size if self.contract_size > 0 else 1000

    @property
    def is_closed(self) -> bool:
        return self.close_price is not None

    @property
    def is_open(self) -> bool:
        return self.close_price is None

    @property
    def total_shares(self) -> int:
        return self.quantity * self.effective_contract_size

    @property
    def direction_sign(self) -> int:
        return self.leg_type.side_sign

    # ─── محاسبات ───

    def entry_value(self) -> float:
        return (self.quantity * self.entry_price
                * self.effective_contract_size)

    def close_value(self) -> float:
        if self.close_price is None:
            return 0.0
        try:
            cp = float(self.close_price)
        except (TypeError, ValueError):
            return 0.0
        return (self.quantity * cp * self.effective_contract_size)

    def current_value(self) -> float:
        price = self.current_price if self.current_price > 0 \
            else self.entry_price
        return (self.quantity * price * self.effective_contract_size)

    def cash_flow_at_open(self) -> float:
        val = self.entry_value()
        fee = self.entry_fee if self.entry_fee > 0 else 0.0
        if self.leg_type == LegType.BUY:
            return -(val + fee)
        return val - fee

    def is_complete(self) -> bool:
        if self.is_stock:
            return bool(self.symbol)
        return (
            bool(self.symbol)
            and self.strike_price > 0
            and bool(self.expiry_date)
        )

    # ─── PnL (Delegate) ───

    def live_pnl(self) -> float:
        """PnL لحظه‌ای — Delegate به SharedAnalytics."""
        from position_saver.pnl_calculator import PositionPnLCalculator
        return PositionPnLCalculator.calculate_leg_live_pnl(self)

    def realized_pnl_value(self) -> float:
        """PnL محقق‌شده — Delegate به SharedAnalytics."""
        from position_saver.pnl_calculator import PositionPnLCalculator
        return PositionPnLCalculator.calculate_leg_realized_pnl(self)

    # ─── Serialization ───

    def to_dict(self) -> dict:
        return {
            "leg_id": self.leg_id,
            "symbol": self.symbol,
            "is_option": self.is_option,
            "option_kind": self.option_kind.name,
            "leg_type": self.leg_type.value,
            "strike_price": self.strike_price,
            "contract_size": self.contract_size,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_fee": self.entry_fee,
            "current_price": self.current_price,
            "close_price": self.close_price,
            "close_fee": self.close_fee,
            "expiry_date": self.expiry_date,
            "ins_code": self.ins_code,
            "ins_code_ua": self.ins_code_ua,
            "open_date": self.open_date,
            "open_time": self.open_time,
            "close_date": self.close_date,
            "close_time": self.close_time,
            "trade_time": self.trade_time,
            "is_defaulted": self.is_defaulted,
            "default_penalty": self.default_penalty,
            "default_payment": self.default_payment,
            "settlement_price": self.settlement_price,
            "source": self.source,
            "needs_review": self.needs_review,
            "trade_ref": self.trade_ref,
            "close_trade_ref": self.close_trade_ref,
            "realized_pnl": self.realized_pnl,
            "close_reason": self.close_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptionLeg":
        kind_name = data.get("option_kind")
        if kind_name:
            try:
                option_kind = OptionType[kind_name]
            except KeyError:
                option_kind = cls._infer_option_kind(
                    data.get("symbol", ""))
        else:
            option_kind = cls._infer_option_kind(
                data.get("symbol", ""))

        is_option = bool(
            data.get("is_option", option_kind != OptionType.STOCK))

        try:
            leg_type = LegType.from_value(data.get("leg_type", "buy"))
        except ValueError:
            leg_type = LegType.BUY

        close_price_raw = data.get("close_price")
        close_price: Optional[float] = None
        if close_price_raw is not None and close_price_raw != "":
            try:
                close_price = float(close_price_raw)
            except (TypeError, ValueError):
                close_price = None

        realized_pnl_raw = data.get("realized_pnl")
        realized_pnl: Optional[float] = None
        if realized_pnl_raw is not None:
            try:
                realized_pnl = float(realized_pnl_raw)
            except (TypeError, ValueError):
                realized_pnl = None

        return cls(
            leg_id=data.get("leg_id", str(uuid.uuid4())[:8]),
            symbol=data.get("symbol", ""),
            is_option=is_option,
            option_kind=option_kind,
            leg_type=leg_type,
            strike_price=float(data.get("strike_price", 0.0)),
            contract_size=int(data.get(
                "contract_size", 1000 if is_option else 1)),
            quantity=int(data.get("quantity", 0)),
            entry_price=float(data.get("entry_price", 0.0)),
            entry_fee=float(data.get("entry_fee", 0.0)),
            current_price=float(data.get("current_price", 0.0)),
            close_price=close_price,
            close_fee=float(data.get("close_fee", 0.0)),
            expiry_date=str(data.get("expiry_date", "")),
            ins_code=str(data.get("ins_code", "")),
            ins_code_ua=str(data.get("ins_code_ua", "")),
            open_date=str(data.get("open_date", "")),
            open_time=str(data.get("open_time", "")),
            close_date=str(data.get("close_date", "")),
            close_time=str(data.get("close_time", "")),
            trade_time=str(data.get("trade_time", "")),
            is_defaulted=bool(data.get("is_defaulted", False)),
            default_penalty=float(data.get("default_penalty", 0.0)),
            default_payment=float(data.get("default_payment", 0.0)),
            settlement_price=float(data.get("settlement_price", 0.0)),
            source=str(data.get("source", "manual")),
            needs_review=bool(data.get("needs_review", False)),
            trade_ref=str(data.get("trade_ref", "")),
            close_trade_ref=str(data.get("close_trade_ref", "")),
            realized_pnl=realized_pnl,
            close_reason=str(data.get("close_reason", "")),
        )

    @staticmethod
    def _infer_option_kind(symbol: str) -> OptionType:
        s = str(symbol).strip()
        if not s:
            return OptionType.STOCK
        if s.startswith("ض"):
            return OptionType.CALL
        if s.startswith("ط"):
            return OptionType.PUT
        return OptionType.STOCK

    def copy(self) -> "OptionLeg":
        return OptionLeg.from_dict(self.to_dict())


# ═══════════════════════════════════════════════════
# StrategyPosition — با فیلدهای جدید ✅
# ═══════════════════════════════════════════════════

@dataclass
class StrategyPosition:
    """موقعیت استراتژی — واحد معاملاتی (Lot)."""

    # ─── اصلی ───
    position_id: str = field(
        default_factory=lambda: f"POS-{str(uuid.uuid4())[:6].upper()}")
    strategy_name: str = ""
    strategy_type: str = ""
    broker_name: str = "مفید"
    underlying_symbol: str = ""
    underlying_price: float = 0.0
    underlying_price_at_close: float = 0.0
    execution_date: str = ""
    expiry_date: str = ""
    status: PositionStatus = PositionStatus.OPEN
    legs: List[OptionLeg] = field(default_factory=list)

    # ─── آلرت پویا ✅ ───
    target_roi_maturity: float = 0.0     # ROI ماهانه‌ی هدف (%)
    alert_enabled: bool = True            # ✅ جدید
    alert_sent: bool = False

    # ─── قیمت هدف سهم پایه (برای سود نامحدود) ✅ ───
    price_target: float = 0.0             # ✅ جدید

    # ─── بستن ───
    close_date: Optional[str] = None
    notes: str = ""

    # ─── Import ───
    source: str = "manual"
    import_batch_id: str = ""
    needs_review: bool = False
    cash_settlement_amount: float = 0.0
    close_reason: str = ""

    # ─── Propertyها ───

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status.is_final

    @property
    def option_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_option]

    @property
    def stock_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if not leg.is_option]

    @property
    def call_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_call]

    @property
    def put_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_put]

    @property
    def open_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_open]

    @property
    def closed_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_closed]

    @property
    def status_label_fa(self) -> str:
        return self.status.label_fa

    @property
    def total_legs(self) -> int:
        return len(self.legs)

    @property
    def is_imported(self) -> bool:
        return self.source == "excel_import"

    @property
    def has_incomplete_legs(self) -> bool:
        return any(leg.needs_review for leg in self.legs)

    # ─── محاسبات ───

    def days_to_expiry(self) -> Optional[int]:
        expiry = _parse_jalali_date(self.expiry_date)
        if expiry is None:
            return None
        today = jdatetime.date.today()
        return (expiry - today).days

    def days_elapsed(self) -> int:
        """روز سپری‌شده از اجرا."""
        start = _parse_jalali_date(self.execution_date)
        if start is None:
            return 0
        today = jdatetime.date.today()
        return max(0, (today - start).days)

    def total_days(self) -> int:
        """کل روز از اجرا تا سررسید."""
        start = _parse_jalali_date(self.execution_date)
        end = _parse_jalali_date(self.expiry_date)
        if start is None or end is None:
            return 30
        return max(1, (end - start).days)

    def has_any_close_price(self) -> bool:
        return any(l.close_price is not None for l in self.legs)

    def all_legs_closed(self) -> bool:
        return all(l.close_price is not None for l in self.legs)

    def total_live_pnl(self) -> float:
        """مجموع PnL لحظه‌ای — Delegate به PnLCalculator."""
        from position_saver.pnl_calculator import PositionPnLCalculator
        pnl, _ = PositionPnLCalculator.calculate_live_pnl(self)
        return pnl

    def total_realized_pnl(self) -> float:
        """مجموع PnL محقق‌شده — Delegate."""
        from position_saver.pnl_calculator import PositionPnLCalculator
        pnl, _ = PositionPnLCalculator.calculate_realized_pnl(self)
        return pnl

    def total_open_cost(self) -> float:
        """مجموع هزینه‌ی ورود لگ‌های باز."""
        return sum(
            leg.entry_value()
            for leg in self.legs if leg.is_open
        )

    # ─── Serialization ───

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "broker_name": self.broker_name,
            "underlying_symbol": self.underlying_symbol,
            "underlying_price": self.underlying_price,
            "underlying_price_at_close": self.underlying_price_at_close,
            "execution_date": self.execution_date,
            "expiry_date": self.expiry_date,
            "status": self.status.value,
            "target_roi_maturity": self.target_roi_maturity,
            "alert_enabled": self.alert_enabled,       # ✅
            "alert_sent": self.alert_sent,
            "price_target": self.price_target,          # ✅
            "close_date": self.close_date,
            "notes": self.notes,
            "source": self.source,
            "import_batch_id": self.import_batch_id,
            "needs_review": self.needs_review,
            "cash_settlement_amount": self.cash_settlement_amount,
            "close_reason": self.close_reason,
            "legs": [leg.to_dict() for leg in self.legs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyPosition":
        try:
            status = PositionStatus.from_value(
                data.get("status", "open"))
        except ValueError:
            status = PositionStatus.OPEN

        return cls(
            position_id=data.get("position_id", ""),
            strategy_name=data.get("strategy_name", ""),
            strategy_type=str(data.get("strategy_type", "")),
            broker_name=data.get("broker_name", "مفید"),
            underlying_symbol=data.get("underlying_symbol", ""),
            underlying_price=float(data.get("underlying_price", 0.0)),
            underlying_price_at_close=float(
                data.get("underlying_price_at_close", 0.0)),
            execution_date=str(data.get("execution_date", "")),
            expiry_date=str(data.get("expiry_date", "")),
            status=status,
            target_roi_maturity=float(
                data.get("target_roi_maturity", 0.0)),
            alert_enabled=bool(data.get("alert_enabled", True)),  # ✅
            alert_sent=bool(data.get("alert_sent", False)),
            price_target=float(data.get("price_target", 0.0)),    # ✅
            close_date=data.get("close_date"),
            notes=data.get("notes", ""),
            source=str(data.get("source", "manual")),
            import_batch_id=str(data.get("import_batch_id", "")),
            needs_review=bool(data.get("needs_review", False)),
            cash_settlement_amount=float(
                data.get("cash_settlement_amount", 0.0)),
            close_reason=str(data.get("close_reason", "")),
            legs=[OptionLeg.from_dict(l)
                  for l in data.get("legs", [])],
        )

    def copy(self) -> "StrategyPosition":
        return StrategyPosition.from_dict(self.to_dict())

    # ═══════════════════════════════════════════════
    # Split / Merge
    # ═══════════════════════════════════════════════

    def split_position(
        self, quantities: List[int],
    ) -> List["StrategyPosition"]:
        """شکستن یک موقعیت به چند قطعه."""
        if not self.legs:
            raise ValueError("موقعیت هیچ لگی ندارد")
        if len(self.legs) != 1:
            raise ValueError(
                "فقط موقعیت‌های تک‌لگی قابل شکستن هستند")

        leg = self.legs[0]

        if sum(quantities) != leg.quantity:
            raise ValueError(
                f"مجموع قطعات ({sum(quantities)}) باید "
                f"برابر تعداد کل ({leg.quantity}) باشد")
        if len(quantities) < 2:
            raise ValueError("حداقل 2 قطعه برای Split لازم است")
        if any(q <= 0 for q in quantities):
            raise ValueError("تعداد هر قطعه باید حداقل 1 باشد")

        result: List[StrategyPosition] = []
        for i, qty in enumerate(quantities, 1):
            new_leg = leg.copy()
            new_leg.leg_id = f"{leg.leg_id}-s{i}"
            new_leg.quantity = qty

            new_pos = StrategyPosition.from_dict(self.to_dict())
            new_pos.position_id = f"{self.position_id}-S{i}"
            new_pos.legs = [new_leg]
            new_pos.strategy_type = ""
            new_pos.strategy_name = ""
            new_pos.alert_sent = False
            new_pos.notes = (
                f"{self.notes}\n[Split from {self.position_id}]"
            ).strip()
            result.append(new_pos)

        return result

    @staticmethod
    def merge_positions(
        positions: List["StrategyPosition"],
    ) -> "StrategyPosition":
        """ادغام چند موقعیت در یک موقعیت."""
        if len(positions) < 2:
            raise ValueError("حداقل دو موقعیت برای ادغام لازم است")

        first = positions[0]
        if len(first.legs) != 1:
            raise ValueError(
                f"موقعیت {first.position_id} تک‌لگ نیست")

        first_leg = first.legs[0]

        for p in positions[1:]:
            if len(p.legs) != 1:
                raise ValueError(
                    f"موقعیت {p.position_id} تک‌لگ نیست")
            leg = p.legs[0]
            if leg.symbol != first_leg.symbol:
                raise ValueError(
                    f"نماد {p.position_id} متفاوت است")
            if abs(leg.strike_price - first_leg.strike_price) > 0.5:
                raise ValueError(
                    f"قیمت اعمال {p.position_id} متفاوت است")
            if leg.expiry_date != first_leg.expiry_date:
                raise ValueError(
                    f"تاریخ سررسید {p.position_id} متفاوت است")
            if abs(leg.entry_price - first_leg.entry_price) > 0.5:
                raise ValueError(
                    f"قیمت ورود {p.position_id} متفاوت است")
            if leg.leg_type != first_leg.leg_type:
                raise ValueError(
                    f"جهت {p.position_id} متفاوت است")
            if p.status != first.status:
                raise ValueError(
                    f"وضعیت {p.position_id} متفاوت است")

        total_qty = sum(p.legs[0].quantity for p in positions)

        new_leg = first_leg.copy()
        new_leg.leg_id = f"{first_leg.leg_id}-m"
        new_leg.quantity = total_qty

        new_pos = StrategyPosition.from_dict(first.to_dict())
        new_pos.legs = [new_leg]
        new_pos.strategy_type = ""
        new_pos.strategy_name = ""
        new_pos.alert_sent = False

        sources = ", ".join(p.position_id for p in positions)
        new_pos.notes = (
            f"{first.notes}\n[Merged: {sources}]"
        ).strip()

        return new_pos


# ═══════════════════════════════════════════════════
# صادرات
# ═══════════════════════════════════════════════════

__all__ = [
    "LegType",
    "PositionStatus",
    "OptionLeg",
    "StrategyPosition",
]