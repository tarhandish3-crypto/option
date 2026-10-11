# position_saver/importer/schemas.py
# -*- coding: utf-8 -*-

"""
ساختار داده‌های موقت برای ایمپورت اکسل کارگزاری.

این ماژول شامل مدل‌های داده‌ای است که در طول فرایند ایمپورت
استفاده می‌شوند، ولی در فایل `positions_data.json` ذخیره نمی‌شوند.

تفاوت با position_saver/models.py:
    - models.py:    مدل‌های ماندگار (StrategyPosition, OptionLeg)
    - schemas.py:   مدل‌های موقت برای Wizard (TradeRecord, MatchedLot)

نکته طراحی:
    نام schemas.py انتخاب شد تا با models.py تداخل نداشته باشد
    و برنامه‌نویس سریع بفهمد که این‌ها DTO (Data Transfer Objects)
    هستند، نه مدل‌های ماندگار.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core.enums import OptionType
from position_saver.models import LegType


# =====================================================
# TradeRecord — یک ردیف خام از اکسل
# =====================================================

@dataclass
class TradeRecord:
    """
    یک ردیف معامله که از اکسل کارگزاری پارس شده است.

    چرخه‌ی عمر:
        ۱. Parser: پر کردن فیلدهای اصلی از اکسل
        ۲. Enricher: پر کردن strike/expiry/contract_size از Snapshot
        ۳. Wizard: نمایش به کاربر و ویرایش دستی

    فیلدهای کلیدی:
        - trade_id: شناسه‌ی یکتای ردیف (برای ارجاع در OptionLeg)
        - timestamp: datetime میلادی (از تاریخ و ساعت شمسی)
        - side: BUY یا SELL
        - needs_review: اگر strike/expiry خالی باشد True می‌شود
        - is_complete: property که همه‌ی فیلدهای لازم را چک می‌کند
    """

    # ─── از اکسل ───
    trade_id: str = field(
        default_factory=lambda: f"trade_{str(uuid.uuid4())[:6]}")
    timestamp: Optional[datetime] = None
    raw_date: str = ""              # "1405/07/19"
    raw_time: str = ""              # "12:07:43"
    symbol: str = ""                # نرمال‌شده: "ضفزر722"
    side: LegType = LegType.BUY
    quantity: int = 0
    price: float = 0.0
    raw_status: str = ""            # "انجام شده"

    # ─── از Wizard ───
    broker: str = ""                # "مفید"

    # ─── از Snapshot (پس از Enrichment) ───
    strike_price: Optional[float] = None
    expiry_date: str = ""           # "1405/07/26"
    contract_size: int = 0          # پیش‌فرض آپشن: 1000
    option_kind: Optional[OptionType] = None
    underlying_symbol: str = ""     # "فزر"
    ins_code: str = ""              # کد نماد

    # ─── متادیتا ───
    is_selected: bool = True        # انتخاب کاربر در Wizard
    needs_review: bool = False      # اطلاعات ناقص
    user_edited: bool = False       # کاربر دستی ویرایش کرده
    warnings: List[str] = field(default_factory=list)

    # =====================================================
    # Property های مشتق‌شده
    # =====================================================

    @property
    def is_option(self) -> bool:
        """آیا این معامله روی آپشن است؟"""
        if self.option_kind is None:
            # اگر option_kind ست نشده، از پیشوند نماد تشخیص بده
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
    def effective_contract_size(self) -> int:
        """
        اندازه‌ی قرارداد مؤثر:
            - سهم پایه: 1
            - آپشن: contract_size یا 1000 (پیش‌فرض بورس تهران)
        """
        if not self.is_option:
            return 1
        return self.contract_size if self.contract_size > 0 else 1000

    @property
    def is_complete(self) -> bool:
        """
        آیا همه‌ی فیلدهای لازم پر است؟

        قاعده:
            - سهم پایه: فقط symbol لازم است
            - آپشن: symbol + strike_price + expiry_date
        """
        if not self.symbol:
            return False

        # اگر option_kind ست نشده، نمی‌توانیم بگوییم کامل است
        if self.option_kind is None:
            return False

        if self.option_kind == OptionType.STOCK:
            return True

        # آپشن: strike و expiry لازم است
        return (
            self.strike_price is not None
            and self.strike_price > 0
            and bool(self.expiry_date)
        )

    @property
    def is_incomplete(self) -> bool:
        """عکسِ is_complete"""
        return not self.is_complete

    @property
    def datetime_str(self) -> str:
        """نمایش زیبای timestamp"""
        if self.timestamp is None:
            return f"{self.raw_date} {self.raw_time}".strip()
        try:
            return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return f"{self.raw_date} {self.raw_time}".strip()

    @property
    def side_label_fa(self) -> str:
        """نمایش فارسی سمت سفارش"""
        return self.side.label_fa

    # =====================================================
    # محاسبات
    # =====================================================

    def value(self) -> float:
        """
        ارزش کل این معامله (بدون کارمزد).
        = quantity × price × contract_size
        """
        return (
            self.quantity
            * self.price
            * self.effective_contract_size
        )

    def signed_quantity(self) -> int:
        """
        تعداد با علامت:
            +quantity برای BUY
            -quantity برای SELL
        """
        return self.quantity * self.side.side_sign

    def signed_value(self) -> float:
        """
        ارزش با علامت (جریان نقدی خام):
            +value برای SELL (دریافت وجه)
            -value برای BUY  (پرداخت وجه)
        """
        if self.side == LegType.BUY:
            return -self.value()
        return self.value()

    # =====================================================
    # Serialization
    # =====================================================

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "timestamp": (
                self.timestamp.isoformat()
                if self.timestamp else None
            ),
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
            "option_kind": (
                self.option_kind.name
                if self.option_kind else None
            ),
            "underlying_symbol": self.underlying_symbol,
            "ins_code": self.ins_code,
            "is_selected": self.is_selected,
            "needs_review": self.needs_review,
            "user_edited": self.user_edited,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRecord":
        # timestamp
        ts_raw = data.get("timestamp")
        ts = None
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw)
            except Exception:
                ts = None

        # option_kind
        ok_raw = data.get("option_kind")
        option_kind = None
        if ok_raw:
            try:
                option_kind = OptionType[ok_raw]
            except KeyError:
                option_kind = None

        # side
        try:
            side = LegType.from_value(data.get("side", "buy"))
        except ValueError:
            side = LegType.BUY

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
            strike_price=(
                float(data["strike_price"])
                if data.get("strike_price") is not None
                else None
            ),
            expiry_date=data.get("expiry_date", ""),
            contract_size=int(data.get("contract_size", 0)),
            option_kind=option_kind,
            underlying_symbol=data.get("underlying_symbol", ""),
            ins_code=data.get("ins_code", ""),
            is_selected=bool(data.get("is_selected", True)),
            needs_review=bool(data.get("needs_review", False)),
            user_edited=bool(data.get("user_edited", False)),
            warnings=list(data.get("warnings", [])),
        )

    def copy(self) -> "TradeRecord":
        """کپی مستقل"""
        return TradeRecord.from_dict(self.to_dict())

    def copy_with_quantity(self, new_qty: int) -> "TradeRecord":
        """
        کپی با تغییر quantity.
        برای Partial Match در Matcher استفاده می‌شود.
        """
        new_trade = self.copy()
        new_trade.quantity = new_qty
        new_trade.trade_id = f"{self.trade_id}_q{new_qty}"
        return new_trade


# =====================================================
# MatchedLot — جفت BUY-SELL
# =====================================================

@dataclass
class MatchedLot:
    """
    یک lot معاملاتی: یک BUY و اختیاراً یک SELL که آن را بست.

    خروجی FifoMatcher.

    حالت‌ها:
        - is_closed=True:  BUY + SELL (آفست شده)
        - is_open=True:    فقط BUY (موقعیت باز)
    """

    lot_id: str = field(
        default_factory=lambda: f"lot_{str(uuid.uuid4())[:6]}")
    symbol: str = ""
    open_trade: Optional[TradeRecord] = None
    close_trade: Optional[TradeRecord] = None
    realized_pnl: Optional[float] = None

    # =====================================================
    # Property ها
    # =====================================================

    @property
    def is_closed(self) -> bool:
        """آیا lot بسته شده؟"""
        return self.close_trade is not None

    @property
    def is_open(self) -> bool:
        """آیا lot باز است؟"""
        return self.close_trade is None

    @property
    def quantity(self) -> int:
        """تعداد lot (از BUY)"""
        return self.open_trade.quantity if self.open_trade else 0

    @property
    def entry_price(self) -> float:
        """قیمت ورود (BUY)"""
        return self.open_trade.price if self.open_trade else 0.0

    @property
    def close_price(self) -> Optional[float]:
        """قیمت خروج (SELL) — None اگر باز باشد"""
        return self.close_trade.price if self.close_trade else None

    @property
    def entry_value(self) -> float:
        """ارزش ورود کل"""
        if not self.open_trade:
            return 0.0
        return self.open_trade.value()

    @property
    def close_value(self) -> float:
        """ارزش خروج کل — صفر اگر باز باشد"""
        if not self.close_trade:
            return 0.0
        return self.close_trade.value()

    @property
    def open_timestamp(self) -> Optional[datetime]:
        return self.open_trade.timestamp if self.open_trade else None

    @property
    def close_timestamp(self) -> Optional[datetime]:
        return self.close_trade.timestamp if self.close_trade else None

    @property
    def entry_date_jalali(self) -> str:
        """تاریخ ورود شمسی"""
        if not self.open_trade:
            return ""
        return self.open_trade.raw_date

    @property
    def close_date_jalali(self) -> str:
        """تاریخ خروج شمسی"""
        if not self.close_trade:
            return ""
        return self.close_trade.raw_date

    @property
    def option_kind(self) -> Optional[OptionType]:
        """نوع آپشن (از open_trade)"""
        if self.open_trade:
            return self.open_trade.option_kind
        return None

    @property
    def underlying_symbol(self) -> str:
        """نماد پایه"""
        if self.open_trade:
            return self.open_trade.underlying_symbol
        return ""

    # =====================================================
    # محاسبات
    # =====================================================

    def holding_days(self) -> Optional[int]:
        """
        مدت نگه‌داری به روز.
        فقط اگر باز شده باشد (close_timestamp موجود).
        """
        if not self.open_timestamp or not self.close_timestamp:
            return None
        delta = self.close_timestamp - self.open_timestamp
        return delta.days

    def gross_pnl(self) -> Optional[float]:
        """
        سود/زیان خام (بدون کارمزد).
        فقط برای lot های بسته.
        """
        if not self.is_closed:
            return None
        # BUY ارزان + SELL گران = سود
        return self.close_value - self.entry_value

    def compute_realized_pnl(self, calculator=None) -> Optional[float]:
        """
        محاسبه‌ی سود/زیان محقق‌شده با کارمزد.

        Args:
            calculator: PositionPnLCalculator (اختیاری)

        Returns:
            float یا None اگر lot باز باشد
        """
        if not self.is_closed:
            return None

        # ساده: بدون کارمزد
        return self.gross_pnl()

    # =====================================================
    # Serialization
    # =====================================================

    def to_dict(self) -> dict:
        return {
            "lot_id": self.lot_id,
            "symbol": self.symbol,
            "open_trade": (
                self.open_trade.to_dict() if self.open_trade else None
            ),
            "close_trade": (
                self.close_trade.to_dict() if self.close_trade else None
            ),
            "realized_pnl": self.realized_pnl,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MatchedLot":
        open_raw = data.get("open_trade")
        close_raw = data.get("close_trade")

        open_trade = (
            TradeRecord.from_dict(open_raw)
            if open_raw else None
        )
        close_trade = (
            TradeRecord.from_dict(close_raw)
            if close_raw else None
        )

        realized = data.get("realized_pnl")
        if realized is not None:
            try:
                realized = float(realized)
            except (TypeError, ValueError):
                realized = None

        return cls(
            lot_id=data.get("lot_id", ""),
            symbol=data.get("symbol", ""),
            open_trade=open_trade,
            close_trade=close_trade,
            realized_pnl=realized,
        )

    def copy(self) -> "MatchedLot":
        return MatchedLot.from_dict(self.to_dict())


# =====================================================
# ImportSettings — تنظیمات Wizard
# =====================================================

@dataclass
class ImportSettings:
    """
    تنظیمات وارد شده توسط کاربر در Wizard.

    این تنظیمات در مرحله‌ی ۱ Wizard اعمال می‌شوند و
    در ImportEngine.run() استفاده می‌شوند.
    """

    # روش تطبیق BUY-SELL
    match_method: str = "fifo"          # "fifo" | "lifo"

    # پنجره‌ی زمانی گروه‌بندی (ثانیه)
    time_window_seconds: int = 60

    # گروه‌بندی بر اساس نماد پایه
    group_by_underlying: bool = True

    # رفتار با تکراری‌ها
    skip_duplicates: bool = True

    # وضعیت‌های مجاز سفارش
    valid_statuses: List[str] = field(
        default_factory=lambda: ["انجام شده"])

    # حد هشدار پیش‌فرض برای موقعیت‌های جدید
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
            skip_duplicates=bool(
                data.get("skip_duplicates", True)),
            valid_statuses=list(
                data.get("valid_statuses", ["انجام شده"])),
            default_alert_roi=float(
                data.get("default_alert_roi", 10.0)),
        )


# =====================================================
# ImportBatch — یک ایمپورت کامل
# =====================================================

@dataclass
class ImportBatch:
    """
    شناسنامه‌ی یک ایمپورت کامل.

    در `import_batches.json` ذخیره می‌شود و
    برای rollback و audit استفاده می‌شود.
    """

    batch_id: str = field(
        default_factory=lambda: (
            datetime.now().strftime("%Y%m%d-%H%M%S-")
            + str(uuid.uuid4())[:4]
        ))
    broker: str = ""
    source_file: str = ""
    created_at: str = ""                # ISO datetime
    import_date_jalali: str = ""        # "1405/10/21"

    # ─── آمار ───
    n_trades: int = 0
    n_positions_open: int = 0
    n_positions_closed: int = 0
    n_needs_review: int = 0

    # ─── ارجاعات ───
    position_ids: List[str] = field(default_factory=list)

    @property
    def n_positions_total(self) -> int:
        """تعداد کل موقعیت‌های ساخته‌شده"""
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
            position_ids=list(data.get("position_ids", [])),
        )


# =====================================================
# ImportResult — خروجی ImportEngine.run()
# =====================================================

@dataclass
class ImportResult:
    """
    نتیجه‌ی کامل ImportEngine.run().

    این ساختار در Wizard استفاده می‌شود تا:
        - معاملات کامل را در تب «کامل» نشان دهد
        - معاملات ناقص را در تب «ناقص» نشان دهد
        - lot های باز/بسته را برای گروه‌بندی نمایش دهد
    """

    # ─── معاملات ───
    trades: List[TradeRecord] = field(default_factory=list)
    complete_trades: List[TradeRecord] = field(default_factory=list)
    incomplete_trades: List[TradeRecord] = field(default_factory=list)

    # ─── Lot ها ───
    lots: List[MatchedLot] = field(default_factory=list)
    open_lots: List[MatchedLot] = field(default_factory=list)
    closed_lots: List[MatchedLot] = field(default_factory=list)

    # ─── خطاها ───
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # =====================================================
    # Property ها
    # =====================================================

    @property
    def has_incomplete(self) -> bool:
        """آیا معاملات ناقص وجود دارد؟"""
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

    @property
    def all_complete(self) -> bool:
        """آیا همه‌ی معاملات کامل هستند؟"""
        return (
            len(self.incomplete_trades) == 0
            and len(self.trades) > 0
        )

    # =====================================================
    # Summary
    # =====================================================

    def summary_text(self) -> str:
        """خلاصه‌ی متنی برای نمایش در UI"""
        parts = []
        parts.append(f"کل: {self.n_trades}")
        parts.append(f"کامل: {self.n_complete}")
        if self.n_incomplete:
            parts.append(f"ناقص: {self.n_incomplete}")
        parts.append(f"بسته: {self.n_closed_lots}")
        parts.append(f"باز: {self.n_open_lots}")
        return " | ".join(parts)


# =====================================================
# BrokerTemplate — قالب ستون‌های کارگزاری
# =====================================================

@dataclass
class BrokerTemplate:
    """
    نگاشت ستون‌های اکسل یک کارگزاری به فیلدهای TradeRecord.

    برای هر کارگزاری یک قالب ذخیره می‌شود تا در ایمپورت‌های
    بعدی نیازی به تعیین دستی ستون‌ها نباشد.
    """

    broker_name: str = ""
    date_col: str = "تاریخ"
    time_col: str = "ساعت"
    side_col: str = "سمت سفارش"
    symbol_col: str = "نماد"
    qty_col: str = "حجم انجام شده"
    price_col: str = "قیمت"
    status_col: str = "وضعیت"
    valid_statuses: List[str] = field(
        default_factory=lambda: ["انجام شده"])

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
            valid_statuses=list(
                data.get("valid_statuses", ["انجام شده"])),
        )

    def copy(self) -> "BrokerTemplate":
        return BrokerTemplate.from_dict(self.to_dict())


# =====================================================
# صادرات
# =====================================================

__all__ = [
    "TradeRecord",
    "MatchedLot",
    "ImportSettings",
    "ImportBatch",
    "ImportResult",
    "BrokerTemplate",
]