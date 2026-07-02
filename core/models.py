# core/models.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union

from core.enums import ExchangeType, AssetType, OptionType, Side, MarketType, RiskLevel, InvestorProfile
from config import get_price_levels, get_price_steps

# تنظیم logger برای این ماژول
logger = logging.getLogger("OptionScanner.Core.Models")

# =====================================================
# مدل‌های داده‌ای دامنه (Domain Models)
# =====================================================


@dataclass(slots=True)
class UnderlyingAsset:
    """
    مدل داده‌ای دارایی پایه (نماد مادر)
    """
    ticker: str
    name: str
    last_price: float
    close_price: float
    market: ExchangeType = ExchangeType.TSE
    asset_type: AssetType = AssetType.STOCK
    is_frozen: bool = False
    daily_change_pct: float = 0.0
    yesterday_price: float = 0.0

    def __str__(self) -> str:
        return f"UnderlyingAsset(Ticker={self.ticker}, Price={self.last_price:,} IRR)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'last_price': self.last_price,
            'close_price': self.close_price,
            'market': self.market.value if isinstance(self.market, Enum) else self.market,
            'asset_type': self.asset_type.value if isinstance(self.asset_type, Enum) else self.asset_type,
            'is_frozen': self.is_frozen,
            'daily_change_pct': self.daily_change_pct,
            'yesterday_price': self.yesterday_price
        }


@dataclass(slots=True)
class OptionContract:
    """
    مدل داده‌ای یک قرارداد اختیار معامله یا دارایی لگ دارایی پایه در بورس تهران
    """
    # ===== مشخصات پایه =====
    ticker: str                               # نماد قرارداد
    name: str                                 # نام قرارداد
    underlying_ticker: str                    # نماد دارایی پایه
    option_type: OptionType                   # نوع قرارداد (Call/Put/Stock)
    strike_price: float                       # قیمت اعمال
    contract_size: int = 1000                 # اندازه هر قرارداد (تعداد سهام)
    expiry_date: Optional[Union[str, datetime]] = None  # تاریخ سررسید
    days_to_maturity: int = 0                 # روزهای باقی‌مانده تا سررسید

    # ===== اطلاعات تابلو و قیمت =====
    bid: float = 0.0                          # قیمت خرید (Bid)
    ask: float = 0.0                          # قیمت فروش (Ask)
    last_price: float = 0.0                   # آخرین قیمت معامله شده
    close_price: float = 0.0                  # قیمت پایانی جلسه قبل
    underlying_price: float = 0.0             # قیمت لحظه‌ای دارایی پایه
    yesterday_price: float = 0.0              # قیمت دیروز قرارداد

    # ===== حجم و ارزش =====
    volume: int = 0                          # حجم معاملات روز
    open_interest: int = 0                   # تعداد موقعیت‌های باز
    value: float = 0.0                       # ارزش معاملات (ریال)
    bid_volume: int = 0                      # حجم در صف خرید
    ask_volume: int = 0                      # حجم در صف فروش
    initial_margin: float = 0.0              # وجه تضمین اولیه

    # ===== پارامترهای تحلیلی و یونانی‌ها (Greeks) =====
    iv: Optional[float] = None               # نوسان‌پذیری ضمنی
    delta: Optional[float] = None            # دلتا
    gamma: Optional[float] = None            # گاما
    theta: Optional[float] = None            # تتا
    vega: Optional[float] = None             # وگا
    rho: Optional[float] = None              # رو
    implied_volatility: Optional[float] = None  # نوسان ضمنی (از مدل BSM)
    iv_hv_ratio: float = 1.0                 # نسبت نوسان ضمنی به تاریخی

    # ===== کدهای داخلی سازمان بورس =====
    instrument_code: str = ""                # کد ابزار
    instrument_code_ua: str = ""             # کد ابزار دارایی پایه

    def __post_init__(self):
        """اعتبارسنجی و بهسازی داده‌های کثیف بازار در زمان لود"""
        if self.days_to_maturity < 0:
            logger.debug(
                f"روزهای سررسید منفی برای قرارداد {self.ticker} اصلاح شد.")
            self.days_to_maturity = 0

    def __str__(self) -> str:
        return f"OptionContract(Ticker={self.ticker}, Strike={self.strike_price:,}, DTE={self.days_to_maturity})"

    @property
    def intrinsic_value(self) -> float:
        """ارزش ذاتی (Intrinsic Value)"""
        if self.option_type == OptionType.STOCK:
            return 0.0
        if self.option_type == OptionType.CALL:
            return max(0.0, self.underlying_price - self.strike_price)
        else:
            return max(0.0, self.strike_price - self.underlying_price)

    @property
    def time_value(self) -> float:
        """ارزش زمانی = آخرین قیمت - ارزش ذاتی"""
        if self.option_type == OptionType.STOCK:
            return 0.0
        return max(0.0, self.last_price - self.intrinsic_value)

    @property
    def mid_price(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last_price

    @property
    def spread_pct(self) -> float:
        if self.bid <= 0 or self.ask <= 0:
            return 1.0
        mid = self.mid_price
        if mid <= 0:
            return 1.0
        return (self.ask - self.bid) / mid

    @property
    def moneyness(self) -> float:
        if self.option_type == OptionType.STOCK:
            return 1.0
        if self.strike_price <= 0 or self.underlying_price <= 0:
            return 1.0
        if self.option_type == OptionType.CALL:
            return self.underlying_price / self.strike_price
        else:
            return self.strike_price / self.underlying_price

    @property
    def option_status(self) -> str:
        if self.option_type == OptionType.STOCK:
            return "ATM"
        if self.strike_price <= 0 or self.underlying_price <= 0:
            return "OTM"
        distance_pct = abs(self.underlying_price -
                           self.strike_price) / self.strike_price
        if distance_pct <= 0.01:
            return "ATM"
        if self.option_type == OptionType.CALL:
            return "ITM" if self.underlying_price > self.strike_price else "OTM"
        else:
            return "ITM" if self.underlying_price < self.strike_price else "OTM"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'underlying_ticker': self.underlying_ticker,
            'option_type': self.option_type.value if isinstance(self.option_type, Enum) else self.option_type,
            'strike_price': self.strike_price,
            'contract_size': self.contract_size,
            'days_to_maturity': self.days_to_maturity,
            'bid': self.bid,
            'ask': self.ask,
            'last_price': self.last_price,
            'underlying_price': self.underlying_price,
            'volume': self.volume,
            'open_interest': self.open_interest,
            'iv': self.iv,
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega
        }


# =====================================================
# مدل‌های خروجی اسکن و تصمیم‌یار (DSS)
# =====================================================

@dataclass(slots=True)
class StrategyClassification:
    """برچسب‌های رفتاری، سناریوی بازار و ماهیت استراتژی برای سیستم تصمیم‌یار"""
    market_type: str = MarketType.NEUTRAL.value
    investor_profile: str = InvestorProfile.BALANCED.value
    risk_level: str = RiskLevel.MEDIUM.value
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'market_type': self.market_type,
            'investor_profile': self.investor_profile,
            'risk_level': self.risk_level,
            'description': self.description
        }


@dataclass(slots=True)
class ProfileScores:
    """ساختار متمرکز امتیازدهی موازی متناسب با مشخصات رفتاری سرمایه‌گذاران مختلف"""
    conservative: float = 0.0
    balanced: float = 0.0
    aggressive: float = 0.0
    income: float = 0.0
    volatility: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            'conservative': self.conservative,
            'balanced': self.balanced,
            'aggressive': self.aggressive,
            'income': self.income,
            'volatility': self.volatility
        }


# =====================================================
# ✅ اصلاح گام ۲ مانیفست: ایجاد کلاس مستقل الگوی لگ‌ها
# =====================================================
@dataclass(slots=True)
class StrategyLegPattern:
    """
    نماینده الگوی تئوریک یک لگ در تعریف استراتژی (Strategy Template)
    """
    option_type: OptionType  # CALL, PUT, STOCK
    side: Side = Side.BUY
    ratio: int = 1
    strike_group: Optional[str] = None     # "K1", "K2", ...
    maturity_group: Optional[str] = None   # "M1", "M2", ...

    @property
    def weight(self) -> float:
        return float(self.ratio if self.side == Side.BUY else -self.ratio)


# =====================================================
# ✅ اصلاح گام ۳ مانیفست: ساده‌سازی لگ موقعیت واقعی
# =====================================================
@dataclass(slots=True)
class LegDefinition:
    """تعریف یک لگ معاملاتی عینی و پر شده با قرارداد واقعی بازار (Position Leg)"""
    side: Side = Side.BUY
    ratio: int = 1
    contract: Optional[OptionContract] = None
    # قیمت ورود (mid_price یا last_price در زمان ساخت لگ)
    entry_price: float = 0.0

    def __post_init__(self):
        # اعتبارسنجی نسبت‌های وزنی
        if self.ratio <= 0:
            raise ValueError(
                f"نسبت وزنی (Ratio) در لگ باید یک عدد مثبت بزرگتر از صفر باشد.")

        if self.entry_price < 0:
            raise ValueError(
                f"قیمت ورود (entry_price) نمی‌تواند منفی باشد: {self.entry_price}")

        if self.contract is not None:
            if not hasattr(self.contract, 'option_type'):
                raise ValueError("آبجکت متصل شده به لگ یک قرارداد معتبر نیست.")

    @property
    def option_type(self) -> Optional[OptionType]:
        """واکشی پویا و زنده نوع اختیار یا دارایی از قرارداد متصل"""
        if self.contract is None:
            return None
        return self.contract.option_type

    @property
    def is_stock_leg(self) -> bool:
        """تشخیص خودکار سهم پایه بدون نیاز به فلگ صلب فیلدها"""
        return self.option_type == OptionType.STOCK

    @property
    def weight(self) -> float:
        return float(self.ratio if self.side == Side.BUY else -self.ratio)

    def __str__(self) -> str:
        symbol = self.contract.ticker if self.contract else "Unknown"
        return f"Leg({self.side.value} {self.ratio}x {symbol})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'side': self.side.value if isinstance(self.side, Enum) else self.side,
            'ratio': self.ratio,
            'is_stock_leg': self.is_stock_leg,
            'option_type': self.option_type.value if self.option_type else None,
            'contract': self.contract.to_dict() if self.contract else None
        }


@dataclass(slots=True)
class Opportunity:
    """
    مدل جامع یک موقعیت معاملاتی کشف شده.
    """
    strategy_name: str
    underlying_ticker: str
    legs: List[LegDefinition]
    S0_stock: float = 0.0
    days_to_maturity: int = 0

    # ===== معیارهای مالی =====
    net_premium: float = 0.0
    pop: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    break_even_points: List[float] = field(default_factory=list)

    # اضافه شدن فیلد رسمی برای منحنی بازدهی درصدی جهت دسترسی سریع لایه فیلترها
    returns_monthly_pct: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=float))

    # ===== معیارهای سرمایه =====
    required_margin: float = 0.0
    total_premium: float = 0.0

    # ===== معیارهای نسبت‌ها =====
    risk_reward_ratio: float = 0.0
    expected_return_pct: float = 0.0
    max_profit_pct: float = 0.0
    max_loss_pct: float = 0.0

    # ===== معیارهای اجرا و نقدشوندگی =====
    liquidity_score: float = 0.0
    execution_score: float = 0.0

    # ===== سیستم امتیازدهی و کلاس‌بندی چندبعدی (DSS) =====
    classification: StrategyClassification = field(
        default_factory=StrategyClassification)
    profile_scores: ProfileScores = field(default_factory=ProfileScores)

    # ===== امتیاز نهایی و رتبه‌بندی عمومی =====
    final_score: float = 0.0
    rank: int = 0

    # ===== اطلاعات تکمیلی =====
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.days_to_maturity < 0:
            logger.warning(
                f"روزهای سررسید منفی برای فرصت {self.underlying_ticker} به صفر اصلاح شد.")
            self.days_to_maturity = 0

    def __str__(self) -> str:
        return (f"✨ Opportunity(Strategy={self.strategy_name}, Ticker={self.underlying_ticker}, "
                f"DTE={self.days_to_maturity}, Score={self.final_score:.2f}, Rank={self.rank})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategy_name': self.strategy_name,
            'underlying_ticker': self.underlying_ticker,
            'days_to_maturity': self.days_to_maturity,
            'net_premium': self.net_premium,
            'max_profit': self.max_profit,
            'max_loss': self.max_loss,
            'break_even_points': self.break_even_points,
            'required_margin': self.required_margin,
            'risk_reward_ratio': self.risk_reward_ratio,
            'expected_return_pct': self.expected_return_pct,
            'liquidity_score': self.liquidity_score,
            'classification': self.classification.to_dict(),
            'profile_scores': self.profile_scores.to_dict(),
            'final_score': self.final_score,
            'rank': self.rank,
            'timestamp': self.timestamp.isoformat(),
            'legs': [leg.to_dict() for leg in self.legs]}


@dataclass(slots=True)
class ScanResult:
    """مدل نهایی خروجی یک دور اسکن کامل بازار"""

    timestamp: datetime = field(default_factory=datetime.now)
    total_strategies_scanned: int = 0
    total_combinations_generated: int = 0
    total_combinations_filtered: int = 0
    opportunities: List[Opportunity] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dataframe(self) -> pd.DataFrame:
        if not self.opportunities:
            return pd.DataFrame()

        records = []
        for opp in self.opportunities:
            record = {
                'Strategy': opp.strategy_name,
                'Ticker': opp.underlying_ticker,
                'DaysToMaturity': opp.days_to_maturity,
                'MarketType': opp.classification.market_type,
                'InvestorProfile': opp.classification.investor_profile,
                'RiskLevel': opp.classification.risk_level,
                'NetPremium': round(opp.net_premium, 2),
                'MaxProfit': round(opp.max_profit, 2),
                'MaxLoss': round(opp.max_loss, 2),
                'RiskReward': round(opp.risk_reward_ratio, 2),
                'ExpectedReturn': round(opp.expected_return_pct, 2),
                'MaxProfitPct': round(opp.max_profit_pct, 2),
                'MaxLossPct': round(opp.max_loss_pct, 2),
                'Margin': round(opp.required_margin, 2),
                'LiquidityScore': round(opp.liquidity_score, 2),
                'FinalScore': round(opp.final_score, 2),
                'Rank': opp.rank,
                'Description': opp.classification.description,
                'Timestamp': opp.timestamp}
            for i, leg in enumerate(opp.legs, 1):
                if leg.contract:
                    record[f'Leg{i}_Symbol'] = leg.contract.ticker
                    record[f'Leg{i}_Side'] = leg.side.value if isinstance(
                        leg.side, Enum) else leg.side
                    record[f'Leg{i}_Ratio'] = leg.ratio
            records.append(record)

        df = pd.DataFrame(records)
        if 'Rank' in df.columns:
            df = df.sort_values('Rank')
        return df


# =====================================================
# مدل تصویر لحظه‌ای بازار (Market Snapshot)
# =====================================================

@dataclass(slots=True)
class MarketSnapshot:
    """تصویر لحظه‌ای از کل زنجیره بازار آپشن و دارایی‌های پایه بورس ایران"""

    timestamp: datetime = field(default_factory=datetime.now)
    underlying_assets: Dict[str, UnderlyingAsset] = field(default_factory=dict)
    option_contracts: List[OptionContract] = field(default_factory=list)
    risk_free_rate: float = 0.24

    # کش‌های داخلی سریع
    _options_by_underlying: Dict[str, List[OptionContract]] = field(
        default_factory=dict, repr=False)
    _options_by_symbol: Dict[str, OptionContract] = field(
        default_factory=dict, repr=False)
    _indices_built: bool = field(default=False, repr=False)

    # سطوح قیمتی متمرکز (جدید)
    price_levels: Optional[np.ndarray] = None
    pct_steps: Optional[np.ndarray] = None

    def __post_init__(self):
        self.sync_underlying_prices()
        self.build_indices()
        # تولید یکبار سطوح قیمتی
        if self.price_levels is None:
            self.price_levels = get_price_levels(10000.0)  # S0 پیش‌فرض
            self.pct_steps = get_price_steps()

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> MarketSnapshot:
        if df.empty:
            logger.warning("انتقال دیتای خالی به قالب DataFrame.")
            return cls()

        underlying_assets = cls._extract_underlyings(df)
        option_contracts = []
        skipped_rows = 0

        raw_records = df.to_dict(orient='records')
        for row in raw_records:
            try:
                contract = cls._row_to_option_contract_from_dict(row)
                if contract.ticker:
                    option_contracts.append(contract)
                else:
                    skipped_rows += 1
            except Exception as e:
                logger.debug(f"خطا در پارس سطر: {e}")
                skipped_rows += 1
                continue

        if skipped_rows > 0:
            logger.info(
                f"تعداد {skipped_rows} سطر در فرآیند نگاشت فیلتر شدند.")

        return cls(
            timestamp=datetime.now(),
            underlying_assets=underlying_assets,
            option_contracts=option_contracts)

    @classmethod
    def _extract_underlyings(cls, df: pd.DataFrame) -> Dict[str, UnderlyingAsset]:
        underlyings = {}
        for ticker, group in df.groupby('UnderlyingTicker'):
            if pd.isna(ticker) or ticker == '':
                continue

            ticker_str = str(ticker)
            underlying_price = cls._clean_float(
                group['UnderlyingPrice'].iloc[0])

            name = str(group['Name'].iloc[0])

            market = ExchangeType.TSE
            if 'Market' in group.columns and pd.notna(group['Market'].iloc[0]):
                market_str = str(group['Market'].iloc[0]).lower()
                if market_str in ['ifb', 'فرابورس']:
                    market = ExchangeType.IFB

            asset_type = AssetType.STOCK
            if 'IsETF' in group.columns and pd.notna(group['IsETF'].iloc[0]):
                if bool(group['IsETF'].iloc[0]):
                    asset_type = AssetType.ETF_STOCK

            underlyings[ticker_str] = UnderlyingAsset(
                ticker=ticker_str, name=name, last_price=underlying_price,
                close_price=underlying_price, market=market, asset_type=asset_type,
                yesterday_price=underlying_price)
        return underlyings

    @classmethod
    def _row_to_option_contract_from_dict(cls, row: pd.Series) -> OptionContract:

        return OptionContract(
            ticker=str(row.get('Ticker', '')),
            name=str(row.get('Name', '')),
            underlying_ticker=str(row.get('UnderlyingTicker', '')),
            option_type=row['Type'],
            strike_price=cls._clean_float(row.get('StrikePrice')),
            contract_size=int(row.get('ContractSize', 1000)) if pd.notna(
                row.get('ContractSize')) else 1000,
            expiry_date=row.get('MaturityDate') if pd.notna(
                row.get('MaturityDate')) else None,
            days_to_maturity=int(row.get('DaysToMaturity', 0)) if pd.notna(
                row.get('DaysToMaturity')) else 0,
            bid=cls._clean_float(row.get('BidPrice')),
            ask=cls._clean_float(row.get('AskPrice')),
            last_price=cls._clean_float(row.get('LastPrice')),
            close_price=cls._clean_float(row.get('ClosePrice')),
            underlying_price=cls._clean_float(row.get('UnderlyingPrice')),
            yesterday_price=cls._clean_float(row.get('ClosePrice')),
            volume=int(row.get('Volume', 0)) if pd.notna(
                row.get('Volume')) else 0,
            open_interest=int(row.get('OpenPositions', 0)) if pd.notna(
                row.get('OpenPositions')) else 0,
            value=cls._clean_float(row.get('Value')),
            bid_volume=int(row.get('BidVolume', 0)) if pd.notna(
                row.get('BidVolume')) else 0,
            ask_volume=int(row.get('AskVolume', 0)) if pd.notna(
                row.get('AskVolume')) else 0,
            iv=cls._clean_float_or_none(row.get('IV')),
            delta=cls._clean_float_or_none(row.get('Delta')),
            gamma=cls._clean_float_or_none(row.get('Gamma')),
            theta=cls._clean_float_or_none(row.get('Theta')),
            vega=cls._clean_float_or_none(row.get('Vega')),
            rho=cls._clean_float_or_none(row.get('Rho')),
            implied_volatility=cls._clean_float_or_none(row.get('BS_Price')),
            instrument_code=str(row.get('InstrumentCode', '')),
            instrument_code_ua=str(row.get('InstrumentCode-UA', '')))

    @staticmethod
    def _clean_float(val) -> float:
        if pd.isna(val) or val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _clean_float_or_none(val) -> Optional[float]:
        if pd.isna(val) or val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def sync_underlying_prices(self) -> None:
        for opt in self.option_contracts:
            if not opt.underlying_ticker:
                continue
            underlying = self.get_underlying(opt.underlying_ticker)
            if underlying:
                opt.underlying_price = underlying.last_price

    def build_indices(self) -> None:
        self._options_by_underlying.clear()
        self._options_by_symbol.clear()

        for opt in self.option_contracts:
            if not opt.underlying_ticker:
                continue

            if opt.underlying_ticker not in self._options_by_underlying:
                self._options_by_underlying[opt.underlying_ticker] = []
            self._options_by_underlying[opt.underlying_ticker].append(opt)

            if opt.ticker:
                self._options_by_symbol[opt.ticker] = opt

        self._indices_built = True

    def get_options(self, underlying_ticker: str) -> List[OptionContract]:
        if not self._indices_built:
            self.build_indices()
        return self._options_by_underlying.get(underlying_ticker, [])

    def get_option(self, symbol: str) -> Optional[OptionContract]:
        if not self._indices_built:
            self.build_indices()
        return self._options_by_symbol.get(symbol)

    def get_underlying(self, ticker: str) -> Optional[UnderlyingAsset]:
        return self.underlying_assets.get(ticker)

    def refresh(self) -> None:
        self.sync_underlying_prices()
        self.build_indices()

    def summary(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'total_underlyings': len(self.underlying_assets),
            'total_options': len(self.option_contracts),
            'risk_free_rate': self.risk_free_rate,
            'underlyings_list': list(self.underlying_assets.keys()),
            'options_by_underlying': {ticker: len(opts) for ticker, opts in self._options_by_underlying.items()}
        }
