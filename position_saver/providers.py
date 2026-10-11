# position_saver/providers.py
# -*- coding: utf-8 -*-

"""
Provider Registry — نقطه‌ی مرکزی برای توابعی که از برنامه‌ی مادر می‌آیند.

این ماژول هیچ import داخلی ندارد و از همه‌جا قابل import است
بدون خطر circular import.
"""

import logging
from typing import Optional, Callable, Any

logger = logging.getLogger("PositionSaver.Providers")


# ═══════════════════════════════════════════════════
# Snapshot Provider
# ═══════════════════════════════════════════════════

_snapshot_provider: Optional[Callable] = None


def set_snapshot_provider(provider: Callable) -> None:
    global _snapshot_provider
    _snapshot_provider = provider
    logger.info("Snapshot provider registered")


def get_market_snapshot(use_cache: bool = True,
                        force_refresh: bool = False) -> Any:
    if _snapshot_provider is not None:
        try:
            return _snapshot_provider(
                use_cache=use_cache, force_refresh=force_refresh)
        except Exception as e:
            logger.exception(f"Snapshot provider failed: {e}")
            return None
    try:
        from data.manager import get_market_snapshot as _gms
        return _gms(use_cache=use_cache, force_refresh=force_refresh)
    except ImportError:
        return None


# ═══════════════════════════════════════════════════
# Bale Provider
# ═══════════════════════════════════════════════════

_bale_provider: Optional[Callable] = None


def set_bale_provider(provider: Callable) -> None:
    global _bale_provider
    _bale_provider = provider
    logger.info("Bale provider registered")


def get_bale_notifier() -> Any:
    if _bale_provider is not None:
        try:
            return _bale_provider()
        except Exception as e:
            logger.exception(f"Bale provider failed: {e}")
            return None
    try:
        from alerts.bale_notifier import BaleNotifier
        return BaleNotifier()
    except ImportError:
        return None


# ═══════════════════════════════════════════════════
# Settings Provider
# ═══════════════════════════════════════════════════

_settings_provider: Optional[Callable] = None


def set_settings_provider(provider: Callable) -> None:
    global _settings_provider
    _settings_provider = provider
    logger.info("Settings provider registered")


def get_setting(key: str, *args, default: Any = None) -> Any:
    if _settings_provider is not None:
        try:
            return _settings_provider(key, *args)
        except Exception:
            pass
    try:
        from config import get_commission_rate
        if key == "commission":
            market, asset_type, is_buy = args[:3]
            return get_commission_rate(market, asset_type, is_buy)
    except (ImportError, ValueError, IndexError):
        pass
    if key == "commission":
        asset_type = args[1] if len(args) > 1 else None
        is_buy = args[2] if len(args) > 2 else True
        if asset_type == "option":
            return 0.001
        return 0.003712 if is_buy else 0.0088
    return default


def get_commission_rate(market: str, asset_type: str,
                        is_buy: bool) -> float:
    rate = get_setting("commission", market, asset_type, is_buy)
    return float(rate) if rate is not None else 0.001