# scoring/ranker.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Union

from scoring.metrics import calculate_all_metrics
from config import RANKING_CONFIG, get_ranking_weights
from scoring.liquidity_score import LiquidityScorer
from core.enums import RankingProfile
from core.models import Opportunity, ProfileScores, LegDefinition

# تنظیم لوگر اختصاصی برای رنکر موازی
logger = logging.getLogger("OptionScanner.Scoring.Ranker")


@dataclass(slots=True)
class RankingWeights:
    """وزن‌های امتیازدهی بر اساس مشخصات رفتاری سرمایه‌گذار"""
    win_rate: float = 0.0
    risk_reward: float = 0.0
    rom: float = 0.0
    margin_efficiency: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0  # تاثیر معکوس (ریسک کمتر = امتیاز بیشتر)


# هماهنگ‌سازی ساختار پروفایل‌ها با دیتای ثابت سیستم
PROFILES: Dict[RankingProfile, RankingWeights] = {
    RankingProfile.CONSERVATIVE: RankingWeights(
        win_rate=0.35, risk_reward=0.10, rom=0.10, margin_efficiency=0.15, max_profit=0.05, max_loss=0.25
    ),
    RankingProfile.BALANCED: RankingWeights(
        win_rate=0.25, risk_reward=0.15, rom=0.20, margin_efficiency=0.15, max_profit=0.10, max_loss=0.15
    ),
    RankingProfile.AGGRESSIVE: RankingWeights(
        win_rate=0.10, risk_reward=0.15, rom=0.35, margin_efficiency=0.15, max_profit=0.15, max_loss=0.10
    ),
    RankingProfile.INCOME: RankingWeights(
        win_rate=0.30, risk_reward=0.10, rom=0.25, margin_efficiency=0.20, max_profit=0.05, max_loss=0.10
    ),
    RankingProfile.VOLATILITY: RankingWeights(
        win_rate=0.10, risk_reward=0.30, rom=0.15, margin_efficiency=0.05, max_profit=0.25, max_loss=0.15
    ),
}


class OpportunityRanker:
    """
    موتور رتبه‌بندی و امتیازدهی موازی (Decision Support System)
    
    ویژگی‌های پیاده‌سازی شده:
    ۱. حذف کامل رویکرد حذفی (No Discard Flow) جهت حفظ تمام پوزیشن‌ها برای DSS.
    ۲. محاسبه همزمان امتیازات برای ۵ پروفایل رفتاری مختلف به صورت موازی.
    ۳. پشتیبانی داینامیک از ورودی Dict و شیء دامنه‌ای Opportunity (ترازبندی قراردادها).
    """

    def __init__(self, default_profile: RankingProfile = RankingProfile.BALANCED):
        """ایجاد رنکر موازی با مشخص کردن پروفایل مبنا برای مرتب‌سازی نهایی"""
        self.default_profile = default_profile
        self.profile_weights: Dict[RankingProfile, RankingWeights] = {}
        self._load_all_profile_weights()

    def _load_all_profile_weights(self) -> None:
        """بارگذاری موازی تمام وزن‌ها از فایل کانفیگ با مکانیزم Fallback ایمن"""
        for profile in RankingProfile:
            try:
                weights_dict = get_ranking_weights(profile.value)
                self.profile_weights[profile] = RankingWeights(
                    win_rate=weights_dict.get("win_rate", PROFILES[profile].win_rate),
                    risk_reward=weights_dict.get("risk_reward", PROFILES[profile].risk_reward),
                    rom=weights_dict.get("rom", PROFILES[profile].rom),
                    margin_efficiency=weights_dict.get("margin_efficiency", PROFILES[profile].margin_efficiency),
                    max_profit=weights_dict.get("max_profit", PROFILES[profile].max_profit),
                    max_loss=weights_dict.get("max_loss", PROFILES[profile].max_loss),)
            except Exception:
                # استفاده از هاردکد ثابت در صورت عدم وجود تنظیمات بیرونی
                self.profile_weights[profile] = PROFILES[profile]

    def rank_opportunities(self, raw_opportunities: List[Union[Dict[str, Any], Opportunity]]) -> List[Opportunity]:
        """پردازش، ارزیابی چندبعدی و رتبه‌بندی داینامیک فرصت‌های بازار بدون فیلترینگ صلب"""
        if not raw_opportunities:
            return []
        
        # شناسایی و ثبت وضعیت نوع ورودی برای مانیتورینگ سیستم
        processed_opportunities: List[Opportunity] = []

        for opp_data in raw_opportunities:
            opportunity = self._analyze_and_score_single(opp_data)
            if opportunity is not None:
                processed_opportunities.append(opportunity)

        if not processed_opportunities:
            return []

        # استخراج پویا نام خصوصیات بر اساس مقدار رشته‌ای انوم (e.g., 'conservative')
        profile_attr = self.default_profile.value.lower()

        # ۱. مرتب‌سازی کل لایه بر اساس خصوصیات پروفایل انتخابی کاربر
        processed_opportunities.sort(
            key=lambda x: getattr(x.profile_scores, profile_attr, x.profile_scores.balanced), 
            reverse=True)

        # ۲. تزریق رتبه پویا (Rank) و تراز کردن فیلد نهایی نهایی سیستم (final_score)
        for i, opp in enumerate(processed_opportunities, 1):
            opp.rank = i
            opp.final_score = getattr(opp.profile_scores, profile_attr, opp.profile_scores.balanced)

        logger.info(f"Ranking layer processing complete. Ranked {len(processed_opportunities)} opportunities.")
        return processed_opportunities

    def _analyze_and_score_single(self, opp: Union[Dict[str, Any], Opportunity]) -> Optional[Opportunity]:
        """تبدیل، استخراج متادیتا و غنی‌سازی چندبعدی شاخص‌های پوزیشن با ایمن‌سازی لبه‌های خطا"""
        is_dict = isinstance(opp, dict)
        
        # ============================================================
        # ۱. استخراج و نرمال‌سازی متادیتا و خصوصیات پایه
        # ============================================================
        if is_dict:
            metadata = opp.get('metadata', {})
            if not isinstance(metadata, dict) or not metadata:
                metadata = opp
        else:
            metadata = getattr(opp, 'metadata', {})
            if not isinstance(metadata, dict) or not metadata:
                metadata = {}
                # تبدیل فیلدهای شیء به دیکشنری بک‌آپ جهت استفاده یکپارچه در لایه‌های پایین
                for key in ['strategy_name', 'underlying_ticker', 'max_profit', 'max_loss', 
                            'net_premium', 'required_margin', 'risk_reward_ratio', 
                            'expected_return_pct', 'max_profit_pct', 'max_loss_pct',
                            'liquidity_score', 'days_to_maturity']:
                    if hasattr(opp, key):
                        metadata[key] = getattr(opp, key)
        
        # استخراج امن آرایه سود و زیان (Payoff Profile)
        profits = self._extract_profits(opp, metadata, is_dict)
        if not profits:
            # اگر ورودی شیء کلاسی بود خود را پاس بده تا زنجیره قطع نشود؛ اگر دیکشنری خام بود دیتای نامعتبر است
            return opp if not is_dict else None
        
        expected_return = self._extract_value(opp, metadata, 'expected_return_pct', is_dict, 0.0)
        margin = self._extract_value(opp, metadata, 'required_margin', is_dict, 0.0)
        days = self._extract_value(opp, metadata, 'days_to_maturity', is_dict, 0)
        strategy_name = self._extract_value(opp, metadata, 'strategy_name', is_dict, 'unknown')
        underlying_ticker = self._extract_value(opp, metadata, 'underlying_ticker', is_dict, 
                             self._extract_value(opp, metadata, 'ticker', is_dict, ''))
        
        # ============================================================
        # ۲. محاسبه شاخص‌های آماری پایه از لایه ریاضیات محاسباتی
        # ============================================================
        metrics = calculate_all_metrics(profits, expected_return, margin, days)

        # ============================================================
        # ۳. نرمالایز کردن استاندارد فاکتورها (بازه صفر تا ۱۰۰)
        # ============================================================
        win_rate_norm = metrics.win_rate * 100
        risk_reward_norm = min(metrics.risk_reward_ratio * 20, 100.0)
        rom_norm = min(metrics.rom * 10, 100.0)
        margin_eff_norm = min(metrics.margin_efficiency * 1000, 100.0)
        max_profit_norm = min(metrics.max_profit * 2, 100.0)
        max_loss_norm = min(abs(metrics.max_loss) * 2, 100.0)

        # ============================================================
        # ۴. محاسبه موازی امتیازها برای تک‌تک پروفایل‌های سرمایه‌گذاری
        # ============================================================
        scores = {}
        for profile in RankingProfile:
            w = self.profile_weights[profile]
            score = (
                win_rate_norm * w.win_rate +
                risk_reward_norm * w.risk_reward +
                rom_norm * w.rom +
                margin_eff_norm * w.margin_efficiency +
                max_profit_norm * w.max_profit +
                (100.0 - max_loss_norm) * w.max_loss)
            scores[profile] = round(score, 2)

        # محاسبه امتیاز نقدشوندگی
        liquidity_score = self._calculate_liquidity_score(opp, is_dict)

        # ساختاردهی به خروجی مدل امتیازات
        profile_scores = ProfileScores(
            conservative=scores[RankingProfile.CONSERVATIVE],
            balanced=scores[RankingProfile.BALANCED],
            aggressive=scores[RankingProfile.AGGRESSIVE],
            income=scores[RankingProfile.INCOME],
            volatility=scores[RankingProfile.VOLATILITY])

        # ============================================================
        # ۵. تزریق به شیء موجود یا قالب‌بندی دیکشنری ورودی به مدل جدید
        # ============================================================
        if not is_dict:
            # اعمال مستقیم روی ارجاع شیء دامنه هسته سیستم
            opp.profile_scores = profile_scores
            opp.liquidity_score = round(liquidity_score, 2)
            opp.max_profit = metrics.max_profit
            opp.max_loss = metrics.max_loss
            opp.risk_reward_ratio = metrics.risk_reward_ratio
            opp.expected_return_pct = expected_return
            opp.required_margin = margin
            
            # غنی‌سازی ساختار لایه دیکشنری داخلی متادیتا جهت استفاده شیت اکسل
            if hasattr(opp, 'metadata') and isinstance(opp.metadata, dict):
                opp.metadata['win_rate'] = metrics.win_rate
                opp.metadata['expected_value'] = metrics.expected_return
                opp.metadata['risk_reward_ratio'] = metrics.risk_reward_ratio
                opp.metadata['sharpe_ratio'] = metrics.sharpe_ratio
                opp.metadata['rom'] = metrics.rom
                opp.metadata['margin_efficiency'] = metrics.margin_efficiency
            
            return opp
        else:
            # کار با ساختار دیکشنری قدیمی و ساخت نمونه تازه از کلاس دامنه‌ای
            return self._create_opportunity_from_dict(
                opp, metadata, profile_scores, liquidity_score, metrics, 
                strategy_name, underlying_ticker, days
            )

    def _extract_profits(self, opp: Union[Dict, Opportunity], metadata: Dict, is_dict: bool) -> List[float]:
        """استخراج آرایه پپ‌آف از نوع داده با مدیریت ساختارهای نامتوازن"""
        if is_dict:
            profits = metadata.get('profits', [])
            if not profits: profits = opp.get('profits', [])
            if not profits: profits = opp.get('net_profits_closed', [])
            if not profits: profits = metadata.get('net_profits_closed', [])
            return profits
        else:
            profits = getattr(opp, 'profits', [])
            if not profits and hasattr(opp, 'metadata') and isinstance(opp.metadata, dict):
                profits = opp.metadata.get('profits', [])
            if not profits and hasattr(opp, 'net_profits_closed'):
                profits = getattr(opp, 'net_profits_closed', [])
            if not profits and hasattr(opp, 'raw_scores') and isinstance(opp.raw_scores, dict):
                profits = opp.raw_scores.get('net_profits_closed', [])
            return profits

    def _extract_value(self, opp: Union[Dict, Opportunity], metadata: Dict, key: str, 
                       is_dict: bool, default: Any) -> Any:
        """استخراج مقدار کلید بر اساس معماری لایه‌ای تراز شده"""
        if is_dict:
            return metadata.get(key, opp.get(key, default))
        else:
            if hasattr(opp, key):
                return getattr(opp, key, default)
            if hasattr(opp, 'metadata') and isinstance(opp.metadata, dict):
                return opp.metadata.get(key, default)
            if hasattr(opp, 'raw_scores') and isinstance(opp.raw_scores, dict):
                return opp.raw_scores.get(key, default)
            return default

    def _calculate_liquidity_score(self, opp: Union[Dict, Opportunity], is_dict: bool) -> float:
        """محاسبه ماتریس نقدشوندگی بازار آپشن بر اساس حجم معاملات و آپن اینترست لگ‌ها"""
        try:
            legs = opp.get('legs', []) if is_dict else getattr(opp, 'legs', [])
            metadata = opp.get('metadata', {}) if is_dict else getattr(opp, 'metadata', {})
            
            if not legs:
                return 0.0
            
            contract_scores = metadata.get('contract_scores', {}) if isinstance(metadata, dict) else {}
            
            if not contract_scores:
                for leg in legs:
                    contract = leg.get('contract') if isinstance(leg, dict) else getattr(leg, 'contract', None)
                    if contract:
                        is_c_dict = isinstance(contract, dict)
                        ticker = contract.get('ticker', '') if is_c_dict else getattr(contract, 'ticker', '')
                        volume = contract.get('volume', 0) if is_c_dict else getattr(contract, 'volume', 0)
                        oi = contract.get('open_interest', 0) if is_c_dict else getattr(contract, 'open_interest', 0)
                        
                        if ticker:
                            score = min(volume / 100, 1.0) * 30 + min(oi / 50, 1.0) * 25
                            contract_scores[ticker] = score
            
            leg_defs = []
            for leg in legs:
                if isinstance(leg, LegDefinition):
                    leg_defs.append(leg)
                elif isinstance(leg, dict):
                    leg_defs.append(LegDefinition(
                        contract=leg.get('contract'),
                        side=leg.get('side'),
                        ratio=leg.get('ratio', 1)
                    ))
                elif hasattr(leg, 'contract'):
                    leg_defs.append(leg)
            
            return LiquidityScorer.score_strategy(leg_defs, contract_scores)
            
        except Exception as e:
            logger.debug(f"Non-critical issue inside liquidity score routing: {e}")
            return 0.0

    def _create_opportunity_from_dict(self, opp: Dict, metadata: Dict, profile_scores: ProfileScores,
                                       liquidity_score: float, metrics, strategy_name: str,
                                       underlying_ticker: str, days: int) -> Opportunity:
        """کارخانه شیءسازی داخلی لایه رنکر برای ورودی‌های دیکشنری خام"""
        raw_legs = opp.get('legs', [])
        leg_definitions: List[LegDefinition] = []
        
        for leg in raw_legs:
            if isinstance(leg, LegDefinition):
                leg_definitions.append(leg)
            elif isinstance(leg, dict):
                leg_definitions.append(LegDefinition(
                    name=leg.get('name', ''),
                    option_type=leg.get('option_type'),
                    side=leg.get('side'),
                    ratio=leg.get('ratio', 1),
                    contract=leg.get('contract'),
                    is_stock_leg=leg.get('is_stock_leg', False)
                ))
        
        return Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=underlying_ticker,
            legs=leg_definitions,
            days_to_maturity=days,
            net_premium=opp.get('net_premium', 0.0),
            max_profit=metrics.max_profit,
            max_loss=metrics.max_loss,
            break_even_points=metadata.get('break_even_points', []),
            required_margin=opp.get('required_margin', 0.0),
            risk_reward_ratio=metrics.risk_reward_ratio,
            expected_return_pct=opp.get('expected_return_pct', 0.0),
            max_profit_pct=opp.get('max_profit_pct', 0.0),
            max_loss_pct=opp.get('max_loss_pct', 0.0),
            liquidity_score=round(liquidity_score, 2),
            profile_scores=profile_scores,
            metadata=metadata
        )

    def _calculate_liquidity_score_for_opportunity(self, opp: Dict[str, Any]) -> float:
        """متد موروثی و سازگار نگهداری شده برای کدهای قدیمی لایه‌های بالا"""
        return self._calculate_liquidity_score(opp, True)

    def get_top_n(self, ranked_opportunities: List[Opportunity], n: int = 10) -> List[Opportunity]:
        """انتخاب سطرهای برتر جهت مانیتورینگ اولیه یا کنترل موضعی فلو"""
        return ranked_opportunities[:n]

    def get_summary(self, ranked_opportunities: List[Opportunity]) -> Dict[str, Any]:
        """تولید گزارش متمرکز و آماری از کل فرصت‌های رتبه‌بندی شده نهایی بازار"""
        if not ranked_opportunities:
            return {
                "total": 0, "avg_score": 0, "max_score": 0, "min_score": 0, 
                "avg_liquidity": 0, "strategies": {}
            }

        scores = [opp.final_score for opp in ranked_opportunities]
        liquidity_scores = [opp.liquidity_score for opp in ranked_opportunities]

        strategy_stats = {}
        for opp in ranked_opportunities:
            name = opp.strategy_name
            if name not in strategy_stats:
                strategy_stats[name] = {"count": 0, "avg_score": 0, "total_score": 0}
            strategy_stats[name]["count"] += 1
            strategy_stats[name]["total_score"] += opp.final_score

        for name in strategy_stats:
            strategy_stats[name]["avg_score"] = round(
                strategy_stats[name]["total_score"] / strategy_stats[name]["count"], 2
            )
            del strategy_stats[name]["total_score"]

        return {
            "total": len(ranked_opportunities),
            "avg_score": round(sum(scores) / len(scores), 2),
            "max_score": round(max(scores), 2),
            "min_score": round(min(scores), 2),
            "avg_liquidity": round(sum(liquidity_scores) / len(liquidity_scores), 2),
            "strategies": strategy_stats
        }