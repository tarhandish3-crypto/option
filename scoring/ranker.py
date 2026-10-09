# scoring/ranker.py
# -*- coding: utf-8 -*-

"""
موتور رتبه‌بندی و امتیازدهی چند-شخصیتی.

سه شخصیت:
    1 = محافظه‌کار (Conservative)
    2 = متعادل (Balanced) — پیش‌فرض
    3 = پرریسک (Aggressive)

هر فرصت، ۳ امتیاز می‌گیرد. اگر فرصت در یک شخصیت رد شود، امتیاز آن -1 می‌شود.

فرمول امتیازدهی (برگرفته از 0myStrategy/Bull_call_spread.py):
    composite = (R30^w_r) × (M30^w_m)
              × prob_survival
              × (VQ/10)^0.3
              × min(1, (M30/R30)^0.5)
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Any, Optional
from scipy.stats import norm

from core.models import Opportunity

logger = logging.getLogger("OptionScanner.Scoring.Ranker")


# ═══════════════════════════════════════════════════════════════
# ضرایب ۳ شخصیت
# ═══════════════════════════════════════════════════════════════

PERSONALITY_WEIGHTS: Dict[int, Dict[str, Any]] = {
    1: {
        "key": "conservative",
        "name": "محافظه‌کار",
        "w_r": 0.25, "w_m": 0.75,
        "min_monthly_return": 10.0,
        "min_margin_floor": 25.0,
        "min_m_risk": 2.5,
        "min_rr_ratio": 0.20,
    },
    2: {
        "key": "balanced",
        "name": "متعادل",
        "w_r": 0.40, "w_m": 0.60,
        "min_monthly_return": 7.0,
        "min_margin_floor": 20.0,
        "min_m_risk": 2.0,
        "min_rr_ratio": 0.10,
    },
    3: {
        "key": "aggressive",
        "name": "پرریسک",
        "w_r": 0.60, "w_m": 0.40,
        "min_monthly_return": 4.0,
        "min_margin_floor": 12.0,
        "min_m_risk": 1.2,
        "min_rr_ratio": 0.0,
    },
}

DEFAULT_PERSONALITY = 2
PERSONALITY_ORDER = [1, 2, 3]

# ثابت‌های محاسبه
DEFAULT_SIGMA = 0.30
VOL_QUALITY_POWER = 0.3
IMBALANCE_POWER = 0.5
T_DISPLAY_EPSILON = 0.02
DAYS_IN_YEAR = 365


# ═══════════════════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════════════════

class OpportunityRanker:
    """موتور رتبه‌بندی سه‌شخصیتی."""

    __slots__ = ("default_personality",)

    def __init__(self, default_personality: int = DEFAULT_PERSONALITY):
        self.default_personality = default_personality

    # ═══════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════

    def rank_opportunities(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        if not opportunities:
            return []

        scored = []
        for opp in opportunities:
            result = self._score_opportunity(opp)
            if result is not None:
                scored.append(result)

        if not scored:
            return []

        # مرتب‌سازی بر اساس شخصیت پیش‌فرض
        default_key = PERSONALITY_WEIGHTS[self.default_personality]["key"]
        scored.sort(
            key=lambda o: o.scores.get(default_key, -1.0),
            reverse=True,
        )

        # تعیین rank و final_score
        for i, opp in enumerate(scored, 1):
            opp.rank = i
            opp.final_score = opp.scores.get(default_key, 0.0)

        logger.info(f"Ranked {len(scored)} opportunities (3 personalities)")
        return scored

    def get_top_n(self, ranked: List[Opportunity], n: int = 100) -> List[Opportunity]:
        return ranked[:n]

    def get_summary(self, ranked: List[Opportunity]) -> Dict[str, Any]:
        if not ranked:
            return {"total": 0, "by_personality": {}}

        by_p = {}
        for p in PERSONALITY_ORDER:
            key = PERSONALITY_WEIGHTS[p]["key"]
            valid = [o for o in ranked if o.scores.get(key, -1.0) > 0]
            by_p[key] = {
                "count": len(valid),
                "avg_score": round(
                    sum(o.scores[key] for o in valid) / len(valid), 2
                ) if valid else 0.0,
            }
        return {"total": len(ranked), "by_personality": by_p}

    # ═══════════════════════════════════════════════════════════
    # Scoring
    # ═══════════════════════════════════════════════════════════

    def _score_opportunity(self, opp: Opportunity) -> Optional[Opportunity]:
        metadata = opp.metadata or {}

        R30 = float(metadata.get("R30", 0.0))
        M30 = float(metadata.get("M30", 0.0))
        raw_margin = float(metadata.get("raw_margin_percent", 0.0))
        HV_60 = metadata.get("HV_60", None)
        VQ = metadata.get("VQ", None)
        rr_ratio = float(
            metadata.get("risk_reward_ratio", 0.0)
            or opp.risk_reward_ratio
            or 0.0
        )
        days = int(opp.days_to_maturity or 30)

        # محاسبات مشترک
        M_risk = self._calculate_m_risk(raw_margin, days, HV_60)
        prob_survival = float(norm.cdf(M_risk))

        metadata["M_risk"] = round(M_risk, 4)
        metadata["prob_survival"] = round(prob_survival, 4)

        # امتیازدهی برای هر شخصیت
        scores: Dict[str, float] = {}
        for p in PERSONALITY_ORDER:
            w = PERSONALITY_WEIGHTS[p]
            if not self._passes_hard_filters(R30, M30, M_risk, rr_ratio, w):
                scores[w["key"]] = -1.0
                continue
            scores[w["key"]] = self._calculate_composite(
                R30=R30,
                M30=M30,
                prob_survival=prob_survival,
                VQ=VQ,
                w_r=w["w_r"],
                w_m=w["w_m"],
            )

        # اگر همه رد شدند
        if all(s == -1.0 for s in scores.values()):
            return None

        opp.scores = scores
        opp.metadata = metadata
        return opp

    @staticmethod
    def _calculate_m_risk(raw_margin_percent, days, HV_60) -> float:
        """
        محاسبه‌ی M_risk (Z-Score).
        
        فرمول:
            M_risk = (raw_margin / 100) / (sigma × sqrt(T/365))
        """
        sigma = float(HV_60) if HV_60 and HV_60 > 0 else DEFAULT_SIGMA
        sigma = max(0.05, min(sigma, 2.0))
        days_safe = max(float(days), T_DISPLAY_EPSILON)
        raw_fraction = raw_margin_percent / 100.0
        denom = sigma * math.sqrt(days_safe / DAYS_IN_YEAR)
        return raw_fraction / denom if denom > 0 else 0.0

    @staticmethod
    def _calculate_composite(
        R30: float,
        M30: float,
        prob_survival: float,
        VQ: Optional[float],
        w_r: float,
        w_m: float,
    ) -> float:
        """
        محاسبه‌ی امتیاز نهایی (فرمول کامل 0myStrategy).

        فرمول:
            composite = (R30^w_r) × (M30^w_m)
                      × prob_survival
                      × (VQ/10)^0.3
                      × min(1, (M30/R30)^0.5)

        اجزا:
            - Cobb-Douglas: (R30^w_r) × (M30^w_m)
            - prob_survival: احتمال بقا از توزیع نرمال
            - vol_factor: ضریب کیفیت نوسان از VQ
            - imbalance_factor: نسبت عدم‌تعادل M30/R30
        """
        # ─── ۱. مقادیر ایمن ────────────────────────────
        R30_safe = max(float(R30), 0.1)
        M30_safe = max(float(M30), 0.1)

        # ─── ۲. Cobb-Douglas ────────────────────────────
        score_cd = (R30_safe ** w_r) * (M30_safe ** w_m)

        # ─── ۳. ضریب VQ ─────────────────────────────────
        vq_val = float(VQ) if VQ is not None else 5.0
        vq_val = max(0.0, min(vq_val, 10.0))
        vol_factor = (vq_val / 10.0) ** VOL_QUALITY_POWER

        # ─── ۴. ضریب عدم‌تعادل (imbalance) ───────────────
        # هرچه M30/R30 بیشتر باشد، تعادل بهتر است.
        # ولی اگر M30/R30 بزرگ باشد، یعنی حاشیه امنیت خیلی بیشتر از سود است
        # که ممکن است نشانه‌ی فرصت خیلی محافظه‌کارانه باشد.
        ratio = M30_safe / R30_safe
        imbalance = min(1.0, ratio ** IMBALANCE_POWER)

        # ─── ۵. امتیاز نهایی ─────────────────────────────
        composite = score_cd * prob_survival * vol_factor * imbalance

        return round(composite, 4)

    @staticmethod
    def _passes_hard_filters(R30, M30, M_risk, rr_ratio, w) -> bool:
        """
        بررسی عبور از فیلترهای سخت.

        هر شخصیت، فیلترهای خودش را دارد.
        """
        if R30 < w["min_monthly_return"]:
            return False
        if M30 < w["min_margin_floor"]:
            return False
        if M_risk < w["min_m_risk"]:
            return False
        if rr_ratio < w["min_rr_ratio"]:
            return False
        return True