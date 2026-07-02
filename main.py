# main.py
# -*- coding: utf-8 -*-

"""
ماژول اصلی سیستم اسکنر (Main Executive Module) - نسخه ارتقایافته تصمیم‌یار (DSS)
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
            logging.FileHandler(log_dir / "scanner.log", encoding="utf-8")])

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# =====================================================
# کلاس اصلی اسکنر
# =====================================================

class OptionScanner:
    def __init__(
            self,
            interval_minutes: Optional[int] = None,
            parallel: Optional[bool] = None,
            max_workers: Optional[int] = None,
            max_cycles: Optional[int] = None,):
        sys_config = config.get_system_config()

        self.interval_minutes = interval_minutes or sys_config.get(
            "scan_interval_minutes", 3)
        self.parallel = parallel if parallel is not None else sys_config.get(
            "parallel_enabled", True)
        self.max_workers = max_workers or sys_config.get("max_workers", 1)

        # تعداد چرخه: 0 یا None = بی‌نهایت
        cfg_max = sys_config.get("max_cycles")
        self.max_cycles: int = max_cycles if max_cycles is not None else cfg_max

        self.is_running = True
        self.cycle_count = 0

        logger.info("Loading strategies...")
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
            "volatility": RankingProfile.VOLATILITY, }
        profile_name = config.RANKING_CONFIG.get("default_profile", "balanced")
        profile = profile_map.get(profile_name, RankingProfile.BALANCED)

        self.ranker = OpportunityRanker(default_profile=profile)
        self.excel_exporter = ExcelExporter(output_dir=str(config.OUTPUT_DIR))
        self.chart_plotter = ChartPlotter(output_dir=str(config.CHARTS_DIR))

        # مدیریت سیگنال‌های سیستم‌عامل برای خروج امن
        # توجه: SIGINT توسط handler مدیریت می‌شود و KeyboardInterrupt صادر نمی‌شود
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """مدیریت سیگنال‌های خروج با حفظ امنیت داده‌ها"""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(
            f"Received {signal_name} signal. Initiating graceful shutdown...")
        self.is_running = False

    # =====================================================
    # اجرای اسکن چرخه‌ای
    # =====================================================

    def run_cycle(self) -> bool:
        cycle_start = time.time()
        self.cycle_count += 1

        logger.info("=" * 60)
        logger.info(
            f"Cycle #{self.cycle_count} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        try:
            logger.info("Fetching market snapshot...")
            calc_advanced = config.FEATURE_FLAGS.get("calculate_greeks")
            snapshot = self.data_manager.get_market_snapshot(
                force_refresh=False, calc_advanced=calc_advanced)

            if not snapshot or not snapshot.option_contracts:
                logger.warning("MarketSnapshot is empty. Skipping cycle.")
                return False

            logger.info(f"MarketSnapshot: {len(snapshot.option_contracts)} contracts, "
                        f"{len(snapshot.underlying_assets)} underlyings.")

            logger.info("Invoking ScannerEngine...")
            engine = ScannerEngine(
                snapshot=snapshot,)
            scan_result = engine.execute_full_scan()

            if not scan_result.opportunities:
                logger.warning(
                    "No opportunities discovered in this market state.")
                return False

            logger.info(
                f"Discovered {len(scan_result.opportunities)} valid combinations.")

            # =====================================================
            # فیلتر پویا بر اساس استراتژی
            # =====================================================
            logger.info("Applying dynamic strategy filters...")
            filtered_opportunities = [
                opp for opp in scan_result.opportunities
                if apply_strategy_filter(opp)]

            logger.info(
                f"After dynamic filter: {len(filtered_opportunities)} opportunities remained.")

            if not filtered_opportunities:
                logger.warning("No opportunities passed the dynamic filter.")
                return False

            # =====================================================
            # Risk + Ranking + Classification
            # =====================================================
            logger.info("Calculating risk metrics via RiskEngine...")
            enriched_opportunities = []
            risk_success_count = 0
            risk_fail_count = 0

            for opp in filtered_opportunities:
                try:
                    enriched_opp = RiskEngine.evaluate_opportunity(opp)
                    enriched_opportunities.append(enriched_opp)
                    risk_success_count += 1
                except Exception as risk_err:
                    risk_fail_count += 1
                    logger.warning(
                        f"Risk evaluation failed for {opp.strategy_name} on {opp.underlying_ticker}: {risk_err}")
                    enriched_opportunities.append(opp)

            logger.info(
                f"Risk metrics calculated: {risk_success_count} successful, {risk_fail_count} failed")

            logger.info("Ranking & Classifying opportunities...")
            ranked = self.ranker.rank_opportunities(enriched_opportunities)

            # Classification بعد از ranking اجرا می‌شود تا profile_scores موجود باشد
            StrategyClassifier.batch_classify(ranked)

            top_n_limit = config.OUTPUT_CONFIG.get("top_n")
            top_opportunities = self.ranker.get_top_n(ranked, n=top_n_limit)

            # انتخاب نهایی
            if not top_opportunities:
                logger.warning("No opportunities passed ranking layer.")
                return False

            logger.info(
                f"Selected Top {len(top_opportunities)} opportunities for data-dense report.")

            # =====================================================
            # خروجی
            # =====================================================
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"opportunities_cycle_{self.cycle_count}_{timestamp}.xlsx"

            report_path = self.excel_exporter.export(
                opportunities=top_opportunities, filename=filename)
            logger.info(
                f"Multi-sheet Excel report exported successfully: {report_path}")

            try:
                colors = ['#1f77b4', '#ff7f0e',
                          '#2ca02c', '#d62728', '#9467bd']
                chart_data = [
                    (opp.strategy_name, opp, colors[i % len(colors)])
                    for i, opp in enumerate(top_opportunities[:5])]

                self.chart_plotter.plot_comparison(
                    data=chart_data, ticker="Market")
                logger.info("Analytical charts generated successfully.")
            except Exception as chart_err:
                logger.warning(
                    f"Chart plotting generation skipped: {chart_err}")

            elapsed = time.time() - cycle_start
            logger.info(
                f"Cycle #{self.cycle_count} completed efficiently in {elapsed:.2f}s")
            return True

        except Exception as e:
            logger.error(
                f"Cycle #{self.cycle_count} failed critical execution: {e}", exc_info=True)
            return False

        finally:
            try:
                if 'scan_result' in locals():
                    del scan_result
                if 'enriched_opportunities' in locals():
                    del enriched_opportunities
                if 'top_opportunities' in locals():
                    del top_opportunities
                if 'snapshot' in locals():
                    del snapshot
                if 'engine' in locals():
                    del engine
                gc.collect()
                logger.debug(
                    f"Memory cleanup completed for cycle #{self.cycle_count}")
            except Exception as cleanup_err:
                logger.debug(f"Memory cleanup warning: {cleanup_err}")

    # =====================================================
    # حلقه استمرار اسکن
    # =====================================================

    def run_forever(self) -> None:
        """حلقه اصلی اجرا — محدود به max_cycles چرخه یا بی‌نهایت اگر max_cycles == 0"""
        if self.max_cycles > 0:
            logger.info(f"Scheduled Scan Mode: {self.max_cycles} cycles, "
                        f"{self.interval_minutes} min apart.")
        else:
            logger.info(
                "Continuous Decision Support System (DSS) Scan Mode Engaged.")

        while self.is_running:
            # بررسی رسیدن به حد چرخه
            if self.max_cycles > 0 and self.cycle_count >= self.max_cycles:
                logger.info(
                    f"All {self.max_cycles} scheduled cycles completed. Shutting down.")
                self.is_running = False
                break

            try:
                self.run_cycle()
                gc.collect()

                # اگر آخرین چرخه بود، صبر نکن
                if self.max_cycles > 0 and self.cycle_count >= self.max_cycles:
                    continue

                sleep_seconds = int(self.interval_minutes * 60)
                logger.info(
                    f"Waiting {self.interval_minutes} minutes for next cycle "
                    + (f"({self.cycle_count}/{self.max_cycles})..."
                       if self.max_cycles > 0 else "..."))

                check_step = 5
                for spent in range(0, sleep_seconds, check_step):
                    if not self.is_running:
                        break
                    remaining = sleep_seconds - spent
                    time.sleep(min(check_step, remaining))

            except Exception as e:
                logger.error(
                    f"Main loop critical error: {e}. Re-engaging engine in 10s...")
                time.sleep(10)

        logger.info("OptionScanner engine shutdown successfully.")


# =====================================================
# نقطه ورود سیستم
# =====================================================

def main():
    setup_logging()

    logger.info("=" * 60)
    logger.info("OPTION STRATEGY SCANNER v3.0 [DSS ENGINE ARCHITECTURE]")
    logger.info(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    scanner = OptionScanner()

    try:
        scanner.run_forever()
    except Exception as e:
        # فقط خطاهای غیرمنتظره را catch می‌کنیم
        # KeyboardInterrupt توسط signal handler مدیریت می‌شود
        logger.error(
            f"Fatal crash inside executive main entry: {e}", exc_info=True)
        sys.exit(1)

    # خروج عادی برنامه (بدون خطا)
    logger.info("Application terminated normally.")
    sys.exit(0)


if __name__ == "__main__":
    main()
