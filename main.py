# main.py
# -*- coding: utf-8 -*-

"""
ماژول اصلی سیستم اسکنر (Main Executive Module) - نسخه اختصاصی UI
این ماژول پنجره برنامه را فوراً لود کرده و پردازش‌های سنگین را به زمان اجرا موکول می‌کند.
"""

import sys
import time
import logging
import gc
import threading
import sqlite3
from datetime import datetime
from typing import Optional, Callable, List, Any, Dict, Tuple
import json
from dataclasses import dataclass

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

import config
from data.manager import DataManager
from engine.scanner_engine import ScannerEngine
from reports.excel_exporter import ExcelExporter
from reports.chart_plotter import ChartPlotter
from scoring.ranker import OpportunityRanker, RankingProfile
from analytics.risk_engine import RiskEngine
from filters.strategy_filters import apply_strategy_filter
from ui.main_window import MainWindow
from ui.settings_manager import settings_manager
from ui import theme as ui_theme

logger = logging.getLogger("OptionScanner.Main")


# =====================================================
# مدل داده کش
# =====================================================

@dataclass
class ScanCacheEntry:
    """ورودی کش برای نتایج اسکن"""
    timestamp: datetime
    results: List[Any]
    scan_duration: float
    total_opportunities: int
    filters_used: Dict[str, Any]

    def is_expired(self, ttl_seconds: int = 60) -> bool:
        return (datetime.now() - self.timestamp).total_seconds() > ttl_seconds


# =====================================================
# تنظیمات لاگینگ
# =====================================================

def setup_logging() -> None:
    """تنظیم متمرکز لاگ‌ها"""
    log_dir = config.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "scanner.log", encoding="utf-8")
        ]
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# =====================================================
# موتور اصلی اسکنر (مخصوص تعامل با UI)
# =====================================================

class OptionScanner:
    """
    موتور پردازش اسکنر - طراحی‌شده برای لود فوری UI و اجرای Lazy پردازش‌ها
    """

    __slots__ = (
        'is_running', 'data_manager', 'ranker', 'excel_exporter', 
        'chart_plotter', '_cache', '_cache_ttl', '_scan_timeout', 
        '_db_enabled', '_db_path', '_user_filters', '_cancel_event', 
        '_db_lock', '_stats_lock', '_total_scans', '_total_opportunities', 
        '_last_scan_time', '_is_initialized'
    )

    def __init__(self):
        # تنظیمات سبک و سریع برای عدم معطل کردن UI
        self.is_running = True
        self._is_initialized = False
        self._cache_ttl = config.CACHE_TTL_SECONDS
        self._scan_timeout = 300
        self._cache: Optional[ScanCacheEntry] = None
        self._cancel_event = threading.Event()
        self._db_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        
        self._total_scans = 0
        self._total_opportunities = 0
        self._last_scan_time: Optional[datetime] = None

        self._db_enabled = False  # دیتابیس SQLite در این نسخه غیرفعال است
        self._db_path = config.DATA_DIR / "scans.db"
        self._user_filters: Dict[str, Any] = {}

        # متغیرهای سنگین را در init فقط تعریف می‌کنیم
        self.data_manager = None
        self.ranker = None
        self.excel_exporter = None
        self.chart_plotter = None

    def _lazy_init(self) -> None:
        """بارگذاری اولیه کدهای سنگین فقط در اولین اجرا (داخل نخ اسکن)"""
        if self._is_initialized:
            return

        logger.info("⚙️ در حال بارگذاری اولیه ماژول‌ها و ابزارها...")

        if self._db_enabled:
            self._init_database()

        self._load_user_filters()

        # بارگذاری استراتژی‌ها
        from strategies.core import _load_strategies
        _load_strategies()

        # ساخت مدیر داده و ابزارها
        self.data_manager = DataManager(
            cache_dir=str(config.CACHE_DIR),
            use_cache=True,
            ttl_seconds=config.CACHE_TTL_SECONDS
        )

        profile_map = {
            "conservative": RankingProfile.CONSERVATIVE,
            "balanced": RankingProfile.BALANCED,
            "aggressive": RankingProfile.AGGRESSIVE,
            "income": RankingProfile.INCOME,
            "volatility": RankingProfile.VOLATILITY,
        }
        profile_name = config.RANKING_CONFIG.get("default_profile", "balanced")
        profile = profile_map.get(profile_name, RankingProfile.BALANCED)

        self.ranker = OpportunityRanker(default_profile=profile)
        self.excel_exporter = ExcelExporter(output_dir=str(config.OUTPUT_DIR))
        self.chart_plotter = ChartPlotter(output_dir=str(config.CHARTS_DIR))

        self._is_initialized = True
        logger.info("✅ Engine fully initialized in background thread")

    # =====================================================
    # مدیریت دیتابیس و فیلترها
    # =====================================================

    def _init_database(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._db_lock:
                with sqlite3.connect(str(self._db_path), timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS scan_results (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            total_opportunities INTEGER,
                            scan_duration REAL,
                            filters_used TEXT
                        )
                    """)
                    conn.commit()
        except Exception as e:
            logger.warning(f"Database init failed: {e}")
            self._db_enabled = False

    def _save_scan_to_db(self, results: List[Any], duration: float) -> None:
        if not self._db_enabled:
            return
        try:
            with self._db_lock:
                with sqlite3.connect(str(self._db_path), timeout=10.0) as conn:
                    cursor = conn.cursor()
                    filters_json = json.dumps(self._user_filters, ensure_ascii=False)
                    cursor.execute("""
                        INSERT INTO scan_results 
                        (timestamp, total_opportunities, scan_duration, filters_used)
                        VALUES (?, ?, ?, ?)
                    """, (datetime.now().isoformat(), len(results), duration, filters_json))
                    conn.commit()
        except Exception as e:
            logger.warning(f"⚠️ Failed to save to database: {e}")

    def _load_user_filters(self) -> None:
        filters_path = config.BASE_DIR / "user_filters.json"
        if filters_path.exists():
            try:
                with open(filters_path, 'r', encoding='utf-8') as f:
                    self._user_filters = json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load user filters: {e}")

    def update_user_filters(self, new_filters: Dict[str, Any]) -> None:
        self._user_filters.update(new_filters)
        filters_path = config.BASE_DIR / "user_filters.json"
        try:
            with open(filters_path, 'w', encoding='utf-8') as f:
                json.dump(self._user_filters, f, indent=4, ensure_ascii=False)
            self.invalidate_cache()
            logger.info(f"✅ User filters updated: {len(self._user_filters)} filters active")
        except Exception as e:
            logger.error(f"❌ Failed to save user filters: {e}")

    def get_user_filters(self) -> Dict[str, Any]:
        return self._user_filters.copy()

    def apply_user_filters(self, opportunities: List[Any]) -> List[Any]:
        if not opportunities or not self._user_filters:
            return opportunities

        filtered = []
        min_score = self._user_filters.get('min_score')
        max_risk = self._user_filters.get('max_risk')
        min_profit = self._user_filters.get('min_profit')

        for opp in opportunities:
            score = getattr(opp, 'score', getattr(opp, 'rank_score', 0))
            if min_score is not None and score < min_score:
                continue

            risk = getattr(opp, 'risk', getattr(opp, 'max_risk', 0))
            if max_risk is not None and risk > max_risk:
                continue

            profit = getattr(opp, 'profit', getattr(opp, 'expected_profit', 0))
            if min_profit is not None and profit < min_profit:
                continue

            filtered.append(opp)

        return filtered

    def get_available_symbols(self) -> List[str]:
        if not self._is_initialized and self.data_manager is None:
            if hasattr(config, 'SYMBOL_INFO'):
                return sorted(list(config.SYMBOL_INFO.keys()))
            return []

        try:
            snapshot = self.data_manager.get_market_snapshot(
                force_refresh=False, 
                calc_advanced=False
            )
            if snapshot and hasattr(snapshot, 'option_contracts'):
                symbols = set()
                for contract in snapshot.option_contracts:
                    symbol = getattr(contract, 'underlying_symbol', getattr(contract, 'symbol', None))
                    if symbol:
                        symbols.add(symbol)
                return sorted(list(symbols))
        except Exception as e:
            logger.warning(f"Failed to get available symbols: {e}")
        
        return sorted(list(getattr(config, 'SYMBOL_INFO', {}).keys()))

    def set_log_level(self, level: str) -> bool:
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR
        }
        if level in level_map:
            logging.getLogger().setLevel(level_map[level])
            logging.getLogger("OptionScanner").setLevel(level_map[level])
            logger.info(f"Log level changed to {level}")
            return True
        return False

    def get_log_level(self) -> str:
        level = logging.getLogger().getEffectiveLevel()
        for name, value in logging._nameToLevel.items():
            if value == level:
                return name
        return "INFO"

    def get_statistics(self) -> Dict[str, Any]:
        with self._stats_lock:
            scans = self._total_scans
            opps = self._total_opportunities
            last_time = self._last_scan_time.isoformat() if self._last_scan_time else None

        return {
            'total_scans': scans,
            'total_opportunities': opps,
            'avg_opportunities_per_scan': opps / max(1, scans),
            'cache_hit': self._cache is not None and not self._cache.is_expired(self._cache_ttl),
            'last_scan_time': last_time,
            'active_filters': len(self._user_filters),
            'db_enabled': self._db_enabled,
            'cache_ttl': self._cache_ttl,
            'scan_timeout': self._scan_timeout,
            'is_running': self.is_running
        }

    def invalidate_cache(self) -> None:
        self._cache = None

    # =====================================================
    # منطق اجرای اسکن (ورود واقعی فقط با کلیک کاربر یا اتوماتیک)
    # =====================================================

    def run_scan_with_progress(
        self, 
        progress_callback: Optional[Callable[[int, str], None]] = None,
        stop_check_callback: Optional[Callable[[], bool]] = None,
        force_refresh: bool = True
    ) -> List[Any]:

        self._cancel_event.clear()

        def update_progress(percent: int, msg: str):
            if progress_callback:
                progress_callback(percent, msg)

        def is_stopped() -> bool:
            external_stop = stop_check_callback() if stop_check_callback else False
            return external_stop or self._cancel_event.is_set() or not self.is_running

        # کش
        if not force_refresh and self._cache and not self._cache.is_expired(self._cache_ttl):
            update_progress(100, "استفاده از نتایج ذخیره‌شده")
            return self._cache.results

        scan_output = {"results": None, "duration": 0.0, "error": None}

        def target():
            try:
                # بارگذاری موارد سنگین در زمینه (برای بار اول)
                self._lazy_init()
                
                res, dur = self._execute_scan(update_progress, is_stopped, force_refresh)
                scan_output["results"] = res
                scan_output["duration"] = dur
            except Exception as e:
                scan_output["error"] = e

        thread = threading.Thread(target=target, daemon=True, name="ScannerThread")
        thread.start()
        thread.join(timeout=self._scan_timeout)

        if thread.is_alive():
            self._cancel_event.set()
            logger.error(f"⏱Scan timed out after {self._scan_timeout} seconds!")
            update_progress(0, "زمان اسکن به پایان رسید")
            return []

        if scan_output["error"]:
            logger.error(f"Scan error: {scan_output['error']}", exc_info=True)
            update_progress(0, f"خطا: {str(scan_output['error'])}")
            return []

        if self._cancel_event.is_set():
            update_progress(0, " اسکن متوقف شد")
            return []

        result = scan_output["results"] if scan_output["results"] is not None else []
        duration = scan_output["duration"]

        original_count = len(result)
        result = self.apply_user_filters(result)
        
        with self._stats_lock:
            self._total_scans += 1
            self._total_opportunities += len(result)
            self._last_scan_time = datetime.now()
        
        if len(result) < original_count:
            logger.info(f" Filters applied: {original_count} → {len(result)} opportunities")
        
        self._save_scan_to_db(result, duration)
        self._cache = ScanCacheEntry(
            timestamp=datetime.now(),
            results=result,
            scan_duration=duration,
            total_opportunities=len(result),
            filters_used=self._user_filters.copy()
        )

        update_progress(100, f" اسکن کامل شد - {len(result)} فرصت یافت شد")
        gc.collect()
        return result

    def _execute_scan(
        self,
        update_progress: Callable[[int, str], None],
        is_stopped: Callable[[], bool],
        force_refresh: bool
    ) -> Tuple[List[Any], float]:
        
        from ui.settings_manager import settings_manager

        start_time = time.time()

        update_progress(10, "🔍 دریافت اطلاعات بازار...")
        if is_stopped(): return [], 0.0

        calc_advanced = config.FEATURE_FLAGS.get("calculate_greeks", True)
        snapshot = self.data_manager.get_market_snapshot(
            force_refresh=force_refresh, 
            calc_advanced=calc_advanced
        )

        if is_stopped() or not snapshot or not getattr(snapshot, 'option_contracts', None):
            return [], 0.0

        # ── فیلتر نمادهای بلاک‌شده توسط کاربر ─────────────────────
        excluded = set(settings_manager.get_excluded_symbols())
        if excluded:
            before_contracts = len(snapshot.option_contracts)
            before_underlyings = len(snapshot.underlying_assets)

            # حذف از قراردادهای اختیار
            snapshot.option_contracts = [
                c for c in snapshot.option_contracts
                if getattr(c, 'underlying_ticker', '') not in excluded
            ]
            # حذف از دارایی‌های پایه — این کلید است که scanner loop نزند
            for sym in excluded:
                snapshot.underlying_assets.pop(sym, None)

            snapshot.build_indices()

            logger.info(
                f" نمادهای بلاک‌شده: {excluded} — "
                f"قراردادها: {before_contracts}→{len(snapshot.option_contracts)} | "
                f"نمادهای پایه: {before_underlyings}→{len(snapshot.underlying_assets)}"
            )
        # ─────────────────────────────────────────────────────────────

        update_progress(30, f"📊 تحلیل {len(snapshot.option_contracts)} قرارداد...")
        engine = ScannerEngine(snapshot=snapshot)
        scan_result = engine.execute_full_scan()

        if is_stopped() or not scan_result or not getattr(scan_result, 'opportunities', None):
            return [], 0.0

        update_progress(60, "🔧 اعمال فیلترها و محاسبه ریسک...")
        filtered_opportunities = [
            opp for opp in scan_result.opportunities
            if opp is not None and apply_strategy_filter(opp)
        ]

        if is_stopped() or not filtered_opportunities:
            return [], 0.0

        enriched_opportunities = []
        for opp in filtered_opportunities:
            if is_stopped(): return [], 0.0
            try:
                enriched_opportunities.append(RiskEngine.evaluate_opportunity(opp))
            except Exception:
                enriched_opportunities.append(opp)

        update_progress(85, "🏆 رتبه‌بندی فرصت‌های معاملاتی...")
        if is_stopped(): return [], 0.0
        ranked = self.ranker.rank_opportunities(enriched_opportunities)

        top_n_limit = config.OUTPUT_CONFIG.get("top_n", 50)
        top_opportunities = self.ranker.get_top_n(ranked, n=top_n_limit)

        update_progress(95, "💾 ذخیره‌سازی خروجی‌ها...")
        if top_opportunities and not is_stopped():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"opportunities_gui_{timestamp}.xlsx"
            try:
                self.excel_exporter.export(opportunities=top_opportunities, filename=filename)
                logger.info(f"Results exported to {filename}")
            except Exception as exp_err:
                logger.error(f" Error exporting to excel: {exp_err}")

        return top_opportunities, time.time() - start_time


# =====================================================
# نقطه ورود برنامه (فقط UI)
# =====================================================

def main():
    setup_logging()
    logger.info("Starting Option Scanner GUI Application...")

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    ui_theme.apply_app_layout(app)

    try:
        font = QFont("Vazir", 9)
        app.setFont(font)
    except Exception:
        pass

    theme_setting = settings_manager.get_active_settings().get("theme", ui_theme.THEME_LIGHT)
    ui_theme.apply_app_theme(app, theme_setting)

    # ۱. ایجاد موتور (بسیار سبک و بدون دیتابیس/استراتژی اولیه)
    scanner_engine = OptionScanner()

    # ۲. ساخت و نمایش آنی پنجره UI
    window = MainWindow(scanner_engine=scanner_engine)
    window.show()

    logger.info(" UI Window Opened successfully")
    
    # ۳. برنامه منتظر کلیک کاربر بر روی دکمه اسکن یا تایمر اتوماتیک UI باقی می‌ماند
    sys.exit(app.exec())


if __name__ == "__main__":
    main()