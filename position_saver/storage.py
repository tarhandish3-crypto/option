# position_saver/storage.py
# -*- coding: utf-8 -*-

import json
import os
from typing import List

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType, PositionStatus,)
from core.enums import OptionType


class PositionStorage:
    """
    ذخیره‌سازی و بارگذاری موقعیت‌ها در فایل JSON.
    مسیر پیش‌فرض: پوشه position_saver/positions_data.json (مسیر مطلق).
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DEFAULT_FILE = os.path.join(BASE_DIR, "positions_data.json")

    def __init__(self, filepath: str = None):
        self.filepath = filepath if filepath else self.DEFAULT_FILE

    # =====================================================
    # ذخیره و بارگذاری
    # =====================================================

    def save_positions(self, positions: List[StrategyPosition]) -> bool:
        """ذخیره اتمیک لیست موقعیت‌ها در JSON"""
        try:
            data = [pos.to_dict() for pos in positions]
            temp_path = self.filepath + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            os.rename(temp_path, self.filepath)
            return True
        except Exception as e:
            print(f"[PositionStorage] Save failed: {e}")
            return False

    def load_positions(self) -> List[StrategyPosition]:
        """بارگذاری موقعیت‌ها از JSON"""
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [StrategyPosition.from_dict(item) for item in data]
        except Exception as e:
            print(f"[PositionStorage] Load failed: {e}")
            return []

    # =====================================================
    # پارسر اکسل کارگزاری
    # =====================================================

    @staticmethod
    def parse_broker_excel(file_path: str) -> List[StrategyPosition]:
        """
        پارسر انعطاف‌پذیر اکسل خروجی کارگزاری‌ها.
        از ستون‌های متداول فارسی استفاده می‌کند.
        """
        try:
            import pandas as pd
        except ImportError:
            print("[PositionStorage] pandas is required for Excel import")
            return []

        imported: List[StrategyPosition] = []
        try:
            df = pd.read_excel(file_path)
            df.columns = [str(col).strip() for col in df.columns]

            for _, row in df.iterrows():
                symbol = str(row.get("نماد", row.get("نام نماد", ""))).strip()
                if not symbol:
                    continue

                qty = int(row.get("حجم باز", row.get(
                    "تعداد", row.get("مانده", 0))))
                price = float(row.get("قیمت متوسط", row.get(
                    "قیمت خرید", row.get("قیمت", 0))))
                side_str = str(row.get("موقعیت", row.get("نوع معامله", "buy")))

                try:
                    leg_type = LegType.from_value(side_str)
                except ValueError:
                    leg_type = LegType.BUY

                # تشخیص نوع اختیار از نماد
                if symbol.startswith("ض"):
                    option_kind = OptionType.CALL
                    is_option = True
                elif symbol.startswith("ط"):
                    option_kind = OptionType.PUT
                    is_option = True
                else:
                    option_kind = OptionType.STOCK
                    is_option = False

                leg = OptionLeg(
                    symbol=symbol,
                    is_option=is_option,
                    option_kind=option_kind,
                    leg_type=leg_type,
                    quantity=abs(qty),
                    entry_price=price,
                    current_price=price,
                    contract_size=1000 if is_option else 1,
                )

                pos = StrategyPosition(
                    strategy_name="Imported",
                    underlying_symbol=symbol[:4] if len(
                        symbol) >= 4 else symbol,
                    execution_date=pd.Timestamp.now().strftime("%Y/%m/%d"),
                    status=PositionStatus.OPEN,
                    legs=[leg],
                )
                imported.append(pos)
        except Exception as e:
            print(f"[PositionStorage] Excel parse failed: {e}")

        return imported
