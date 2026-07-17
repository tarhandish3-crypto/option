# main.py
# -*- coding: utf-8 -*-

"""
ماژول اصلی سیستم اسکنر (Main Executive Module) - نسخه نهایی V5
هماهنگ با هسته پردازش جریانی و بهینه‌شده برای پایداری در محیط تولید (Production)
"""

import time
import logging
import signal
import sys
import gc
from datetime import datetime
from typing import Optional

import config
from data.manager import DataManager
from engine.scanner_engine import ScannerEngine
from reports.excel_exporter import ExcelExporter
from reports.chart_plotter import ChartPlotter
from scoring.ranker import OpportunityRanker, RankingProfile
from strategies.core import _load_strategies
from analytics.risk_engine import RiskEngine
from analytics.strategy_classifier import StrategyClassifier
from filters.strategy_filters import apply_strategy_filter

logger = logging.getLogger("OptionScanner.Main")

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
    """کلاس اصلی اسکنر با پشتیبانی از معماری V5 و بهینه‌سازی حافظه"""

    __slots__ = (
        'interval_minutes', 'parallel', 'max_workers', 'max_cycles',
        'is_running', 'cycle_count', 'data_manager', 'ranker',
        'excel_exporter', 'chart_plotter')

    def __init__(
            self,
            interval_minutes: Optional[int] = None,
            parallel: Optional[bool] = None,
            max_workers: Optional[int] = None,
            max_cycles: Optional[int] = None):

        sys_config = config.get_system_config()

        self.interval_minutes = interval_minutes or sys_config.get("scan_interval_minutes", 3)
        self.parallel = parallel if parallel is not None else sys_config.get("parallel_enabled", True)
        self.max_workers = max_workers or sys_config.get("max_workers", 1)

        cfg_max = sys_config.get("max_cycles", 0) or 0
        self.max_cycles = max_cycles if max_cycles is not None else cfg_max

        self.is_running = True
        self.cycle_count = 0

        logger.info("Loading strategies definitions...")
        _load_strategies()

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

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """مدیریت ایمن سیگنال‌های خروج"""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(f"Received {signal_name}. Graceful shutdown sequence initiated...")
        self.is_running = False

    # =====================================================
    # اجرای اسکن چرخه‌ای
    # =====================================================

    def run_cycle(self) -> bool:
        """اجرای یک چرخه کامل اسکن بازار"""
        cycle_start = time.time()
        self.cycle_count += 1

        logger.info("=" * 60)
        logger.info(f"Cycle #{self.cycle_count} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        try:
            logger.info("Fetching market snapshot...")
            calc_advanced = config.FEATURE_FLAGS.get("calculate_greeks", True)
            snapshot = self.data_manager.get_market_snapshot(force_refresh=False, calc_advanced=calc_advanced)

            if not snapshot or not snapshot.option_contracts:
                logger.warning("MarketSnapshot empty. Skipping cycle.")
                return False

            logger.info(f"MarketSnapshot: {len(snapshot.option_contracts)} contracts loaded.")

            # ارکستراسیون اسکن
            engine = ScannerEngine(snapshot=snapshot)
            scan_result = engine.execute_full_scan()

            if not scan_result.opportunities:
                logger.warning("No opportunities discovered.")
                return False

            # فیلتر پویا
            filtered_opportunities = [
                opp for opp in scan_result.opportunities
                if opp is not None and apply_strategy_filter(opp)]

            if not filtered_opportunities:
                logger.warning("No opportunities passed the dynamic filters.")
                return False

            # تحلیل ریسک و رتبه‌بندی
            logger.info("Processing Risk & Ranking layers...")
            enriched_opportunities = []
            for opp in filtered_opportunities:
                try:
                    enriched_opportunities.append(RiskEngine.evaluate_opportunity(opp))
                except Exception as risk_err:
                    logger.debug(f"Risk eval error for {opp.strategy_name}: {risk_err}")
                    enriched_opportunities.append(opp)

            ranked = self.ranker.rank_opportunities(enriched_opportunities)
            StrategyClassifier.batch_classify(ranked)

            top_n_limit = config.OUTPUT_CONFIG.get("top_n", 50)
            top_opportunities = self.ranker.get_top_n(ranked, n=top_n_limit)

            # خروجی‌گیری
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"opportunities_cycle_{self.cycle_count}_{timestamp}.xlsx"
            self.excel_exporter.export(opportunities=top_opportunities, filename=filename)
            
            # نمودارها
            try:
                chart_data = [(opp.strategy_name, opp, '#1f77b4') for opp in top_opportunities[:5]]
                self.chart_plotter.plot_comparison(data=chart_data, ticker="Market")
            except Exception as chart_err:
                logger.warning(f"Chart plotting skipped: {chart_err}")

            elapsed = time.time() - cycle_start
            logger.info(f"Cycle #{self.cycle_count} completed successfully in {elapsed:.2f}s")
            return True

        except Exception as e:
            logger.error(f"Cycle #{self.cycle_count} critical failure: {e}", exc_info=True)
            return False

        finally:
            # پاکسازی حتمی حافظه پس از هر چرخه
            gc.collect()

    # =====================================================
    # حلقه اصلی (Main Loop)
    # =====================================================

    def run_forever(self) -> None:
        """حلقه اصلی اجرا با قابلیت زمان‌بندی"""
        if self.max_cycles > 0:
            logger.info(f"Scheduled Mode: {self.max_cycles} cycles, {self.interval_minutes} min interval.")
        else:
            logger.info("Continuous DSS Scan Mode Engaged.")

        while self.is_running:
            if self.max_cycles > 0 and self.cycle_count >= self.max_cycles:
                logger.info("Target cycle count reached. Shutting down.")
                break

            try:
                self.run_cycle()
                
                # بررسی وقفه (Sleep) برای پاسخگویی سریع به سیگنال‌های خروج
                sleep_seconds = int(self.interval_minutes * 60)
                for _ in range(sleep_seconds):
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Main loop error: {e}. Retrying in 10s...")
                time.sleep(10)

        logger.info("OptionScanner engine shutdown complete.")


# =====================================================
# نقطه ورود اصلی
# =====================================================

def main():
    setup_logging()

    logger.info("=" * 60)
    logger.info("OPTION STRATEGY SCANNER v5.0 [STABLE PRODUCTION]")
    logger.info(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    scanner = OptionScanner()

    try:
        scanner.run_forever()
    except Exception as e:
        logger.error(f"Fatal error in main entry: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Application terminated normally.")
    sys.exit(0)


if __name__ == "__main__":
    main()