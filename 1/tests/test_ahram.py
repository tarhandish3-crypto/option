# tests/test_ahram.py
# -*- coding: utf-8 -*-

"""
Test script for the 'ahram' symbol.

This script:
    1. Fetches market data from DataManager.
    2. Filters data specifically for the 'ahram' symbol.
    3. Executes the scanner only on the filtered data.
    4. Displays a summary of the results.
    5. Saves the results to an Excel file.

Execution:
    python -m tests.test_ahram
    or
    cd tests && python test_ahram.py
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.manager import DataManager
from engine.scanner import Scanner
from strategies.core import _load_strategies, get_all_strategies
from strategies.generators import get_generator
from core.models import MarketSnapshot
from scoring.ranker import OpportunityRanker, RankingProfile
from reports.excel_exporter import ExcelExporter

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def filter_by_ticker(snapshot: MarketSnapshot, ticker: str) -> MarketSnapshot:
    """
    Filter MarketSnapshot for a specific ticker.
    
    Args:
        snapshot: Full MarketSnapshot
        ticker: Target ticker (e.g., 'ahram')
        
    Returns:
        MarketSnapshot: Filtered data for the target ticker
    """
    # Filter underlying assets
    filtered_underlyings = {
        ticker: snapshot.underlying_assets[ticker]
        for ticker in [ticker]
        if ticker in snapshot.underlying_assets}
    
    # Filter contracts
    filtered_contracts = [
        c for c in snapshot.option_contracts
        if c.underlying_ticker == ticker
    ]
    
    # Build new MarketSnapshot
    filtered_snapshot = MarketSnapshot(
        timestamp=snapshot.timestamp,
        underlying_assets=filtered_underlyings,
        option_contracts=filtered_contracts,
        risk_free_rate=snapshot.risk_free_rate
    )
    filtered_snapshot.build_indices()
    
    return filtered_snapshot


def print_contract_summary(contracts: list, title: str = "Contracts"):
    """Print a summary of the contracts."""
    if not contracts:
        print(f"\n{title}: No contracts found")
        return
    
    print(f"\n{title}:")
    print("-" * 80)
    print(f"{'Ticker':<12} {'Type':<6} {'Strike':<12} {'DTE':<6} {'Bid':<10} {'Ask':<10} {'Volume':<10} {'OI':<10}")
    print("-" * 80)
    
    for c in contracts[:10]:
        print(f"{c.ticker:<12} {c.option_type.value:<6} {c.strike_price:<12.0f} {c.days_to_maturity:<6} {c.bid:<10.0f} {c.ask:<10.0f} {c.volume:<10} {c.open_interest:<10}")
    
    if len(contracts) > 10:
        print(f"... and {len(contracts) - 10} more")
    
    print("-" * 80)
    print(f"Total: {len(contracts)} contracts")


def print_opportunities(opportunities: list):
    """Print a summary of the generated opportunities."""
    if not opportunities:
        print("\nWARNING: No opportunities found")
        return
    
    print("\nOpportunities:")
    print("-" * 80)
    print(f"{'#':<3} {'Strategy':<20} {'Strike':<12} {'DTE':<6} {'Liquidity':<10} {'Moneyness':<10}")
    print("-" * 80)
    
    for i, opp in enumerate(opportunities, 1):
        option_leg = opp.legs[1] if len(opp.legs) > 1 else None
        strike = option_leg.contract.strike_price if option_leg and option_leg.contract else 0
        moneyness = opp.metadata.get('moneyness', 'N/A')
        
        print(f"{i:<3} {opp.strategy_name:<20} {strike:<12.0f} {opp.days_to_maturity:<6} {opp.liquidity_score:<10.2f} {moneyness:<10}")
    
    print("-" * 80)


def print_first_opportunity_details(opportunities: list):
    """Print detailed information about the first opportunity."""
    if not opportunities:
        return
    
    print("\nFirst opportunity details:")
    first_opp = opportunities[0]
    print(f"   Strategy: {first_opp.strategy_name}")
    print(f"   Ticker: {first_opp.underlying_ticker}")
    print(f"   Days to maturity: {first_opp.days_to_maturity}")
    print(f"   Liquidity score: {first_opp.liquidity_score:.2f}")
    print(f"   Metadata: {first_opp.metadata}")
    
    print("\n   Legs:")
    for j, leg in enumerate(first_opp.legs, 1):
        if leg.contract:
            print(f"      Leg {j}: {leg.contract.ticker} ({leg.contract.option_type.value}) - {leg.side.value} x {leg.ratio}")
        else:
            print(f"      Leg {j}: Stock ({leg.side.value} x {leg.ratio})")


def save_to_excel(opportunities: list, filename_prefix: str = "test_ahram") -> str:
    """
    Save opportunities to an Excel file.
    
    Args:
        opportunities: List of opportunities
        filename_prefix: Prefix for the filename
        
    Returns:
        str: Path to the saved Excel file
    """
    if not opportunities:
        print("WARNING: No opportunities to save to Excel")
        return ""
    
    print("\nSaving results to Excel...")
    
    # Rank the opportunities
    ranker = OpportunityRanker(profile=RankingProfile.BALANCED)
    ranked = ranker.rank_opportunities(opportunities)
    top_opportunities = ranker.get_top_n(ranked, n=20)
    
    # Export to Excel
    exporter = ExcelExporter(output_dir="output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.xlsx"
    
    report_path = exporter.export(
        opportunities=top_opportunities,
        filename=filename,
        include_chart_data=True
    )
    
    print(f"Excel report saved to: {report_path}")
    return report_path


def test_ahram(save_excel: bool = True):
    """
    Run the test on the 'ahram' symbol.
    
    Args:
        save_excel: Whether to save results to Excel (default: True)
    
    Returns:
        list: Generated opportunities
    """
    
    print("=" * 70)
    print("TEST: Symbol 'ahram' (اهرهم)")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Step 1: Load strategies
    print("\nLoading strategies...")
    _load_strategies()
    all_strategies = get_all_strategies()
    print(f"Loaded {len(all_strategies)} strategies: {list(all_strategies.keys())}")
    
    # Step 2: Fetch market data
    print("\nFetching market data...")
    data_manager = DataManager(use_cache=True, ttl_seconds=60)
    snapshot = data_manager.get_market_snapshot(force_refresh=False, calc_advanced=True)
    
    if not snapshot.option_contracts:
        print("ERROR: No data received!")
        return []
    
    print(f"Total contracts: {len(snapshot.option_contracts)}")
    print(f"Total underlyings: {len(snapshot.underlying_assets)}")
    
    # Step 3: Filter for 'ahram'
    TICKER = "اهرم"
    print(f"\nFiltering for ticker: '{TICKER}'")
    
    if TICKER not in snapshot.underlying_assets:
        print(f"ERROR: Ticker '{TICKER}' not found in data!")
        print(f"Available tickers: {list(snapshot.underlying_assets.keys())}")
        return []
    
    filtered_snapshot = filter_by_ticker(snapshot, TICKER)
    
    # Step 4: Display data summary
    underlying_price = filtered_snapshot.underlying_assets[TICKER].last_price
    print(f"\nData for '{TICKER}':")
    print(f"   Underlying price: {underlying_price:,.0f}")
    print(f"   Contracts: {len(filtered_snapshot.option_contracts)}")
    
    # Separate CALL and PUT
    calls = [c for c in filtered_snapshot.option_contracts if c.option_type.value == "Call"]
    puts = [c for c in filtered_snapshot.option_contracts if c.option_type.value == "Put"]
    print(f"   Calls: {len(calls)}")
    print(f"   Puts: {len(puts)}")
    
    # Display contracts
    print_contract_summary(calls, "CALL Contracts")
    print_contract_summary(puts, "PUT Contracts")
    
    # Step 5: Run the scanner
    print(f"\nScanning '{TICKER}'...")
    scanner = Scanner(filtered_snapshot)
    opportunities = scanner.scan_ticker(TICKER)
    
    # Step 6: Display results
    print(f"\nResults for '{TICKER}':")
    print(f"   Total opportunities: {len(opportunities)}")
    
    if opportunities:
        print_opportunities(opportunities)
        print_first_opportunity_details(opportunities)
    else:
        print("\nWARNING: No opportunities found for 'اهرم'")
    
    # Step 7: Save to Excel
    if save_excel and opportunities:
        save_to_excel(opportunities, f"test_ahram")
    
    print("\n" + "=" * 70)
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    return opportunities


def test_specific_strategy(strategy_name: str = "covered_call", save_excel: bool = True):
    """
    Test a specific strategy on the 'ahram' symbol.
    
    Args:
        strategy_name: Name of the strategy (e.g., 'covered_call', 'bull_call_spread')
        save_excel: Whether to save results to Excel (default: True)
    """
    
    print("=" * 70)
    print(f"TEST: Strategy '{strategy_name}' on Symbol 'اهرم'")
    print("=" * 70)
    
    # Load strategies
    _load_strategies()
    all_strategies = get_all_strategies()
    
    if strategy_name not in all_strategies:
        print(f"ERROR: Strategy '{strategy_name}' not found!")
        print(f"Available: {list(all_strategies.keys())}")
        return
    
    strategy_def = all_strategies[strategy_name]
    print(f"Strategy found: {strategy_def.name}")
    print(f"   Generator: {strategy_def.generator_type}")
    print(f"   Weight pattern: {strategy_def.weight_pattern}")
    print(f"   Rules: {strategy_def.rules}")
    
    # Fetch data
    data_manager = DataManager(use_cache=True, ttl_seconds=60)
    snapshot = data_manager.get_market_snapshot(force_refresh=False, calc_advanced=True)
    
    # Filter for 'ahram'
    filtered_snapshot = filter_by_ticker(snapshot, "اهرم")
    
    # Get generator
    generator = get_generator(strategy_def)
    if generator is None:
        print(f"ERROR: No generator for {strategy_name}")
        return
    
    print(f"Generator: {generator.__class__.__name__}")
    
    # Run scanner
    scanner = Scanner(filtered_snapshot)
    opportunities = scanner.scan_ticker("اهرم")
    
    # Filter by strategy name
    filtered_opps = [opp for opp in opportunities if opp.strategy_name == strategy_name]
    
    print(f"\nResults for '{strategy_name}':")
    print(f"   Total opportunities: {len(filtered_opps)}")
    
    for opp in filtered_opps:
        print(f"\nOpportunity:")
        print(f"   Strategy: {opp.strategy_name}")
        print(f"   Ticker: {opp.underlying_ticker}")
        print(f"   Days to maturity: {opp.days_to_maturity}")
        print(f"   Liquidity score: {opp.liquidity_score:.2f}")
        print(f"   Metadata: {opp.metadata}")
    
    # Save to Excel
    if save_excel and filtered_opps:
        save_to_excel(filtered_opps, f"test_{strategy_name}")


if __name__ == "__main__":
    # Run the main test (with Excel export)
    test_ahram(save_excel=True)
    
    # For testing a specific strategy, uncomment the line below:
    # test_specific_strategy("covered_call", save_excel=True)
    # test_specific_strategy("bull_call_spread", save_excel=True)
    # test_specific_strategy("bear_put_spread", save_excel=True)