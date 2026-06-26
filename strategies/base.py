# strategies/base.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, Optional, List
from core.enums import (
    GeneratorType,
    OptionType,
    Side,)
from core.models import StrategyLegPattern

# ============================================================
# Strategy Definition
# ============================================================


@dataclass(slots=True)
class StrategyDefinition:
    """
    تعریف کامل یک استراتژی اختیار معامله.

    این کلاس فقط ساختار تئوریک استراتژی را نگهداری می‌کند و
    هیچ وابستگی به قراردادهای واقعی بازار ندارد.
    """
    # ---------------------------
    # اطلاعات عمومی
    # ---------------------------
    name: str
    generator_type: GeneratorType
    patterns: Tuple[StrategyLegPattern, ...]
    include_stock: bool = False
    description: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

    # ----------------------------------------------------------
    @property
    def legs_count(self) -> int:
        """
        تعداد لگ‌های استراتژی.

        همیشه از روی الگوها محاسبه می‌شود تا ناسازگاری ایجاد نشود.
        """
        return len(self.patterns)

    # ----------------------------------------------------------
    @classmethod
    def create(
            cls,
            *,
            name: str,
            generator_type: GeneratorType,
            patterns: List[Dict[str, Any]],
            include_stock: bool = False,
            description: str = "",
            rules: Optional[Dict[str, Any]] = None,) -> "StrategyDefinition":
        """
        سازنده ساده برای تعریف استراتژی.
        """
        leg_patterns: List[StrategyLegPattern] = []
        for leg in patterns:
            # -------------------------
            # Option Type
            # -------------------------
            option_type = leg["option_type"]
            if isinstance(option_type, str):
                option_type = option_type.upper()
                if option_type == "CALL":
                    option_type = OptionType.CALL
                elif option_type == "PUT":
                    option_type = OptionType.PUT
                elif option_type == "STOCK":
                    option_type = OptionType.STOCK
                else:
                    raise ValueError(
                        f"Unknown option type: {option_type}")
            # -------------------------
            # Side
            # -------------------------
            side = leg.get("side", Side.BUY)
            if isinstance(side, str):
                side = side.upper()
                if side == "BUY":
                    side = Side.BUY
                elif side == "SELL":
                    side = Side.SELL
                else:
                    raise ValueError(
                        f"Unknown side: {side}")
            # -------------------------
            # Ratio
            # -------------------------
            ratio = int(leg.get("ratio", 1))
            if ratio <= 0:
                raise ValueError(
                    "Ratio must be greater than zero.")
            # -------------------------
            # Pattern
            # -------------------------
            leg_patterns.append(
                StrategyLegPattern(
                    option_type=option_type,
                    side=side,
                    ratio=ratio,
                    strike_group=leg.get("strike_group"),
                    maturity_group=leg.get("maturity_group"),
                ))
        return cls(
            name=name,
            generator_type=generator_type,
            patterns=tuple(leg_patterns),
            include_stock=include_stock,
            description=description,
            rules=rules or {},)

    # ----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """
        تبدیل استراتژی به ساختار دیکشنری.
        """
        return {
            "name": self.name,
            "generator_type": self.generator_type.value,
            "legs_count": self.legs_count,
            "include_stock": self.include_stock,
            "description": self.description,
            "rules": self.rules,
            "patterns": [
                {
                    "option_type": p.option_type.value,
                    "side": p.side.value,
                    "ratio": p.ratio,
                    "strike_group": p.strike_group,
                    "maturity_group": p.maturity_group,
                }
                for p in self.patterns
            ],
        }

    # ----------------------------------------------------------
    def __str__(self) -> str:
        return (
            f"StrategyDefinition("
            f"name={self.name}, "
            f"legs={self.legs_count}, "
            f"generator={self.generator_type.value})"
        )
