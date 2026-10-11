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


# =====================================================
# توابع کمکی: کار با تاریخ و زمان
# =====================================================

def _parse_jalali_date(date_str: str) -> Optional[jdatetime.date]:
    """
    تبدیل رشته تاریخ شمسی به jdatetime.date.
    پشتیبانی از فرمت‌های: 1403/01/15، 1403-01-15، 1403/1/15
    """
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


def _normalize_jalali_date(date_str: str) -> str:
    """
    نرمال‌سازی رشته تاریخ شمسی به فرمت YYYY/MM/DD.
    اگر نامعتبر بود، رشته اصلی برگردانده می‌شود.
    """
    if not date_str:
        return ""
    parsed = _parse_jalali_date(date_str)
    if parsed is None:
        return str(date_str).strip()
    return parsed.strftime("%Y/%m/%d")


def _normalize_time_str(time_str: str) -> str:
    """
    نرمال‌سازی رشته زمان به فرمت HH:MM:SS.
    ورودی‌های ممکن: "9:25", "09:25:34", "09:25:34.000"
    """
    if not time_str:
        return ""
    try:
        s = str(time_str).strip()
        # اگر شامل نقطه بود (میلی‌ثانیه)، حذف کن
        if '.' in s:
            s = s.split('.')[0]
        parts = s.split(':')
        if len(parts) < 2:
            return s
        h = int(parts[0])
        m = int(parts[1])
        sec = int(parts[2]) if len(parts) >= 3 else 0
        return f"{h:02d}:{m:02d}:{sec:02d}"
    except Exception:
        return str(time_str).strip()


# =====================================================
# Enumها
# =====================================================

class LegType(Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def label_fa(self) -> str:
        return "خرید" if self == LegType.BUY else "فروش"

    @property
    def side_sign(self) -> int:
        """علامت جهت: 1 برای خرید، -1 برای فروش"""
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
        """آیا وضعیت نهایی است؟ (دیگر قابل تغییر نیست)"""
        return self != PositionStatus.OPEN

    @property
    def is_default(self) -> bool:
        """آیا مربوط به نکول است؟"""
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


# =====================================================
# مدل لنگه
# =====================================================

@dataclass
class OptionLeg:
    """
    یک لنگه معاملاتی (خرید/فروش آپشن یا سهم پایه).

    نکات مهم:
        - contract_size از بازار خوانده می‌شود و صرفاً مقدار اولیه اینجاست.
        - close_price اگر None باشد، یعنی لگ هنوز بسته نشده.
        - entry_fee و close_fee باید هنگام ثبت/بستن ذخیره شوند
          (نه بازمحاسبه با نرخ امروز).

    فیلدهای Import:
        - source: منبع لگ — "manual" یا "excel_import"
        - needs_review: اگر strike/expiry ناقص باشد True
        - trade_ref: شناسه ردیف اکسل BUY که این لگ از آن آمده
        - close_trade_ref: شناسه ردیف اکسل SELL که این را بست
        - realized_pnl: سود/زیان محقق‌شده‌ی همین لگ (اگر بسته شده)
    """
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

    # ---------- تاریخ و زمان ----------
    open_date: str = ""       # تاریخ باز شدن لگ (YYYY/MM/DD)
    open_time: str = ""       # زمان باز شدن لگ (HH:MM:SS)
    close_date: str = ""      # تاریخ بسته شدن لگ
    close_time: str = ""      # زمان بسته شدن لگ
    trade_time: str = ""      # زمان معامله در اکسل (HH:MM:SS)

    # ---------- فیلدهای نکول ----------
    is_defaulted: bool = False
    default_penalty: float = 0.0
    default_payment: float = 0.0
    settlement_price: float = 0.0

    # ---------- فیلدهای Import ----------
    source: str = "manual"                # "manual" | "excel_import"
    needs_review: bool = False            # اطلاعات ناقص (strike/expiry)
    trade_ref: str = ""                   # شناسه ردیف اکسل
    close_trade_ref: str = ""             # شناسه ردیف SELL که این را بست
    realized_pnl: Optional[float] = None  # سود/زیان محقق‌شده‌ی همین لگ

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
        """اندازه قرارداد واقعی: ۱ برای سهام، contract_size برای آپشن"""
        if not self.is_option:
            return 1
        return self.contract_size if self.contract_size > 0 else 1000

    @property
    def is_closed(self) -> bool:
        """آیا لگ بسته شده است؟"""
        return self.close_price is not None

    @property
    def total_shares(self) -> int:
        """تعداد کل سهم (quantity × contract_size)"""
        return self.quantity * self.effective_contract_size

    @property
    def direction_sign(self) -> int:
        """علامت جهت: 1 برای خرید، -1 برای فروش"""
        return self.leg_type.side_sign

    @property
    def is_imported(self) -> bool:
        """آیا این لگ از ایمپورت اکسل آمده؟"""
        return self.source == "excel_import"

    # ---------- محاسبات کمکی ----------

    def entry_value(self) -> float:
        """ارزش ورود کل (بدون کارمزد)"""
        return self.quantity * self.entry_price * self.effective_contract_size

    def close_value(self) -> float:
        """ارزش خروج کل (بدون کارمزد) - اگر بسته نشده، صفر"""
        if self.close_price is None:
            return 0.0
        return self.quantity * self.close_price * self.effective_contract_size

    def current_value(self) -> float:
        """ارزش لحظه‌ای کل (بدون کارمزد)"""
        price = self.current_price if self.current_price > 0 \
            else self.entry_price
        return self.quantity * price * self.effective_contract_size

    def cash_flow_at_open(self) -> float:
        """
        جریان نقدی در لحظه باز شدن لگ.
        مثبت = دریافت نقدی، منفی = پرداخت نقدی.
        """
        val = self.entry_value()
        fee = self.entry_fee if self.entry_fee > 0 else 0.0

        if self.leg_type == LegType.BUY:
            # خرید: پرداخت ارزش + کارمزد
            return -(val + fee)
        else:
            # فروش: دریافت ارزش - کارمزد
            return val - fee

    def is_complete(self) -> bool:
        """
        آیا همه‌ی فیلدهای لازم پر است؟
        برای Wizard Import استفاده می‌شود.
        """
        if self.is_stock:
            return bool(self.symbol)
        return (
            bool(self.symbol)
            and self.strike_price > 0
            and bool(self.expiry_date)
        )

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
            # تاریخ و زمان
            "open_date": self.open_date,
            "open_time": self.open_time,
            "close_date": self.close_date,
            "close_time": self.close_time,
            "trade_time": self.trade_time,
            # نکول
            "is_defaulted": self.is_defaulted,
            "default_penalty": self.default_penalty,
            "default_payment": self.default_payment,
            "settlement_price": self.settlement_price,
            # Import
            "source": self.source,
            "needs_review": self.needs_review,
            "trade_ref": self.trade_ref,
            "close_trade_ref": self.close_trade_ref,
            "realized_pnl": self.realized_pnl,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptionLeg":
        # option_kind
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

        # leg_type
        try:
            leg_type = LegType.from_value(data.get("leg_type", "buy"))
        except ValueError:
            leg_type = LegType.BUY

        # realized_pnl (Optional[float])
        realized_pnl_raw = data.get("realized_pnl")
        realized_pnl = None
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
            close_price=data.get("close_price"),
            close_fee=float(data.get("close_fee", 0.0)),
            expiry_date=str(data.get("expiry_date", "")),
            ins_code=str(data.get("ins_code", "")),
            # تاریخ و زمان
            open_date=str(data.get("open_date", "")),
            open_time=str(data.get("open_time", "")),
            close_date=str(data.get("close_date", "")),
            close_time=str(data.get("close_time", "")),
            trade_time=str(data.get("trade_time", "")),
            # نکول
            is_defaulted=bool(data.get("is_defaulted", False)),
            default_penalty=float(data.get("default_penalty", 0.0)),
            default_payment=float(data.get("default_payment", 0.0)),
            settlement_price=float(data.get("settlement_price", 0.0)),
            # Import
            source=str(data.get("source", "manual")),
            needs_review=bool(data.get("needs_review", False)),
            trade_ref=str(data.get("trade_ref", "")),
            close_trade_ref=str(data.get("close_trade_ref", "")),
            realized_pnl=realized_pnl,
        )

    @staticmethod
    def _infer_option_kind(symbol: str) -> OptionType:
        """حدس نوع اختیار از روی نام نماد"""
        s = str(symbol).strip()
        if not s:
            return OptionType.STOCK
        if s.startswith("ض"):
            return OptionType.CALL
        if s.startswith("ط"):
            return OptionType.PUT
        return OptionType.STOCK

    def copy(self) -> "OptionLeg":
        """
        کپی مستقل از لگ (برای حفظ فیلدها در ویرایش).
        از dataclass استفاده می‌کند تا همه فیلدها کپی شوند.
        """
        return OptionLeg.from_dict(self.to_dict())


# =====================================================
# مدل موقعیت
# =====================================================

@dataclass
class StrategyPosition:
    """
    یک موقعیت استراتژی چندلنگه‌ای.

    نکات:
        - underlying_price از آخرین snapshot بروزرسانی می‌شود.
        - alert_sent پس از ارسال هشدار True می‌شود.
        - target_roi_maturity هدف سود تا سررسید است (اختیاری).

    فیلدهای Import:
        - source: منبع موقعیت — "manual" یا "excel_import"
        - import_batch_id: شناسه یکتای batch ایمپورت
        - needs_review: اگر حداقل یک لگ ناقص باشد True
        - cash_settlement_amount: مبلغ تسویه نقدی (برای وضعیت CASH_SETTLED)
        - underlying_price_at_close: قیمت پایانی سهم پایه در لحظه بستن
    """
    position_id: str = field(
        default_factory=lambda: f"POS-{str(uuid.uuid4())[:6].upper()}")
    strategy_name: str = ""
    broker_name: str = "مفید"
    underlying_symbol: str = ""
    underlying_price: float = 0.0
    underlying_price_at_close: float = 0.0
    execution_date: str = ""
    expiry_date: str = ""
    status: PositionStatus = PositionStatus.OPEN
    legs: List[OptionLeg] = field(default_factory=list)

    target_roi_maturity: float = 0.0
    alert_target_roi: float = 0.0
    alert_sent: bool = False

    close_date: Optional[str] = None
    notes: str = ""

    # ---------- فیلدهای Import ----------
    source: str = "manual"                # "manual" | "excel_import"
    import_batch_id: str = ""             # شناسه یکتای batch
    needs_review: bool = False            # اگر لگ ناقص دارد
    cash_settlement_amount: float = 0.0   # برای CASH_SETTLED

    # ---------- ویژگی‌های مشتق‌شده ----------

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
    def status_label_fa(self) -> str:
        return self.status.label_fa

    @property
    def has_default(self) -> bool:
        """آیا موقعیت نکول دارد؟"""
        return self.status.is_default or any(
            l.is_defaulted for l in self.legs)

    @property
    def total_legs(self) -> int:
        return len(self.legs)

    @property
    def is_imported(self) -> bool:
        """آیا این موقعیت از ایمپورت اکسل آمده؟"""
        return self.source == "excel_import"

    @property
    def has_incomplete_legs(self) -> bool:
        """آیا حداقل یک لگ ناقص دارد؟"""
        return any(leg.needs_review for leg in self.legs)

    # ---------- محاسبات کمکی ----------

    def days_to_expiry(self) -> Optional[int]:
        """تعداد روزهای باقی‌مانده تا سررسید"""
        expiry = _parse_jalali_date(self.expiry_date)
        if expiry is None:
            return None
        today = jdatetime.date.today()
        return (expiry - today).days

    def is_expired(self) -> bool:
        """آیا سررسید گذشته است؟"""
        days = self.days_to_expiry()
        return days is not None and days < 0

    def has_any_close_price(self) -> bool:
        """آیا حداقل یک لگ close_price دارد؟"""
        return any(l.close_price is not None for l in self.legs)

    def all_legs_closed(self) -> bool:
        """آیا همه لگ‌ها بسته شده‌اند؟"""
        return all(l.close_price is not None for l in self.legs)

    # ---------- Serialization ----------

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "strategy_name": self.strategy_name,
            "broker_name": self.broker_name,
            "underlying_symbol": self.underlying_symbol,
            "underlying_price": self.underlying_price,
            "underlying_price_at_close": self.underlying_price_at_close,
            "execution_date": self.execution_date,
            "expiry_date": self.expiry_date,
            "status": self.status.value,
            "target_roi_maturity": self.target_roi_maturity,
            "alert_target_roi": self.alert_target_roi,
            "alert_sent": self.alert_sent,
            "close_date": self.close_date,
            "notes": self.notes,
            # Import
            "source": self.source,
            "import_batch_id": self.import_batch_id,
            "needs_review": self.needs_review,
            "cash_settlement_amount": self.cash_settlement_amount,
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
            underlying_price_at_close=float(
                data.get("underlying_price_at_close", 0.0)),
            execution_date=str(data.get("execution_date", "")),
            expiry_date=str(data.get("expiry_date", "")),
            status=status,
            target_roi_maturity=float(data.get("target_roi_maturity", 0.0)),
            alert_target_roi=float(data.get("alert_target_roi", 0.0)),
            alert_sent=bool(data.get("alert_sent", False)),
            close_date=data.get("close_date"),
            notes=data.get("notes", ""),
            # Import
            source=str(data.get("source", "manual")),
            import_batch_id=str(data.get("import_batch_id", "")),
            needs_review=bool(data.get("needs_review", False)),
            cash_settlement_amount=float(
                data.get("cash_settlement_amount", 0.0)),
            legs=[OptionLeg.from_dict(l) for l in data.get("legs", [])],
        )

    def copy(self) -> "StrategyPosition":
        """کپی مستقل از موقعیت"""
        return StrategyPosition.from_dict(self.to_dict())