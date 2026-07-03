# strategies/definitions/base.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from typing import Tuple, Dict, Any, Optional, List

from core.enums import GeneratorType, OptionType, Side
from core.models import StrategyLegPattern

logger = logging.getLogger("OptionScanner.Strategies.Base")

@dataclass(slots=True)
class StrategyDefinition:
    """
    تعریف کامل و خودکار یک استراتژی اختیار معامله
    """
    name: str
    generator_type: GeneratorType
    patterns: Tuple[StrategyLegPattern, ...]
    include_stock: bool = False
    description: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """اعتبارسنجی خودکار و ثبت آمار لگ‌ها"""
        if not self.patterns:
            raise ValueError(f"استراتژی {self.name} باید حداقل یک الگو داشته باشد.")
        
        # لاگ برای استراتژی‌های بسیار پیچیده جهت دیباگ سریع
        if self.legs_count > 4:
            logger.warning(f"استراتژی {self.name} دارای {self.legs_count} لگ است.")

    @property
    def legs_count(self) -> int:
        """محاسبه خودکار تعداد لگ‌ها بر اساس پترن‌های تعریف شده"""
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
        """سازنده ساده برای تبدیل دیکشنری‌های خام به ساختار شیءگرا"""
        leg_patterns: List[StrategyLegPattern] = []

        for leg in patterns:
            # مدیریت هوشمند OptionType
            opt = leg["option_type"]
            if isinstance(opt, str):
                opt = opt.upper()
                mapping = {"CALL": OptionType.CALL, "PUT": OptionType.PUT, "STOCK": OptionType.STOCK, "S": OptionType.STOCK}
                option_type = mapping.get(opt)
                if not option_type:
                    raise ValueError(f"Unknown option_type: {opt}")
            else:
                option_type = opt

            # مدیریت هوشمند Side
            side_raw = str(leg.get("side", "BUY")).upper()
            side = Side.BUY if side_raw == "BUY" else Side.SELL

            leg_patterns.append(
                StrategyLegPattern(
                    option_type=option_type,
                    side=side,
                    ratio=int(leg.get("ratio", 1)),
                    strike_group=leg.get("strike_group"), # در صورت عدم وجود سهم، None می‌ماند
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
        """تبدیل به دیکشنری جهت خروجی‌های سیستم یا گزارش‌گیری"""
        return {
            "name": self.name,
            "generator_type": self.generator_type.value,
            "legs_count": self.legs_count, # استفاده از property
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

    def __str__(self) -> str:
        return f"StrategyDefinition(name={self.name}, legs={self.legs_count}, type={self.generator_type.value})"