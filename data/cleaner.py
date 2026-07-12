# data/cleaner.py

"""
پاکسازی و پیش‌پردازش داده‌های بازار اختیار معامله
"""

import pandas as pd
import numpy as np
import logging
from core.enums import OptionType, OptionStatus
from config import MIN_VOLUME, MAX_SPREAD_PCT, DaysToMaturity

logger = logging.getLogger("OptionScanner.Data.Cleaner")


class DataCleaner:
    """
    پاکسازی و پیش‌پردازش داده‌های بازار
    """

    # =====================================================
    # پاکسازی اصلی
    # =====================================================

    @staticmethod
    def clean(df: pd.DataFrame) -> pd.DataFrame:
        """
        پاکسازی کامل داده
        """

        original_count = len(df)
        logger.info(f"Starting cleaning with {original_count} records")

        df = df.copy()

        # 1. فیلتر مقادیر نامعتبر
        df = DataCleaner._filter_invalid(df)

        # 2. فیلتر حجم (اختیاری)
        min_volume = MIN_VOLUME
        df = DataCleaner._filter_volume(df, min_volume)

        # 3. مدیریت و حذف صف‌های غیرقابل معامله (تعداد یا حجم صفر)
        df = DataCleaner._handle_queues(df)

        # 4. فیلتر سررسید
        df = DataCleaner._filter_maturity(df, DaysToMaturity)

        # DEBUG_SYMBOls = ['اهرم', 'اخابر']
        # DEBUG_SYMBOls = ['اهرم']
        # df = df[df['UnderlyingTicker'].isin(DEBUG_SYMBOls)]
        df = df[df['Ticker'].isin(['ضهرم4024', 'ضهرم4033', 'طهرم4032'])]

        after_debug = len(df)
        removed_count = original_count - after_debug
        logger.info(
            f"Cleaning complete: {len(df)} records kept, {removed_count} removed")

        return df

    # =====================================================
    # مراحل پاکسازی
    # =====================================================

    @staticmethod
    def _filter_invalid(df: pd.DataFrame) -> pd.DataFrame:
        """فیلتر مقادیر نامعتبر"""
        before = len(df)

        if 'StrikePrice' in df.columns:
            df = df[df['StrikePrice'] > 1]

        if 'LastPrice' in df.columns:
            df = df[df['LastPrice'] > 1]

        if before - len(df) > 0:
            logger.debug(
                f"Removed {before - len(df)} rows with invalid values")

        return df

    @staticmethod
    def _handle_queues(df: pd.DataFrame) -> pd.DataFrame:
        """
        مدیریت و فیلتر صف‌های خرید و فروش.
        """
        before_count = len(df)

        # تبدیل نوع داده به float جهت مقایسه امن
        bid_p = df['BidPrice'].values.astype(float)
        bid_v = df['BidVolume'].values.astype(float)
        ask_p = df['AskPrice'].values.astype(float)
        ask_v = df['AskVolume'].values.astype(float)

        # ✅ ۱. حذف قراردادهای کاملاً مرده (صف خرید و فروش هر دو صفر)
        dead_market = (bid_p == 0) & (ask_p == 0)

        # ✅ ۲. حذف صف‌های یک‌طرفه فاقد اعتبار (مانند نمونه ارسالی شما: قیمت عرضه هست اما تقاضا حجم و تعدادش صفر است)
        # صف خرید معلق (بدون خریدار واقعی) یا صف فروش معلق (بدون فروشنده واقعی)
        empty_bid = (bid_p == 0) | (bid_v == 0)
        empty_ask = (ask_p == 0) | (ask_v == 0)

        # قراردادهایی که فاقد هرگونه موقعیت معامله معتبر در یکی از طرفین اصلی هستند، نگهداری نمی‌شوند
        invalid_queues = dead_market | empty_bid | empty_ask

        # فیلتر کردن و نگه‌داشتن ردیف‌های معتبر
        df = df[~invalid_queues].reset_index(drop=True)

        removed = before_count - len(df)
        if removed > 0:
            logger.debug(
                f"Removed {removed} contracts due to empty/invalid order book queues (0 volume/price rows).")

        return df

    @staticmethod
    def _filter_maturity(df: pd.DataFrame, min_days: int = 2) -> pd.DataFrame:
        """فیلتر سررسید"""
        if 'DaysToMaturity' in df.columns:
            before = len(df)
            df = df[df['DaysToMaturity'] > min_days]
            if before - len(df) > 0:
                logger.debug(
                    f"Removed {before - len(df)} contracts with <= {min_days} days")
        return df

    @staticmethod
    def _filter_volume(df: pd.DataFrame, min_volume: int = 1) -> pd.DataFrame:
        """فیلتر حجم معاملات"""
        if 'Volume' in df.columns:
            before = len(df)
            df = df[df['Volume'] >= min_volume]
            if before - len(df) > 0:
                logger.debug(
                    f"Removed {before - len(df)} rows with low volume")
        return df

    # =====================================================
    # ستون‌های مشتق شده
    # =====================================================

    @staticmethod
    def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        اضافه کردن ستون‌های مشتق شده با روش برداری ایمن
        """
        if df.empty:
            return df

        df = df.copy()

        # 1. ارزش ذاتی (Intrinsic Value)
        if all(col in df.columns for col in ['UnderlyingPrice', 'StrikePrice', 'Type']):
            S = df['UnderlyingPrice'].values.astype(float)
            K = df['StrikePrice'].values.astype(float)
            is_call = (df['Type'] == OptionType.CALL).values

            df['IntrinsicValue'] = np.where(
                is_call, np.maximum(S - K, 0), np.maximum(K - S, 0))
            df['IntrinsicValue'] = df['IntrinsicValue'].fillna(0)

        # 2. قیمت میانی (Mid Price)
        if all(col in df.columns for col in ['BidPrice', 'AskPrice', 'LastPrice']):
            bid = df['BidPrice'].values.astype(float)
            ask = df['AskPrice'].values.astype(float)
            last = df['LastPrice'].values.astype(float)

            mid = (bid + ask) / 2
            df['MidPrice'] = np.where(
                (mid <= 0) | np.isnan(mid), last, mid)
            df['MidPrice'] = np.nan_to_num(df['MidPrice'], nan=0.0)

        # 3. ارزش زمانی (Time Value)
        if all(col in df.columns for col in ['MidPrice', 'IntrinsicValue']):
            df['TimeValue'] = np.maximum(
                df['MidPrice'].values - df['IntrinsicValue'].values, 0)
            df['TimeValue'] = np.nan_to_num(df['TimeValue'], nan=0.0)

        # 4. نسبت Moneyness و وضعیت اختیار
        if all(col in df.columns for col in ['UnderlyingPrice', 'StrikePrice', 'Type']):
            S = df['UnderlyingPrice'].values.astype(float)
            K = df['StrikePrice'].values.astype(float)
            is_call = (df['Type'] == OptionType.CALL).values

            S_safe = np.where(S <= 0, np.nan, S)

            df['Moneyness'] = np.where(is_call, S / K, K / S_safe)
            df['Moneyness'] = np.nan_to_num(df['Moneyness'], 1.0)

            conditions = [
                (df['Type'] == OptionType.CALL) & (
                    df['UnderlyingPrice'] > df['StrikePrice']),
                (df['Type'] == OptionType.PUT) & (
                    df['UnderlyingPrice'] < df['StrikePrice']),
                (df['UnderlyingPrice'] == df['StrikePrice']),
                (df['Type'] == OptionType.CALL) & (
                    df['UnderlyingPrice'] < df['StrikePrice']),
                (df['Type'] == OptionType.PUT) & (
                    df['UnderlyingPrice'] > df['StrikePrice'])
            ]
            choices = [
                OptionStatus.ITM.value,
                OptionStatus.ITM.value,
                OptionStatus.ATM.value,
                OptionStatus.OTM.value,
                OptionStatus.OTM.value
            ]
            df['OptionStatus'] = np.select(
                conditions, choices, default='Unknown')

        # 5. درصد اسپرد
        if all(col in df.columns for col in ['BidPrice', 'AskPrice']):
            bid = df['BidPrice'].values.astype(float)
            ask = df['AskPrice'].values.astype(float)

            mid = (bid + ask) / 2
            mid = np.where(mid <= 0, 1.0, mid)

            df['SpreadPct'] = np.where(
                (bid > 0) & (ask > 0),
                (ask - bid) / mid, 1.0)
            df['SpreadPct'] = np.nan_to_num(df['SpreadPct'], 1.0)

        # 6. نسبت حق بیمه به ارزش ذاتی
        if all(col in df.columns for col in ['LastPrice', 'IntrinsicValue']):
            last = df['LastPrice'].values.astype(float)
            intrinsic = df['IntrinsicValue'].values.astype(float)

            intrinsic_safe = np.where(intrinsic <= 0, np.nan, intrinsic)
            df['PremiumOverIntrinsic'] = np.where(
                intrinsic > 0, last / intrinsic_safe, 0)
            df['PremiumOverIntrinsic'] = np.nan_to_num(
                df['PremiumOverIntrinsic'], nan=0.0)

        logger.debug(f"Added derived columns successfully")

        return df
