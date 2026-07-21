# main.py
# -*- coding: utf-8 -*-

"""
ماژول اصلی سیستم اسکنر (Main Executive Module) - نسخه اصلاح‌شده V6.2
هماهنگ با هسته پردازش جریانی، UI، ورکر پس‌زمینه و قابلیت‌های پیشرفته
"""

import time
import logging
import signal
import sys
import gc
import threading
import sqlite3
from datetime import datetime
from typing import Optional, Callable, List, Any, Dict, Tuple
from pathlib import Path
import json
from dataclasses import dataclass

import config
from data.manager import DataManager
from engine.scanner_engine import ScannerEngine
from reports.excel_exporter import ExcelExporter
from reports.chart_plotter import ChartPlotter
from scoring.ranker import OpportunityRanker, RankingProfile
from strategies.core import _load_strategies
from analytics.risk_engine import RiskEngine
from filters.strategy_filters import apply_strategy_filter

logger = logging.getLogger("OptionScanner.Main")


# =====================================================
# مدل‌های داده برای کش
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
        """بررسی انقضای کش"""
        return (datetime.now() - self.timestamp).total_seconds() > ttl_seconds


# =====================================================
# تنظیمات لاگینگ متمرکز
# =====================================================

def setup_logging() -> None:
    """تنظیمات لاگینگ متمرکز پروژه"""
    log_dir = config.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "scanner.log", encoding="utf-8")
        ])

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# =====================================================
# کلاس اصلی اسکنر
# =====================================================

class OptionScanner:
    """کلاس اصلی اسکنر با پشتیبانی از معماری V6 و اتصال ایمن به UI"""

    __slots__ = (
        'interval_minutes', 'parallel', 'max_workers', 'max_cycles',
        'is_running', 'cycle_count', 'data_manager', 'ranker',
        'excel_exporter', 'chart_plotter', '_last_scan_time',
        '_cache', '_cache_ttl', '_scan_timeout', '_db_enabled',
        '_db_path', '_user_filters', '_total_scans', '_total_opportunities',
        '_cancel_event'
    )

    def __init__(
            self,
            interval_minutes: Optional[int] = None,
            parallel: Optional[bool] = None,
            max_workers: Optional[int] = None,
            max_cycles: Optional[int] = None,
            cache_ttl_seconds: int = 60,
            scan_timeout_seconds: int = 300,
            db_enabled: bool = False,
            db_path: Optional[Path] = None):

        sys_config = config.get_system_config()

        self.interval_minutes = interval_minutes or sys_config.get("scan_interval_minutes", 3)
        self.parallel = parallel if parallel is not None else sys_config.get("parallel_enabled", True)
        self.max_workers = max_workers or sys_config.get("max_workers", 1)

        cfg_max = sys_config.get("max_cycles", 0)
        self.max_cycles = max_cycles if max_cycles is not None else cfg_max

        self.is_running = True
        self.cycle_count = 0
        self._total_scans = 0
        self._total_opportunities = 0
        self._last_scan_time: Optional[datetime] = None

        self._cache_ttl = cache_ttl_seconds
        self._cache: Optional[ScanCacheEntry] = None
        self._scan_timeout = scan_timeout_seconds
        self._cancel_event = threading.Event()

        self._db_enabled = db_enabled
        self._db_path = db_path or (config.DATA_DIR / "scans.db")
        if self._db_enabled:
            self._init_database()

        self._user_filters: Dict[str, Any] = {}
        self._load_user_filters()

        logger.info("Loading strategies definitions...")
        _load_strategies()

        self.data_manager = DataManager(
            cache_dir=str(config.CACHE_DIR),
            use_cache=True,
            ttl_seconds=config.CACHE_TTL_SECONDS)

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

        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            pass

        logger.info("✅ OptionScanner V6.2 initialized successfully")

    # =====================================================
    # دیتابیس و فیلترها
    # =====================================================

    def _init_database(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
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
            logger.info(f"✅ Database initialized at {self._db_path}")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}")
            self._db_enabled = False

    def _save_scan_to_db(self, results: List[Any], duration: float) -> None:
        if not self._db_enabled or not results:
            return
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                cursor = conn.cursor()
                filters_json = json.dumps(self._user_filters, ensure_ascii=False)
                cursor.execute("""
                    INSERT INTO scan_results 
                    (timestamp, total_opportunities, scan_duration, filters_used)
                    VALUES (?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    len(results),
                    duration,
                    filters_json
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"⚠️ Failed to save to database: {e}")

    def _load_user_filters(self) -> None:
        filters_path = config.CONFIG_DIR / "user_filters.json"
        if filters_path.exists():
            try:
                with open(filters_path, 'r', encoding='utf-8') as f:
                    self._user_filters = json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load user filters: {e}")
                self._user_filters = {}

    def apply_user_filters(self, opportunities: List[Any]) -> List[Any]:
        if not opportunities or not self._user_filters:
            return opportunities

        filtered = []
        for opp in opportunities:
            # پشتیبانی امن از خصوصیات با getattr
            score = getattr(opp, 'score', getattr(opp, 'rank_score', 0))
            if score < self._user_filters.get('min_score', 0):
                continue

            risk = getattr(opp, 'risk', getattr(opp, 'max_risk', 0))
            if risk > self._user_filters.get('max_risk', float('inf')):
                continue

            profit = getattr(opp, 'profit', getattr(opp, 'expected_profit', 0))
            if profit < self._user_filters.get('min_profit', 0):
                continue

            filtered.append(opp)

        return filtered

    # =====================================================
    # کش و اجرای اسکن
    # =====================================================

    def get_cached_results(self, force_refresh: bool = False) -> Optional[List[Any]]:
        if force_refresh:
            return None
        if self._cache and not self._cache.is_expired(self._cache_ttl):
            logger.debug(f"📦 Cache hit: {len(self._cache.results)} results")
            return self._cache.results
        return None

    def update_cache(self, results: List[Any], duration: float) -> None:
        self._cache = ScanCacheEntry(
            timestamp=datetime.now(),
            results=results,
            scan_duration=duration,
            total_opportunities=len(results),
            filters_used=self._user_filters.copy()
        )

    def _signal_handler(self, signum, frame) -> None:
        self.is_running = False
        self._cancel_event.set()

    def run_scan_with_progress(
        self, 
        progress_callback: Optional[Callable[[int, str], None]] = None,
        stop_check_callback: Optional[Callable[[], bool]] = None,
        force_refresh: bool = True,
        timeout_seconds: Optional[int] = None
    ) -> List[Any]:

        self._cancel_event.clear()

        def update_progress(percent: int, msg: str):
            if progress_callback:
                progress_callback(percent, msg)

        def is_stopped() -> bool:
            external_stop = stop_check_callback() if stop_check_callback else False
            return external_stop or self._cancel_event.is_set() or not self.is_running

        if not force_refresh:
            cached = self.get_cached_results()
            if cached is not None:
                update_progress(100, "📦 استفاده از نتایج ذخیره‌شده")
                return cached

        scan_output = {"results": [], "duration": 0.0, "error": None}

        def target():
            try:
                res, dur = self._execute_scan(update_progress, is_stopped, force_refresh)
                scan_output["results"] = res
                scan_output["duration"] = dur
            except Exception as e:
                scan_output["error"] = e

        timeout = timeout_seconds or self._scan_timeout
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            self._cancel_event.set() # سیگنال لغو به Thread در حال اجرای اسکن
            logger.error(f"⏱️ Scan timed out after {timeout} seconds!")
            update_progress(0, f"⏱️ زمان اسکن به پایان رسید ({timeout} ثانیه)")
            return []

        if scan_output["error"]:
            logger.error(f"❌ Scan error: {scan_output['error']}", exc_info=True)
            update_progress(0, f"❌ خطا: {str(scan_output['error'])}")
            return []

        result = scan_output["results"]
        duration = scan_output["duration"]

        if result:
            result = self.apply_user_filters(result)
            
            self._total_scans += 1
            self._total_opportunities += len(result)
            self._last_scan_time = datetime.now()
            
            self._save_scan_to_db(result, duration)
            self.update_cache(result, duration)

        update_progress(100, f"✅ اسکن کامل شد - {len(result)} فرصت یافت شد")
        return result

    def _execute_scan(
        self,
        update_progress: Callable[[int, str], None],
        is_stopped: Callable[[], bool],
        force_refresh: bool
    ) -> Tuple[List[Any], float]:
        
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
        ranked = self.ranker.rank_opportunities(enriched_opportunities)

        top_n_limit = config.OUTPUT_CONFIG.get("top_n", 50)
        top_opportunities = self.ranker.get_top_n(ranked, n=top_n_limit)

        update_progress(95, "💾 ذخیره‌سازی خروجی‌ها...")
        if top_opportunities and not is_stopped():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"opportunities_gui_{timestamp}.xlsx"
            try:
                self.excel_exporter.export(opportunities=top_opportunities, filename=filename)
            except Exception as exp_err:
                logger.error(f"❌ Error exporting to excel: {exp_err}")

        scan_duration = time.time() - start_time
        return top_opportunities, scan_duration

    def run_scan(self) -> List[Any]:
        return self.run_scan_with_progress()

    def run_cycle(self) -> bool:
        cycle_start = time.time()
        self.cycle_count += 1

        logger.info(f"🔄 Cycle #{self.cycle_count} started...")
        try:
            results = self.run_scan_with_progress(force_refresh=False)
            return bool(results)
        except Exception as e:
            logger.error(f"❌ Cycle #{self.cycle_count} failure: {e}")
            return False
        finally:
            gc.collect()

    def run_forever(self) -> None:
        logger.info("♾️ Scanner loop started.")
        while self.is_running:
            if self.max_cycles > 0 and self.cycle_count >= self.max_cycles:
                break
            try:
                self.run_cycle()
                sleep_seconds = int(self.interval_minutes * 60)
                for _ in range(sleep_seconds):
                    if not self.is_running:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"❌ Main loop error: {e}")
                time.sleep(5)


def main():
    setup_logging()
    scanner = OptionScanner(
        cache_ttl_seconds=config.FEATURE_FLAGS.get("cache_ttl", 60),
        scan_timeout_seconds=config.FEATURE_FLAGS.get("scan_timeout", 300),
        db_enabled=config.FEATURE_FLAGS.get("database_enabled", False)
    )

    try:
        scanner.run_forever()
    except KeyboardInterrupt:
        logger.info("⏹️ Keyboard interrupt received.")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()