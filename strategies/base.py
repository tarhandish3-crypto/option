# strategies/base.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

from core.models import LegDefinition
from core.enums import OptionType, Side, GeneratorType


@dataclass(slots=True)
class StrategyDefinition:
    """
    تعریف کامل یک استراتژی - داده محور
    """
    name: str
    legs_count: int
    generator_type: GeneratorType
    weight_pattern: Tuple[LegDefinition, ...]
    include_stock: bool = False
    description: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
            cls,
            name: str,
            generator_type: GeneratorType,
            weight_pattern: List[Tuple[str, float]],
            include_stock: bool = False,
            description: str = "",
            rules: Optional[Dict] = None) -> StrategyDefinition:
        """
        ساخت استراتژی با الگوی ساده

        Args:
            name: نام استراتژی
            generator_type: نوع تولیدکننده
            weight_pattern: الگوی وزنی [("call", 1.0), ("put", -1.0)]
            include_stock: آیا سهم پایه دارد؟
            description: توضیحات
            rules: قوانین خاص استراتژی

        Returns:
            StrategyDefinition
        """
        legs = []
        for i, (opt_type, weight) in enumerate(weight_pattern):
            option_type = OptionType.CALL if opt_type.lower() == "call" else OptionType.PUT
            side = Side.BUY if weight > 0 else Side.SELL

            legs.append(LegDefinition(
                name=f"leg_{i + 1}",
                option_type=option_type,
                side=side,
                strike_rel=f"K{i + 1}",
                ratio=abs(int(weight)) if abs(weight) > 0 else 1))

        return cls(
            name=name,
            legs_count=len(legs),
            generator_type=generator_type,
            weight_pattern=tuple(legs),
            include_stock=include_stock,
            description=description,
            rules=rules or {})
