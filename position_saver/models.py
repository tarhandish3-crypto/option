# position_saver/models.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from core.enums import OptionType


# =====================================================
# Enumها
# =====================================================

class LegType(Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def label_fa(self) -> str:
        return "خرید" if self == LegType.BUY else "فروش"

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


# =====================================================
# مدل لنگه
# =====================================================

@dataclass
class OptionLeg:
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

    # ---------- فیلدهای نکول ----------
    is_defaulted: bool = False
    default_penalty: float = 0.0
    default_payment: float = 0.0
    settlement_price: float = 0.0

    # ---------- ویژگی‌های مشتق‌شده ----------

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
    def leg_type_label_fa(self) -> str:
        return self.leg_type.label_fa

    @property
    def effective_contract_size(self) -> int:
        if not self.is_option:
            return 1
        return self.contract_size if self.contract_size > 0 else 1000

    # ---------- Serialization ----------

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
            "is_defaulted": self.is_defaulted,
            "default_penalty": self.default_penalty,
            "default_payment": self.default_payment,
            "settlement_price": self.settlement_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptionLeg":
        kind_name = data.get("option_kind")
        if kind_name:
            try:
                option_kind = OptionType[kind_name]
            except KeyError:
                option_kind = cls._infer_option_kind(data.get("symbol", ""))
        else:
            option_kind = cls._infer_option_kind(data.get("symbol", ""))

        is_option = bool(
            data.get("is_option", option_kind != OptionType.STOCK))

        try:
            leg_type = LegType.from_value(data.get("leg_type", "buy"))
        except ValueError:
            leg_type = LegType.BUY

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
            close_price=data.get("close_price"),
            close_fee=float(data.get("close_fee", 0.0)),
            expiry_date=data.get("expiry_date", ""),
            ins_code=str(data.get("ins_code", "")),
            is_defaulted=bool(data.get("is_defaulted", False)),
            default_penalty=float(data.get("default_penalty", 0.0)),
            default_payment=float(data.get("default_payment", 0.0)),
            settlement_price=float(data.get("settlement_price", 0.0)),
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


# =====================================================
# مدل موقعیت
# =====================================================

@dataclass
class StrategyPosition:
    position_id: str = field(
        default_factory=lambda: f"POS-{str(uuid.uuid4())[:6].upper()}")
    strategy_name: str = ""
    broker_name: str = "مفید"
    underlying_symbol: str = ""
    underlying_price: float = 0.0
    execution_date: str = ""
    expiry_date: str = ""
    status: PositionStatus = PositionStatus.OPEN
    legs: List[OptionLeg] = field(default_factory=list)

    target_roi_maturity: float = 0.0
    alert_target_roi: float = 0.0
    alert_sent: bool = False

    close_date: Optional[str] = None
    notes: str = ""

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    @property
    def option_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if leg.is_option]

    @property
    def stock_legs(self) -> List[OptionLeg]:
        return [leg for leg in self.legs if not leg.is_option]

    @property
    def status_label_fa(self) -> str:
        return self.status.label_fa

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "strategy_name": self.strategy_name,
            "broker_name": self.broker_name,
            "underlying_symbol": self.underlying_symbol,
            "underlying_price": self.underlying_price,
            "execution_date": self.execution_date,
            "expiry_date": self.expiry_date,
            "status": self.status.value,
            "target_roi_maturity": self.target_roi_maturity,
            "alert_target_roi": self.alert_target_roi,
            "alert_sent": self.alert_sent,
            "close_date": self.close_date,
            "notes": self.notes,
            "legs": [leg.to_dict() for leg in self.legs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyPosition":
        try:
            status = PositionStatus.from_value(data.get("status", "open"))
        except ValueError:
            status = PositionStatus.OPEN

        return cls(
            position_id=data.get("position_id", ""),
            strategy_name=data.get("strategy_name", ""),
            broker_name=data.get("broker_name", "مفید"),
            underlying_symbol=data.get("underlying_symbol", ""),
            underlying_price=float(data.get("underlying_price", 0.0)),
            execution_date=data.get("execution_date", ""),
            expiry_date=data.get("expiry_date", ""),
            status=status,
            target_roi_maturity=float(data.get("target_roi_maturity", 0.0)),
            alert_target_roi=float(data.get("alert_target_roi", 0.0)),
            alert_sent=bool(data.get("alert_sent", False)),
            close_date=data.get("close_date"),
            notes=data.get("notes", ""),
            legs=[OptionLeg.from_dict(l) for l in data.get("legs", [])],
        )