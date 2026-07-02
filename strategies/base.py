# strategies/base.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, Optional, List

from core.enums import GeneratorType, OptionType, Side
from core.models import StrategyLegPattern


@dataclass(slots=True)
class StrategyDefinition:
    """
    تعریف کامل یک استراتژی اختیار معامله (تئوریک)
    """
    name: str
    generator_type: GeneratorType
    patterns: Tuple[StrategyLegPattern, ...]
    include_stock: bool = False
    description: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """اعتبارسنجی بعد از ساخت"""
        if not self.patterns:
            raise ValueError(
                f"استراتژی {self.name} باید حداقل یک الگو داشته باشد.")
        if len(self.patterns) > 4:
            logger.warning(
                f"استراتژی {self.name} دارای {len(self.patterns)} لگ است (بیش از حد معمول).")

    @property
    def legs_count(self) -> int:
        """تعداد لگ‌های استراتژی"""
        return len(self.patterns)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        generator_type: GeneratorType,
        patterns: List[Dict[str, Any]],
        include_stock: bool = False,
        description: str = "",
        rules: Optional[Dict[str, Any]] = None,
    ) -> "StrategyDefinition":
        """
        سازنده ساده و امن برای تعریف استراتژی
        """
        leg_patterns: List[StrategyLegPattern] = []

        for leg in patterns:
            # Option Type
            opt = leg["option_type"]
            if isinstance(opt, str):
                opt = opt.upper()
                if opt == "CALL":
                    option_type = OptionType.CALL
                elif opt == "PUT":
                    option_type = OptionType.PUT
                elif opt in ["STOCK", "S"]:
                    option_type = OptionType.STOCK
                else:
                    raise ValueError(f"Unknown option_type: {opt}")
            else:
                option_type = opt

            # Side
            side = leg.get("side", Side.BUY)
            if isinstance(side, str):
                side = side.upper()
                side = Side.BUY if side == "BUY" else Side.SELL

            # Ratio
            ratio = int(leg.get("ratio", 1))
            if ratio <= 0:
                raise ValueError("Ratio must be positive.")

            leg_patterns.append(
                StrategyLegPattern(
                    option_type=option_type,
                    side=side,
                    ratio=ratio,
                    strike_group=leg.get("strike_group"),
                    maturity_group=leg.get("maturity_group"),
                )
            )

        return cls(
            name=name,
            generator_type=generator_type,
            patterns=tuple(leg_patterns),
            include_stock=include_stock,
            description=description,
            rules=rules or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "generator_type": self.generator_type.value,
            "legs_count": self.legs_count,
            "include_stock": self.include_stock,
            "description": self.description,
            "rules": self.rules,
            "patterns": [
                {
                    "option_type": p.option_type.value if hasattr(p.option_type, 'value') else str(p.option_type),
                    "side": p.side.value if hasattr(p.side, 'value') else str(p.side),
                    "ratio": p.ratio,
                    "strike_group": p.strike_group,
                    "maturity_group": p.maturity_group,
                }
                for p in self.patterns
            ],
        }

    def __str__(self) -> str:
        return f"StrategyDefinition(name={self.name}, legs={self.legs_count}, generator={self.generator_type.value})"
