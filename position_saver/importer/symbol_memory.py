# position_saver/importer/symbol_memory.py
# -*- coding: utf-8 -*-

"""
حافظه‌ی نمادها — ذخیره‌ی قیمت اعمال و سررسید هر نماد.

ساختار فایل symbol_memory.json:
    {
        "ضفزر614": {
            "strike_price": 140000.0,
            "expiry_date": "1405/05/25",
            "contract_size": 1000,
            "option_kind": "CALL",
            "underlying_symbol": "فزر",
            "ins_code": "55395635854601988",
            "ins_code_ua": "8175784894140974",
            "last_updated": "1405/07/21 12:00:00"
        },
        ...
    }
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from core.enums import OptionType


logger = logging.getLogger("PositionSaver.Importer.SymbolMemory")


# ═══════════════════════════════════════════════════
# مسیر فایل
# ═══════════════════════════════════════════════════

_MEMORY_FILE = Path(__file__).parent / "symbol_memory.json"
_cache: Optional[Dict[str, dict]] = None


# ═══════════════════════════════════════════════════
# API اصلی
# ═══════════════════════════════════════════════════

def get_symbol_info(symbol: str) -> Optional[dict]:
    """دریافت اطلاعات ذخیره‌شده‌ی یک نماد"""
    if not symbol:
        return None
    memory = _load()
    return memory.get(str(symbol).strip())


def has_symbol(symbol: str) -> bool:
    """آیا نماد در حافظه موجود است؟"""
    if not symbol:
        return False
    return str(symbol).strip() in _load()


def save_symbol_info(
    symbol: str,
    strike_price: Optional[float] = None,
    expiry_date: Optional[str] = None,
    contract_size: Optional[int] = None,
    option_kind: Optional[OptionType] = None,
    underlying_symbol: Optional[str] = None,
    ins_code: Optional[str] = None,
    ins_code_ua: Optional[str] = None,
) -> bool:
    """
    ذخیره یا به‌روزرسانی اطلاعات یک نماد.

    فقط فیلدهایی که مقدار غیر None دارند به‌روزرسانی می‌شوند.
    فیلدهای قبلی حفظ می‌شوند.
    """
    if not symbol:
        return False

    symbol = str(symbol).strip()
    memory = _load()

    info = memory.get(symbol, {})

    if strike_price is not None and strike_price > 0:
        info["strike_price"] = float(strike_price)

    if expiry_date:
        info["expiry_date"] = str(expiry_date).strip()

    if contract_size is not None and contract_size > 0:
        info["contract_size"] = int(contract_size)

    if option_kind is not None:
        info["option_kind"] = option_kind.name

    if underlying_symbol:
        info["underlying_symbol"] = str(underlying_symbol).strip()

    if ins_code:
        info["ins_code"] = str(ins_code).strip()

    if ins_code_ua:
        info["ins_code_ua"] = str(ins_code_ua).strip()

    info["last_updated"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    memory[symbol] = info
    return _save(memory)


def save_from_trade(trade) -> bool:
    """
    ذخیره‌ی اطلاعات یک TradeRecord در حافظه.
    """
    if trade is None:
        return False

    return save_symbol_info(
        symbol=getattr(trade, "symbol", ""),
        strike_price=getattr(trade, "strike_price", None),
        expiry_date=getattr(trade, "expiry_date", None),
        contract_size=getattr(trade, "contract_size", None),
        option_kind=getattr(trade, "option_kind", None),
        underlying_symbol=getattr(trade, "underlying_symbol", None),
        ins_code=getattr(trade, "ins_code", None),
        ins_code_ua=getattr(trade, "ins_code_ua", None),
    )


def save_bulk(symbol_infos: Dict[str, dict]) -> bool:
    """ذخیره‌ی گروهی اطلاعات چند نماد"""
    if not symbol_infos:
        return False

    memory = _load()
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    for symbol, info in symbol_infos.items():
        if not symbol or not info:
            continue
        s = str(symbol).strip()
        existing = memory.get(s, {})
        existing.update({k: v for k, v in info.items()
                         if v is not None})
        existing["last_updated"] = now
        memory[s] = existing

    return _save(memory)


def get_all() -> Dict[str, dict]:
    """دریافت همه‌ی اطلاعات"""
    return dict(_load())


def get_count() -> int:
    """تعداد نمادهای ذخیره‌شده"""
    return len(_load())


def clear_symbol(symbol: str) -> bool:
    """حذف اطلاعات یک نماد"""
    if not symbol:
        return False
    memory = _load()
    symbol = str(symbol).strip()
    if symbol in memory:
        del memory[symbol]
        return _save(memory)
    return False


def clear_all() -> bool:
    """حذف همه‌ی اطلاعات"""
    return _save({})


def export_to_dict() -> dict:
    """صادرات برای بک‌آپ"""
    return dict(_load())


def import_from_dict(data: dict) -> bool:
    """واردات از بک‌آپ (ادغام می‌کند)"""
    if not isinstance(data, dict):
        return False
    return save_bulk(data)


# ═══════════════════════════════════════════════════
# داخلی
# ═══════════════════════════════════════════════════

def _load() -> Dict[str, dict]:
    """بارگذاری از فایل (با cache)"""
    global _cache
    if _cache is not None:
        return _cache

    if not _MEMORY_FILE.exists():
        _cache = {}
        return _cache

    try:
        with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            _cache = {}
            return _cache
        _cache = data
        logger.info(
            f"Loaded {len(_cache)} symbols from memory")
        return _cache
    except Exception as e:
        logger.warning(f"Load symbol memory failed: {e}")
        _cache = {}
        return _cache


def _save(data: Dict[str, dict]) -> bool:
    """
    ذخیره‌ی اتمیک در فایل.

    ✅ FIX: handle os.replace failure در ویندوز
    """
    global _cache
    temp_path = str(_MEMORY_FILE) + ".tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass

        try:
            os.replace(temp_path, str(_MEMORY_FILE))
        except PermissionError:
            # ویندوز: اگر فایل مقصد قفل باشد، تلاش دوباره
            logger.warning(
                "PermissionError on os.replace — "
                "removing target and retrying")
            try:
                if _MEMORY_FILE.exists():
                    os.remove(str(_MEMORY_FILE))
                os.rename(temp_path, str(_MEMORY_FILE))
            except Exception as e2:
                logger.exception(f"Retry failed: {e2}")
                raise

        _cache = data
        logger.info(f"Saved {len(data)} symbols to memory")
        return True
    except Exception as e:
        logger.exception(f"Save symbol memory failed: {e}")
        # پاکسازی temp
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def _invalidate_cache():
    """پاکسازی cache (برای تست)"""
    global _cache
    _cache = None


__all__ = [
    "get_symbol_info",
    "has_symbol",
    "save_symbol_info",
    "save_from_trade",
    "save_bulk",
    "get_all",
    "get_count",
    "clear_symbol",
    "clear_all",
    "export_to_dict",
    "import_from_dict",
]