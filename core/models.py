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
    """مدل داده‌ای دارایی پایه (نماد مادر)"""
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
    """مدل داده‌ای یک قرارداد اختیار معامله یا دارایی لگ دارایی پایه در بورس تهران"""
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
    volume: int = 0                           # حجم معاملات روز
    open_interest: int = 0                    # تعداد موقعیت‌های باز
    value: float = 0.0                        # ارزش معاملات (ریال)
    bid_volume: int = 0                       # حجم در صف خرید
    ask_volume: int = 0                       # حجم در صف فروش
    initial_margin: float = 0.0               # وجه تضمین اولیه

    # ===== پارامترهای تحلیلی و یونانی‌ها (Greeks) =====
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    iv_hv_ratio: float = 1.0

    # ===== کدهای داخلی سازمان بورس =====
    # کد ابزار (شناسه یکتای سجام/بورس)
    instrument_code: str = ""
    instrument_code_ua: str = ""              # کد ابزار دارایی پایه

    def __post_init__(self):
        if self.days_to_maturity < 0:
            self.days_to_maturity = 0

    @property
    def intrinsic_value(self) -> float:
        if self.option_type == OptionType.STOCK:
            return 0.0
        if self.option_type == OptionType.CALL:
            return max(0.0, self.underlying_price - self.strike_price)
        else:
            return max(0.0, self.strike_price - self.underlying_price)

    @property
    def time_value(self) -> float:
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
        return (self.ask - self.bid) / mid if mid > 0 else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker, 'name': self.name, 'underlying_ticker': self.underlying_ticker,
            'option_type': self.option_type.value if isinstance(self.option_type, Enum) else self.option_type,
            'strike_price': self.strike_price, 'contract_size': self.contract_size,
            'days_to_maturity': self.days_to_maturity, 'bid': self.bid, 'ask': self.ask,
            'last_price': self.last_price, 'underlying_price': self.underlying_price, 'volume': self.volume,
            'open_interest': self.open_interest, 'iv': self.iv, 'delta': self.delta, 'instrument_code': self.instrument_code
        }


@dataclass(slots=True)
class LegDefinition:
    """تعریف یک لگ معاملاتی عینی و پر شده با قرارداد واقعی بازار (Position Leg)"""
    side: Side = Side.BUY
    ratio: int = 1
    contract: Optional[OptionContract] = None
    entry_price: float = 0.0

    def __post_init__(self):
        if self.ratio <= 0:
            raise ValueError("نسبت وزنی (Ratio) در لگ باید یک عدد مثبت باشد.")
        if self.entry_price < 0:
            raise ValueError("قیمت ورود نمی‌تواند منفی باشد.")

    @property
    def weight(self) -> float:
        return float(self.ratio if self.side == Side.BUY else -self.ratio)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'side': self.side.value if isinstance(self.side, Enum) else self.side,
            'ratio': self.ratio,
            'contract': self.contract.to_dict() if self.contract else None,
            'entry_price': self.entry_price
        }


# =====================================================
# ساختارهای داده‌ای آنالیز واسط خط لوله (Pipeline Intermediate Results)
# =====================================================

@dataclass(slots=True)
class PayoffAnalysis:
    """حامل مستقل نتایج محاسبات ماتریسی بازدهی و نقاط سربی‌سر (خروجی PayoffCalculator)"""
    returns_pct: np.ndarray = field(compare=False, repr=False)
    net_premium: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    break_even_points: List[float] = field(default_factory=list)


@dataclass(slots=True)
class EvaluationMetrics:
    """حامل داده‌ای امتیازات ریسک، مارجین و نقدشوندگی استخراج‌شده در خط لوله جریانی"""
    required_margin: float = 0.0
    liquidity_score: float = 0.0
    risk_reward_ratio: float = 0.0
    expected_return_pct: float = 0.0


@dataclass(slots=True)
class StrategyClassification:
    """برچسب‌های رفتاری سناریوی بازار برای سیستم تصمیم‌یار"""
    market_type: str = MarketType.NEUTRAL.value
    investor_profile: str = InvestorProfile.BALANCED.value
    risk_level: str = RiskLevel.MEDIUM.value
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {'market_type': self.market_type, 'investor_profile': self.investor_profile, 'risk_level': self.risk_level, 'description': self.description}


@dataclass(slots=True)
class ProfileScores:
    """ساختار متمرکز امتیازدهی موازی متناسب با الگوهای مختلف رفتاری معامله‌گران"""
    conservative: float = 0.0
    balanced: float = 0.0
    aggressive: float = 0.0
    income: float = 0.0
    volatility: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {'conservative': self.conservative, 'balanced': self.balanced, 'aggressive': self.aggressive, 'income': self.income, 'volatility': self.volatility}


# =====================================================
# کاندیدای سبک استراتژی (Opportunity Candidate)
# =====================================================

@dataclass(slots=True)
class OpportunityCandidate:
    """
    کاندیدای سبک و خالص استراتژی برای خط لوله جریانی (Streaming Pipeline).
    کاملاً بیونیک، فاقد محاسبات تو در تو و بهینه‌سازی شده برای فیلترهای لایه اول.
    """
    strategy_name: str
    underlying_ticker: str
    underlying: UnderlyingAsset
    legs: tuple[LegDefinition, ...]
    reference_dte: int  # رفع ایراد چهارم: تعیین DTE مرجع بر اساس منطق اختصاصی ژنراتور استراتژی

    # رفع ایراد اول و هفتم: کپسوله‌سازی نتایج آنالیزها به جای پهن کردن فیلدها در سطح کاندیدا
    analysis: Optional[PayoffAnalysis] = field(
        default=None, compare=False, repr=False)
    metrics: Optional[EvaluationMetrics] = field(
        default=None, compare=False, repr=False)

    @property
    def strategy_key(self) -> tuple:
        """
        رفع ایراد سوم: تولید کلید یکتای کاملاً امن برای استراتژی‌های پیچیده چند سررسیدی (Calendar Spreads)
        با ترکیب نماد، قیمت اعمال، روز تا سررسید، موقعیت و ضریب هر لگ.
        """
        return (
            self.strategy_name,
            self.underlying_ticker,
            tuple(
                (leg.contract.ticker, leg.contract.strike_price,
                 leg.contract.days_to_maturity, leg.side, leg.ratio)
                for leg in self.legs if leg.contract
            )
        )


# =====================================================
# مدل جامع فرصت معاملاتی (Opportunity)
# =====================================================

@dataclass(slots=True)
class Opportunity:
    """مدل جامع یک موقعیت معاملاتی کشف، ارزیابی و رتبه‌بندی شده نهایی برای کلاینت"""
    strategy_name: str
    underlying_ticker: str
    legs: List[LegDefinition]
    S0_stock: float = 0.0
    days_to_maturity: int = 0

    # ===== معیارهای مالی و ماتریسی =====
    net_premium: float = 0.0
    pop: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    break_even_points: List[float] = field(default_factory=list)
    returns_monthly_pct: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=float), compare=False, repr=False)

    # ===== معیارهای سرمایه و نقدشوندگی =====
    required_margin: float = 0.0
    total_premium: float = 0.0
    risk_reward_ratio: float = 0.0
    expected_return_pct: float = 0.0
    liquidity_score: float = 0.0
    execution_score: float = 0.0

    # ===== امتیازدهی هوشمند (DSS) =====
    classification: StrategyClassification = field(
        default_factory=StrategyClassification)
    profile_scores: ProfileScores = field(default_factory=ProfileScores)
    final_score: float = 0.0
    rank: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategy_name': self.strategy_name, 'underlying_ticker': self.underlying_ticker,
            'days_to_maturity': self.days_to_maturity, 'net_premium': self.net_premium,
            'max_profit': self.max_profit, 'max_loss': self.max_loss, 'break_even_points': self.break_even_points,
            'required_margin': self.required_margin, 'total_premium': self.total_premium,
            'risk_reward_ratio': self.risk_reward_ratio, 'expected_return_pct': self.expected_return_pct,
            'liquidity_score': self.liquidity_score, 'classification': self.classification.to_dict(),
            'profile_scores': self.profile_scores.to_dict(), 'final_score': self.final_score,
            'rank': self.rank, 'timestamp': self.timestamp.isoformat(), 'legs': [leg.to_dict() for leg in self.legs]
        }

    @classmethod
    def from_candidate(cls, candidate: OpportunityCandidate, contract_size: Optional[int] = None) -> Opportunity:
        """
        رفع ایراد پنجم و ششم: تبدیل خالص کارخانه‌ای (Factory Method) بدون محاسبات سنگین داخلی.
        محاسبه پرمیوم کل بر اساس اندازه قرارداد معتبر انجام می‌شود تا از وابستگی به مقادیر ثابت هاردکد رها شویم.
        """
        analysis = candidate.analysis if candidate.analysis is not None else PayoffAnalysis(
            np.array([]))
        metrics = candidate.metrics if candidate.metrics is not None else EvaluationMetrics()

        # استخراج هوشمند ضریب قرارداد از اولین لگ معتبر آپشن در صورت عدم پاس شدن ورودی
        if contract_size is None:
            option_legs = [
                leg for leg in candidate.legs if leg.contract and leg.contract.option_type != OptionType.STOCK]
            contract_size = option_legs[0].contract.contract_size if option_legs else 1000

        return cls(
            strategy_name=candidate.strategy_name,
            underlying_ticker=candidate.underlying_ticker,
            legs=list(candidate.legs),
            S0_stock=candidate.underlying.last_price,
            days_to_maturity=candidate.reference_dte,
            net_premium=analysis.net_premium,
            max_profit=analysis.max_profit,
            max_loss=analysis.max_loss,
            break_even_points=analysis.break_even_points,
            returns_monthly_pct=analysis.returns_pct,
            required_margin=metrics.required_margin,
            total_premium=analysis.net_premium * contract_size,
            risk_reward_ratio=metrics.risk_reward_ratio,
            expected_return_pct=metrics.expected_return_pct,
            liquidity_score=metrics.liquidity_score,
            timestamp=datetime.now()
        )


@dataclass(slots=True)
class ScanResult:
    """مدل نهایی خروجی دوره‌ای اسکن کامل زنجیره بازار"""
    timestamp: datetime = field(default_factory=datetime.now)
    total_strategies_scanned: int = 0
    total_combinations_generated: int = 0
    total_combinations_filtered: int = 0
    candidates: List[OpportunityCandidate] = field(default_factory=list)
    opportunities: List[Opportunity] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dataframe(self) -> pd.DataFrame:
        if not self.opportunities:
            return pd.DataFrame()

        records = []
        for opp in self.opportunities:
            record = {
                'Strategy': opp.strategy_name, 'Ticker': opp.underlying_ticker, 'DaysToMaturity': opp.days_to_maturity,
                'MarketType': opp.classification.market_type, 'InvestorProfile': opp.classification.investor_profile,
                'RiskLevel': opp.classification.risk_level, 'NetPremium': round(opp.net_premium, 2),
                'MaxProfit': round(opp.max_profit, 2), 'MaxLoss': round(opp.max_loss, 2),
                'RiskReward': round(opp.risk_reward_ratio, 2), 'ExpectedReturn': round(opp.expected_return_pct, 2),
                'Margin': round(opp.required_margin, 2), 'LiquidityScore': round(opp.liquidity_score, 2),
                'FinalScore': round(opp.final_score, 2), 'Rank': opp.rank, 'Timestamp': opp.timestamp
            }
            for i, leg in enumerate(opp.legs, 1):
                if leg.contract:
                    record[f'Leg{i}_Symbol'] = leg.contract.ticker
                    record[f'Leg{i}_Side'] = leg.side.value if isinstance(
                        leg.side, Enum) else leg.side
                    record[f'Leg{i}_Ratio'] = leg.ratio
            records.append(record)

        df = pd.DataFrame(records)
        return df.sort_values('Rank') if 'Rank' in df.columns else df


# =====================================================
# مدل تصویر لحظه‌ای متمرکز بازار (Market Snapshot)
# =====================================================

@dataclass(slots=True)
class MarketSnapshot:
    """تصویر لحظه‌ای منسجم و نمایه شده از کل زنجیره بازار آپشن بورس تهران"""
    timestamp: datetime = field(default_factory=datetime.now)
    underlying_assets: Dict[str, UnderlyingAsset] = field(default_factory=dict)
    option_contracts: List[OptionContract] = field(default_factory=list)
    risk_free_rate: float = 0.24

    # کش‌های داخلی سریع لایه دسترسی دیتابیس
    _options_by_underlying: Dict[str, List[OptionContract]] = field(
        default_factory=dict, repr=False)
    _options_by_symbol: Dict[str, OptionContract] = field(
        default_factory=dict, repr=False)
    _indices_built: bool = field(default=False, repr=False)

    # آرایه‌های متمرکز و واحد سطوح قیمت بدون تکرار فیلدها
    price_levels: Optional[np.ndarray] = None
    pct_steps: Optional[np.ndarray] = None

    def __post_init__(self):
        self.sync_underlying_prices()
        self.build_indices()
        if self.price_levels is None:
            self.price_levels = get_price_levels(
                10000.0)  # مبنای محاسبات اولیه پیش‌فرض
            self.pct_steps = get_price_steps()

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> MarketSnapshot:
        if df.empty:
            logger.warning("انتقال دیتای خالی به قالب DataFrame.")
            return cls()

        underlying_assets = cls._extract_underlyings(df)
        option_contracts = []

        raw_records = df.to_dict(orient='records')
        for row in raw_records:
            try:
                contract = cls._row_to_option_contract_from_dict(row)
                if contract.ticker:
                    option_contracts.append(contract)
            except Exception as e:
                logger.debug(f"خطا در پارس سطر دیتا: {e}")
                continue

        return cls(timestamp=datetime.now(), underlying_assets=underlying_assets, option_contracts=option_contracts)

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
                if str(group['Market'].iloc[0]).lower() in ['ifb', 'فرابورس']:
                    market = ExchangeType.IFB

            asset_type = AssetType.STOCK
            if 'IsETF' in group.columns and pd.notna(group['IsETF'].iloc[0]) and bool(group['IsETF'].iloc[0]):
                asset_type = AssetType.ETF_STOCK

            underlyings[ticker_str] = UnderlyingAsset(
                ticker=ticker_str, name=name, last_price=underlying_price,
                close_price=underlying_price, market=market, asset_type=asset_type, yesterday_price=underlying_price
            )
        return underlyings

    @classmethod
    def _row_to_option_contract_from_dict(cls, row: dict) -> OptionContract:
        return OptionContract(
            ticker=str(row.get('Ticker', '')), name=str(row.get('Name', '')),
            underlying_ticker=str(row.get('UnderlyingTicker', '')), option_type=row['Type'],
            strike_price=cls._clean_float(row.get('StrikePrice')),
            contract_size=int(row.get('ContractSize', 1000)) if pd.notna(
                row.get('ContractSize')) else 1000,
            expiry_date=row.get('MaturityDate') if pd.notna(
                row.get('MaturityDate')) else None,
            days_to_maturity=int(row.get('DaysToMaturity', 0)) if pd.notna(
                row.get('DaysToMaturity')) else 0,
            bid=cls._clean_float(row.get('BidPrice')), ask=cls._clean_float(row.get('AskPrice')),
            last_price=cls._clean_float(row.get('LastPrice')), close_price=cls._clean_float(row.get('ClosePrice')),
            underlying_price=cls._clean_float(row.get('UnderlyingPrice')), yesterday_price=cls._clean_float(row.get('ClosePrice')),
            volume=int(row.get('Volume', 0)) if pd.notna(
                row.get('Volume')) else 0,
            open_interest=int(row.get('OpenPositions', 0)) if pd.notna(
                row.get('OpenPositions')) else 0,
            value=cls._clean_float(row.get('Value')), instrument_code=str(row.get('InstrumentCode', '')),
            instrument_code_ua=str(row.get('InstrumentCode-UA', ''))
        )

    @staticmethod
    def _clean_float(val) -> float:
        if pd.isna(val) or val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

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
