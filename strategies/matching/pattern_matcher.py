# strategies/matching/pattern_matcher.py
# -*- coding: utf-8 -*-

import logging
from itertools import permutations
from typing import List, Tuple, Optional, Dict, Any

from core.models import OptionContract, StrategyLegPattern, LegDefinition
from core.enums import OptionType, Side

logger = logging.getLogger("OptionScanner.Strategies.Matching")


class PatternMatcher:
    """
    موتور تطبیق الگوهای استراتژی (نسخه استاندارد صنعتی نهایی)
    کاملاً داینامیک، امن در برابر قفل CPU، و هماهنگ با لایه تعاریف استراتژی‌ها.
    """

    @staticmethod
    def match_all(
        contracts: List[OptionContract], 
        patterns: Tuple[StrategyLegPattern, ...],
        strategy_rules: Optional[Dict[str, Any]] = None
    ) -> List[List[LegDefinition]]:
        """
        تطبیق قراردادهای ورودی با پترن‌های تئوریک استراتژی.
        
        توجه: ژنراتورها باید قبلاً با استفاده از combinations، دقیقاً به تعداد
        لگ‌های استراتژی قرارداد به این متد پاس بدهند.
        """
        strategy_rules = strategy_rules or {}
        
        # 🛠️ رفع ایراد شماره ۱ (حل قطعی باگ کراش CPU):
        # با این گارد، طول لزوماً برابر تعداد پترن‌هاست (مثلا ۴). 
        # جایگشت یک لیست ۴ تایی کلاً ۲۴ حالت است که در میکروثانیه اجرا می‌شود.
        if len(contracts) != len(patterns):
            logger.error(f"تعداد کانتراکت‌های ورودی ({len(contracts)}) با تعداد پترن‌ها ({len(patterns)}) برابر نیست.")
            return []

        valid_matches: List[List[LegDefinition]] = []

        # اجرا روی حداکثر ۲۴ یا ۶ حالت (کاملاً بهینه)
        for contract_perm in permutations(contracts):
            is_valid_match = True
            matched_legs: List[LegDefinition] = []

            for contract, pattern in zip(contract_perm, patterns):
                # تطبیق نوع اختیار (Call/Put/Stock)
                if contract.option_type != pattern.option_type:
                    is_valid_match = False
                    break

                # تعیین entry_price از قرارداد واقعی بر اساس جهت لگ
                if contract.option_type == OptionType.STOCK:
                    ep = contract.last_price
                elif pattern.side == Side.BUY:
                    ep = contract.ask if contract.ask > 0 else contract.last_price
                else:
                    ep = contract.bid if contract.bid > 0 else contract.last_price

                matched_legs.append(LegDefinition(
                    side=pattern.side,
                    ratio=pattern.ratio,
                    contract=contract,
                    entry_price=ep,
                ))

            if is_valid_match:
                # بررسی روابط قیمتی و زمانی کلان بین لگ‌ها
                if PatternMatcher._validate_structural_relationships(matched_legs, patterns, strategy_rules):
                    valid_matches.append(matched_legs)

        return valid_matches

    @staticmethod
    def _validate_structural_relationships(
        legs: List[LegDefinition], 
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any]
    ) -> bool:
        """
        راستی‌آزمایی ماتریس روابط بین لگ‌ها بدون هاردکد کردن ترتیبات صلب بازار.
        """
        strike_groups: Dict[str, float] = {}
        maturity_groups: Dict[str, int] = {}

        # 🛠️ رفع ایراد شماره ۳: اطلاعات strike_group و maturity_group مستقیماً 
        # از پترن (که خود از فایل definition لود شده) خوانده می‌شود. 
        # لذا برای Butterfly به صورت خودکار K1, K2, K2, K3 جفت‌وجور خواهد شد.
        for leg, pattern in zip(legs, patterns):
            contract = leg.contract
            if not contract:
                return False

            if pattern.strike_group:
                g_strike = pattern.strike_group
                # اگر این گروه قبلاً پر شده، پوزیشن فعلی باید دقیقاً همان استرایک را داشته باشد
                if g_strike in strike_groups and strike_groups[g_strike] != contract.strike_price:
                    return False
                strike_groups[g_strike] = contract.strike_price

            if pattern.maturity_group:
                g_mat = pattern.maturity_group
                if g_mat in maturity_groups and maturity_groups[g_mat] != contract.days_to_maturity:
                    return False
                maturity_groups[g_mat] = contract.days_to_maturity

        # 🛠️ رفع ایراد شماره ۲: انطباق کامل با شبیه‌سازی مالی تئوریک (K1 < K2 < K3 < K4)
        # در تمام استراتژی‌ها اعم از Bull یا Bear، نام‌گذاری نمادین استرایک‌ها صعودی است.
        # مثلاً در Bear Put Spread نیز K1 (پایین‌تر) < K2 (بالاتر) است، فقط سمت خرید و فروش جابجا می‌شود.
        strike_order = rules.get("strike_order", "ascending")
        if strike_order == "ascending":
            sorted_keys = sorted([k for k in strike_groups.keys() if k.startswith("K")])
            strike_values = [strike_groups[k] for k in sorted_keys]
            if strike_values != sorted(strike_values):
                return False
        elif strike_order == "descending":
            sorted_keys = sorted([k for k in strike_groups.keys() if k.startswith("K")])
            strike_values = [strike_groups[k] for k in sorted_keys]
            if strike_values != sorted(strike_values, reverse=True):
                return False

        # 🛠️ رفع ایراد شماره ۴: تکمیل و ارتقای کامل روابط سررسید (Maturity Order)
        maturity_order = rules.get("maturity_order", "same")
        if "M1" in maturity_groups and "M2" in maturity_groups:
            if maturity_order == "same" and maturity_groups["M1"] != maturity_groups["M2"]:
                return False
            elif maturity_order == "calendar" and maturity_groups["M1"] >= maturity_groups["M2"]:
                # لگ کوتاه (M1) زودتر از لگ بلند (M2) سررسید می‌شود
                return False
            elif maturity_order == "diagonal" and maturity_groups["M1"] == maturity_groups["M2"]:
                return False

        return True