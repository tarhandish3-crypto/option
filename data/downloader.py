# data/downloader.py

"""
دریافت داده از منابع مختلف بازار اختیار معامله ایران

اولویت دانلود:
    1. TSETMC (مستقیم) - بورس تهران
    2. TSETMC (با DNS bypass - Shecan) - در صورت فیلتر بودن
    3. Optionschool24 (API جایگزین)
    4. Local File (آخرین راه)

خروجی: DataFrame با ساختار طولی (Vertical) و ستون‌های استاندارد و کاملاً همگام‌شده
"""

import pandas as pd
import requests
import jdatetime as jd
import dns.resolver
import time
import logging
from typing import Optional

logger = logging.getLogger("OptionScanner.Data.Downloader")


class MarketDownloader:
    """
    دانلودر داده از منابع مختلف با پشتیبانی از DNS bypass و یکسان‌سازی خودکار ستون‌ها
    """
    
    # =====================================================
    # تنظیمات API
    # =====================================================
    
    TSETMC_URL = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0"
    OPTIONSCHOOL24_URL = "https://s3.optionschool24.com/last"
    
    # DNS شکن (Shecan)
    SHE_CAN_DNS = ['178.22.122.100', '185.51.200.2']
    DOMAINS = ['cdn.tsetmc.com', 'ifb.ir']
    
    # =====================================================
    # DNS Bypass
    # =====================================================
    
    @classmethod
    def _get_dns_bypass_ips(cls) -> dict:
        """
        دریافت IP دامنه‌ها با استفاده از DNS شکن
        """
        domain_ip_map = {}
        
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = cls.SHE_CAN_DNS
            resolver.timeout = 5
            resolver.lifetime = 10
            
            for domain in cls.DOMAINS:
                try:
                    ip = resolver.resolve(domain, 'A')[0].to_text()
                    domain_ip_map[domain] = ip
                    logger.debug(f"Resolved {domain} -> {ip}")
                except Exception as e:
                    logger.warning(f"Could not resolve {domain} via Shecan: {e}")
            
            return domain_ip_map
            
        except Exception as e:
            logger.warning(f"DNS bypass setup failed: {e}")
            return {}
    
    @classmethod
    def _create_bypass_session(cls) -> Optional[requests.Session]:
        """
        ایجاد session با DNS bypass برای دور زدن فیلتر
        """
        domain_ip_map = cls._get_dns_bypass_ips()
        
        if not domain_ip_map:
            return None
        
        session = requests.Session()
        original_request = session.request
        
        def custom_request(method, url, *args, **kwargs):
            for domain, ip in domain_ip_map.items():
                if domain in url:
                    url = url.replace(domain, ip)
                    headers = kwargs.get('headers', {})
                    headers['Host'] = domain
                    kwargs['headers'] = headers
                    kwargs['verify'] = False
                    break
            return original_request(method, url, *args, **kwargs)
        
        session.request = custom_request
        return session
    
    # =====================================================
    # روش ۱: TSETMC (مستقیم)
    # =====================================================
    
    @classmethod
    def from_tsetmc_direct(cls) -> pd.DataFrame:
        """
        دریافت داده از بورس تهران به صورت مستقیم
        """
        try:
            logger.info("Fetching data from TSETMC (direct)...")
            response = requests.get(cls.TSETMC_URL, timeout=15)
            response.raise_for_status()
            
            raw_data = response.json().get("instrumentOptMarketWatch", [])
            if not raw_data:
                logger.warning("TSETMC direct returned empty data")
                return pd.DataFrame()
            
            df = pd.json_normalize(raw_data)
            result = cls._melt_tsetmc_to_standard(df)
            
            if not result.empty:
                logger.info(f"TSETMC direct: {len(result)} records loaded")
            return result
            
        except requests.exceptions.Timeout:
            logger.warning("TSETMC direct: timeout")
            return pd.DataFrame()
        except requests.exceptions.ConnectionError:
            logger.warning("TSETMC direct: connection error")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"TSETMC direct failed: {e}")
            return pd.DataFrame()
    
    # =====================================================
    # روش ۲: TSETMC (با DNS bypass)
    # =====================================================
    
    @classmethod
    def from_tsetmc_with_bypass(cls) -> pd.DataFrame:
        """
        دریافت داده از بورس تهران با استفاده از DNS bypass (Shecan)
        """
        try:
            logger.info("Fetching data from TSETMC (with DNS bypass)...")
            
            session = cls._create_bypass_session()
            if session is None:
                logger.warning("DNS bypass not available")
                return pd.DataFrame()
            
            response = session.get(cls.TSETMC_URL, timeout=20)
            response.raise_for_status()
            
            raw_data = response.json().get("instrumentOptMarketWatch", [])
            if not raw_data:
                logger.warning("TSETMC with bypass returned empty data")
                return pd.DataFrame()
            
            df = pd.json_normalize(raw_data)
            result = cls._melt_tsetmc_to_standard(df)
            
            if not result.empty:
                logger.info(f"TSETMC with bypass: {len(result)} records loaded")
            return result
            
        except requests.exceptions.Timeout:
            logger.warning("TSETMC with bypass: timeout")
            return pd.DataFrame()
        except requests.exceptions.ConnectionError:
            logger.warning("TSETMC with bypass: connection error")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"TSETMC with bypass failed: {e}")
            return pd.DataFrame()
    
    # =====================================================
    # روش ۳: Optionschool24
    # =====================================================
    
    @classmethod
    def from_optionschool24(cls) -> pd.DataFrame:
        """
        دریافت داده از Optionschool24 API
        """
        try:
            logger.info("Fetching data from Optionschool24...")
            response = requests.get(cls.OPTIONSCHOOL24_URL, params={"type": 3}, timeout=15)
            response.raise_for_status()
            
            df = pd.DataFrame(response.json())
            if df.empty:
                logger.warning("Optionschool24 returned empty data")
                return pd.DataFrame()
            
            result = cls._normalize_optionschool24(df)
            
            if not result.empty:
                logger.info(f"Optionschool24: {len(result)} records loaded")
            return result
            
        except requests.exceptions.Timeout:
            logger.warning("Optionschool24: timeout")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"Optionschool24 fetch failed: {e}")
            return pd.DataFrame()
    
    # =====================================================
    # روش ۴: Local File (آخرین راه)
    # =====================================================
    
    @classmethod
    def from_local_file(cls, filepath: str = "data/backup.xlsx") -> pd.DataFrame:
        """
        بارگذاری داده از فایل محلی (آخرین راه)
        """
        try:
            from pathlib import Path
            path = Path(filepath)
            if not path.exists():
                return pd.DataFrame()
            
            logger.info(f"Loading from local file: {filepath}")
            df = pd.read_excel(filepath)
            
            if df.empty:
                logger.warning("Local file is empty")
                return pd.DataFrame()
            
            logger.info(f"Local file: {len(df)} records loaded")
            return cls._apply_standard_schema(df)
            
        except Exception as e:
            logger.error(f"Local file load failed: {e}")
            return pd.DataFrame()
    
    # =====================================================
    # مبدل دیتای TSETMC به ساختار استاندارد طولی
    # =====================================================
    
    @classmethod
    def _melt_tsetmc_to_standard(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        تبدیل دیتای خام پهن TSETMC به دیتابیس طولی و استاندارد اسکنر
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # فرآیند پردازش تاریخ سررسید
        if 'endDate' in df.columns:
            df['MaturityDate'] = pd.to_datetime(df['endDate'].astype(str), format='%Y%m%d', errors='coerce')
            try:
                df['MaturityDate_Jalali'] = df['MaturityDate'].apply(
                    lambda d: jd.date.fromgregorian(year=d.year, month=d.month, day=d.day) if pd.notna(d) else None)
            except Exception:
                df['MaturityDate_Jalali'] = df['MaturityDate']
        else:
            df['MaturityDate_Jalali'] = None

        days_col = 'remainedDay' if 'remainedDay' in df.columns else 'daysToMaturity'
        underlying_price = df['pDrCotVal_UA'].astype(float) if 'pDrCotVal_UA' in df.columns else df.get('pClosing_UA', 0.0)

        # تفکیک بخش ردیف‌های Call
        calls = pd.DataFrame({
            'Ticker': df['lVal18AFC_C'],                       # نمونه خروجی: 'ضهرم4023'
            'Name': df['lVal30_C'],                             # نمونه خروجی: 'اختيارخ اهرم-20000...'
            'StrikePrice': df['strikePrice'].astype(float),
            'UnderlyingTicker': df['lval30_UA'],                # نمونه خروجی: 'اهرم'
            'UnderlyingPrice': underlying_price,
            'MaturityDate': df['MaturityDate_Jalali'],
            'DaysToMaturity': df[days_col].fillna(0).astype(int),
            'OpenPositions': df['yesterdayOP_C'].astype(float) if 'yesterdayOP_C' in df.columns else 0.0,
            'Volume': df['qTotTran5J_C'].astype(float) if 'qTotTran5J_C' in df.columns else 0.0,
            'Value': df['notionalValue_C'].astype(float) if 'notionalValue_C' in df.columns else 0.0,
            'LastPrice': df['pDrCotVal_C'].astype(float) if 'pDrCotVal_C' in df.columns else 0.0,
            'ClosePrice': df['pClosing_C'].astype(float) if 'pClosing_C' in df.columns else 0.0,
            'ContractSize': df['contractSize'].astype(float) if 'contractSize' in df.columns else 1000.0,
            'Type': 'Call',
            'BidPrice': df['pMeDem_C'].astype(float) if 'pMeDem_C' in df.columns else 0.0,
            'AskPrice': df['pMeOf_C'].astype(float) if 'pMeOf_C' in df.columns else 0.0,
            'BidVolume': df['qTitMeDem_C'].astype(float) if 'qTitMeDem_C' in df.columns else 0.0,
            'AskVolume': df['qTitMeOf_C'].astype(float) if 'qTitMeOf_C' in df.columns else 0.0,
            'InstrumentCode': df['insCode_C'] if 'insCode_C' in df.columns else '',
            'InstrumentCode-UA': df['uaInsCode'] if 'uaInsCode' in df.columns else '',
        })
        
        # تفکیک بخش ردیف‌های Put
        puts = pd.DataFrame({
            'Ticker': df['lVal18AFC_P'],                       # نمونه خروجی: 'طهرم4023'
            'Name': df['lVal30_P'],                             # نمونه خروجی: 'اختيارف اهرم-20000...'
            'StrikePrice': df['strikePrice'].astype(float),
            'UnderlyingTicker': df['lval30_UA'],
            'UnderlyingPrice': underlying_price,
            'MaturityDate': df['MaturityDate_Jalali'],
            'DaysToMaturity': df[days_col].fillna(0).astype(int),
            'OpenPositions': df['yesterdayOP_P'].astype(float) if 'yesterdayOP_P' in df.columns else 0.0,
            'Volume': df['qTotTran5J_P'].astype(float) if 'qTotTran5J_P' in df.columns else 0.0,
            'Value': df['notionalValue_P'].astype(float) if 'notionalValue_P' in df.columns else 0.0,
            'LastPrice': df['pDrCotVal_P'].astype(float) if 'pDrCotVal_P' in df.columns else 0.0,
            'ClosePrice': df['pClosing_P'].astype(float) if 'pClosing_P' in df.columns else 0.0,
            'ContractSize': df['contractSize'].astype(float) if 'contractSize' in df.columns else 1000.0,
            'Type': 'Put',
            'BidPrice': df['pMeDem_P'].astype(float) if 'pMeDem_P' in df.columns else 0.0,
            'AskPrice': df['pMeOf_P'].astype(float) if 'pMeOf_P' in df.columns else 0.0,
            'BidVolume': df['qTitMeDem_P'].astype(float) if 'qTitMeDem_P' in df.columns else 0.0,
            'AskVolume': df['qTitMeOf_P'].astype(float) if 'qTitMeOf_P' in df.columns else 0.0,
            'InstrumentCode': df['insCode_P'] if 'insCode_P' in df.columns else '',
            'InstrumentCode-UA': df['uaInsCode'] if 'uaInsCode' in df.columns else '',
        })
        
        result = pd.concat([calls, puts], ignore_index=True)
        return cls._apply_standard_schema(result)
    
    # =====================================================
    # مبدل دیتای Optionschool24 به ساختار استاندارد طولی
    # =====================================================
    
    @classmethod
    def _normalize_optionschool24(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        نرمال‌سازی دیتای دریافتی از اپشن اسکول به ساختار شبیه‌سازی شده استاندارد بورس
        """
        if df.empty:
            return df
            
        df = df.copy()
        
        # استخراج امن اولین عنصر از ساختارهای رشته‌ای صَف‌های خرید و فروش (مانند '29503/29004/28500')
        def parse_queue_string(val):
            if pd.isna(val) or val == "":
                return 0.0
            try:
                return float(str(val).split('/')[0]) if '/' in str(val) else float(val)
            except (ValueError, TypeError):
                return 0.0

        def parse_jalali_date(date_str):
            if pd.isna(date_str) or not isinstance(date_str, str):
                return None
            try:
                # جدا کردن سال، ماه و روز از رشته "1405/04/31"
                parts = [int(p) for p in date_str.replace('-', '/').split('/')]
                if len(parts) == 3:
                    return jd.date(parts[0], parts[1], parts[2])
            except Exception as e:
                logger.warning(f"Failed to parse Jalali date string '{date_str}': {e}")
            return None


        normalized = pd.DataFrame({
            'Ticker': df['name'],                                  # نمونه: 'ضهرم4023'
            'Name': df['fname'],                                    # نمونه: 'اختيارخ اهرم-20000...'
            'StrikePrice': df['emal'].astype(float),
            'UnderlyingTicker': df['basis_name'],                   # نمونه: 'اهرم'
            'UnderlyingPrice': df['basis_c'].astype(float),         # قیمت لایو دارایی پایه
            'MaturityDate': df['to_date'].apply(parse_jalali_date),
            'DaysToMaturity': df['day_left_float'].fillna(df['day_left']).astype(int),
            'OpenPositions': df['op'].astype(float) if 'op' in df.columns else 0.0,
            'Volume': df['Tvolume'].astype(float) if 'Tvolume' in df.columns else 0.0,
            'Value': df['Tvalue'].astype(float) if 'Tvalue' in df.columns else 0.0,
            'LastPrice': df['close'].astype(float) if 'close' in df.columns else 0.0,
            'ClosePrice': df['final'].astype(float) if 'final' in df.columns else 0.0,
            'ContractSize': df['size'].astype(float) if 'size' in df.columns else 1000.0,
            'Type': df['type'].apply(lambda t: 'Call' if str(t) == '1' else 'Put'),
            'BidPrice': df['b_price'].apply(parse_queue_string) if 'b_price' in df.columns else 0.0,
            'AskPrice': df['s_price'].apply(parse_queue_string) if 's_price' in df.columns else 0.0,
            'BidVolume': df['b_volume'].apply(parse_queue_string) if 'b_volume' in df.columns else 0.0,
            'AskVolume': df['s_volume'].apply(parse_queue_string) if 's_volume' in df.columns else 0.0,
            'InstrumentCode': df['ins'] if 'ins' in df.columns else '',
            'InstrumentCode-UA': df['co'] if 'co' in df.columns else '',
        })
        
        return cls._apply_standard_schema(normalized)
        
    # =====================================================
    # متد مهندسی اسکیما و کنترل کیفیت نهایی دیتا
    # =====================================================
    
    @staticmethod
    def _apply_standard_schema(df: pd.DataFrame) -> pd.DataFrame:
        """
        تضمین قالب، نوع داده، تعداد و چیدمان ۱۰۰ درصدی ستون‌های خروجی ماژول دانلودر
        """
        standard_cols = [
            'Ticker', 'Name', 'StrikePrice', 'UnderlyingTicker', 'UnderlyingPrice', 
            'MaturityDate', 'DaysToMaturity', 'OpenPositions', 'Volume', 'Value', 
            'LastPrice', 'ClosePrice', 'ContractSize', 'Type', 'BidPrice', 'AskPrice', 
            'BidVolume', 'AskVolume', 'InstrumentCode', 'InstrumentCode-UA'
        ]
        
        # فیلتر ردیف‌های پوچ و خراب
        df = df[df['Ticker'].notna() & (df['Ticker'] != '')]
        
        # پر کردن ستون‌های مفقود شده با مقادیر پیش‌فرض امن جهت جلوگیری از KeyError در ماژول‌های بالادست
        for col in standard_cols:
            if col not in df.columns:
                df[col] = 0.0 if any(p in col for p in ['Price', 'Volume', 'Value', 'Size']) else ''
                
        # قالب‌بندی چیدمان نهایی ستون‌ها بر مبنای آرایه مرجع
        return df.reindex(columns=standard_cols).reset_index(drop=True)
    
    # =====================================================
    # تابع یکپارچه دانلود
    # =====================================================
    
    @classmethod
    def download(cls) -> pd.DataFrame:
        """
        دانلود داده با چرخه کامل و Fallback
        """
        attempt = 0
        
        while True:
            attempt += 1
            logger.info(f"Download attempt {attempt}")
            
            # 1. TSETMC مستقیم
            df = cls.from_tsetmc_direct()
            if not df.empty:
                logger.info(f"Data received from TSETMC direct (attempt {attempt})")
                return df
            
            # 2. TSETMC با DNS bypass
            df = cls.from_tsetmc_with_bypass()
            if not df.empty:
                logger.info(f"Data received from TSETMC with bypass (attempt {attempt})")
                return df
            
            # 3. Optionschool24
            df = cls.from_optionschool24()
            if not df.empty:
                logger.info(f"Data received from Optionschool24 (attempt {attempt})")
                return df
            
            # 4. Local File
            df = cls.from_local_file()
            if not df.empty:
                logger.warning(f"Using local file (attempt {attempt})")
                return df
            
            # همه روش‌ها ناموفق
            logger.warning(f"All methods failed in attempt {attempt}. Retrying in 5 seconds...")
            time.sleep(5)