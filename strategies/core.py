# strategies/core.py

from __future__ import annotations

import importlib
import pkgutil
import logging
from typing import Dict, Optional, List

from strategies.base import StrategyDefinition, GeneratorType

logger = logging.getLogger("OptionScanner.Strategies.Core")


# =====================================================
# رجیستری استراتژی‌ها
# =====================================================

_strategies: Dict[str, StrategyDefinition] = {}
_loaded = False


def _load_strategies():
    """بارگذاری پویا از فایل‌های definitions"""
    global _loaded
    
    if _loaded:
        return
    
    try:
        import strategies.definitions as defs_module
        
        loaded_count = 0
        for _, name, _ in pkgutil.iter_modules(defs_module.__path__):
            try:
                imported_module = importlib.import_module(f"strategies.definitions.{name}")
                
                if hasattr(imported_module, "DEFINITION"):
                    strategy = getattr(imported_module, "DEFINITION")
                    _strategies[strategy.name] = strategy
                    loaded_count += 1
                    logger.debug(f"Loaded strategy: {strategy.name}")
                else:
                    logger.warning(f"No DEFINITION found in {name}.py")
            except Exception as e:
                logger.warning(f"Failed to load strategy {name}: {e}")
        
        _loaded = True
        logger.info(f"Loaded {loaded_count} strategies")
        
    except ImportError as e:
        logger.error(f"Could not import strategies.definitions: {e}")
        _loaded = True


def get_strategy(name: str) -> Optional[StrategyDefinition]:
    """دریافت استراتژی بر اساس نام"""
    _load_strategies()
    return _strategies.get(name)


def get_all_strategies() -> Dict[str, StrategyDefinition]:
    """دریافت همه استراتژی‌ها"""
    _load_strategies()
    return _strategies.copy()


def get_strategy_names() -> List[str]:
    """دریافت لیست نام همه استراتژی‌ها"""
    _load_strategies()
    return list(_strategies.keys())


def get_strategies_by_generator(generator_type: GeneratorType) -> List[StrategyDefinition]:
    """دریافت استراتژی‌ها بر اساس نوع Generator"""
    _load_strategies()
    return [s for s in _strategies.values() if s.generator_type == generator_type]


def register_strategy(strategy: StrategyDefinition):
    """ثبت استراتژی جدید (در زمان اجرا)"""
    _strategies[strategy.name] = strategy
    logger.info(f"Registered strategy: {strategy.name}")


def reload_strategies():
    """بارگذاری مجدد استراتژی‌ها (برای زمان اجرا)"""
    global _strategies, _loaded
    _strategies.clear()
    _loaded = False
    _load_strategies()