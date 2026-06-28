# tests/test_excel_exporter.py
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from datetime import datetime

# =====================================================
# Add project root to sys.path for direct execution
# =====================================================
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.models import Opportunity, LegDefinition
from core.enums import Side
from reports.excel_exporter import ExcelExporter


def create_sample_opportunities() -> list:
    """
    Create sample Opportunity objects for testing.
    
    Returns:
        list: List of Opportunity objects
    """
    opportunities = []
    
    # ===== Sample 1: Covered Call =====
    opp1 = Opportunity(
        strategy_name="covered_call",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.BUY, ratio=1, is_stock_leg=True),
            LegDefinition(contract=None, side=Side.SELL, ratio=1)
        ],
        days_to_maturity=33,
        timestamp=datetime.now(),
        liquidity_score=74.21,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 46000.0,
            "option_type": "Call",
            "moneyness": "ATM",
            "l1_ticker": "ضهرم4032",
            "l2_ticker": "ضهرم4033"
        }
    )
    opportunities.append(opp1)
    
    # ===== Sample 2: Bull Call Spread =====
    opp2 = Opportunity(
        strategy_name="bull_call_spread",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.SELL, ratio=1)
        ],
        days_to_maturity=61,
        timestamp=datetime.now(),
        liquidity_score=68.50,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 50000.0,
            "option_type": "Call",
            "moneyness": "ATM",
            "l1_ticker": "ضهرم5034",
            "l2_ticker": "ضهرم5035"
        }
    )
    opportunities.append(opp2)
    
    # ===== Sample 3: Bear Put Spread =====
    opp3 = Opportunity(
        strategy_name="bear_put_spread",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.SELL, ratio=1),
            LegDefinition(contract=None, side=Side.BUY, ratio=1)
        ],
        days_to_maturity=61,
        timestamp=datetime.now(),
        liquidity_score=55.22,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 24000.0,
            "option_type": "Put",
            "moneyness": "OTM",
            "l1_ticker": "طهرم5025",
            "l2_ticker": "طهرم5026"
        }
    )
    opportunities.append(opp3)
    
    # ===== Sample 4: Long Straddle =====
    opp4 = Opportunity(
        strategy_name="long_straddle",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.BUY, ratio=1)
        ],
        days_to_maturity=33,
        timestamp=datetime.now(),
        liquidity_score=82.30,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 46000.0,
            "option_type": "Call/Put",
            "moneyness": "ATM",
            "l1_ticker": "ضهرم4032",
            "l2_ticker": "طهرم4033"
        }
    )
    opportunities.append(opp4)
    
    # ===== Sample 5: Strip (1 Call + 2 Put) =====
    opp5 = Opportunity(
        strategy_name="strip",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.BUY, ratio=1)
        ],
        days_to_maturity=33,
        timestamp=datetime.now(),
        liquidity_score=59.44,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 30000.0,
            "option_type": "Put/Call",
            "moneyness": "OTM",
            "l1_ticker": "ضهرم4029",
            "l2_ticker": "طهرم4029",
            "l3_ticker": "طهرم4030"
        }
    )
    opportunities.append(opp5)
    
    # ===== Sample 6: Long Box (4 legs) =====
    opp6 = Opportunity(
        strategy_name="long_box",
        underlying_ticker="اهرم",
        legs=[
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.SELL, ratio=1),
            LegDefinition(contract=None, side=Side.BUY, ratio=1),
            LegDefinition(contract=None, side=Side.SELL, ratio=1)
        ],
        days_to_maturity=61,
        timestamp=datetime.now(),
        liquidity_score=65.75,
        metadata={
            "volatility_signal": "منصفانه",
            "stock_price": 47622.0,
            "strike_price": 30000.0,
            "option_type": "Call/Put",
            "moneyness": "ATM",
            "l1_ticker": "ضهرم5029",
            "l2_ticker": "ضهرم5031",
            "l3_ticker": "طهرم5029",
            "l4_ticker": "طهرم5031"
        }
    )
    opportunities.append(opp6)
    
    return opportunities


def print_sample_summary(opportunities: list) -> None:
    """Print a summary of the sample opportunities."""
    print("\nSample Opportunities:")
    print("-" * 80)
    print(f"{'#':<3} {'Strategy':<20} {'Ticker':<12} {'DTE':<6} {'Liquidity':<10}")
    print("-" * 80)
    
    for i, opp in enumerate(opportunities, 1):
        print(f"{i:<3} {opp.strategy_name:<20} {opp.underlying_ticker:<12} {opp.days_to_maturity:<6} {opp.liquidity_score:<10.2f}")
    
    print("-" * 80)
    print(f"Total: {len(opportunities)} opportunities")


def test_excel_exporter() -> None:
    """Test the ExcelExporter with sample data."""
    
    print("=" * 70)
    print("TEST: ExcelExporter Module")
    print("=" * 70)
    
    # ===== Step 1: Create sample opportunities =====
    print("\nCreating sample opportunities...")
    opportunities = create_sample_opportunities()
    print_sample_summary(opportunities)
    
    # ===== Step 2: Initialize ExcelExporter =====
    print("\nInitializing ExcelExporter...")
    exporter = ExcelExporter(output_dir="output")
    print(f"Output directory: {exporter.output_dir}")
    
    # ===== Step 3: Test export_from_opportunities =====
    print("\n" + "-" * 70)
    print("Test 1: export_from_opportunities (direct from Opportunity)")
    print("-" * 70)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename1 = f"test_excel_exporter_{timestamp}.xlsx"
    
    try:
        report_path = exporter.export_from_opportunities(
            opportunities=opportunities,
            filename=filename1,
            include_chart_data=True,
            include_help_sheet=True
        )
        
        if report_path:
            print(f"SUCCESS: Excel report saved to: {report_path}")
        else:
            print("ERROR: Excel export returned empty path!")
            
    except Exception as e:
        print(f"ERROR: Exception during export: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== Step 4: Test regular export with RankedOpportunity =====
    print("\n" + "-" * 70)
    print("Test 2: export (with RankedOpportunity)")
    print("-" * 70)
    
    try:
        from scoring.ranker import RankedOpportunity, StrategyMetrics
        
        ranked_opportunities = []
        for i, opp in enumerate(opportunities, 1):
            # Create metrics with sample values
            metrics = StrategyMetrics(
                win_rate=75.0 + i * 2,
                risk_reward_ratio=2.5 + i * 0.1,
                rom=15.0 + i * 2,
                margin_efficiency=0.05 + i * 0.01,
                max_profit=1000000.0 + i * 200000,
                max_loss=400000.0 + i * 50000,
                avg_profit=500000.0 + i * 100000,
                avg_loss=200000.0 + i * 30000,
                total_scenarios=20 + i * 2,
                profitable_scenarios=15 + i
            )
            
            ranked_opp = RankedOpportunity(
                strategy_name=opp.strategy_name,
                ticker=opp.underlying_ticker,
                legs=opp.legs,
                days_to_maturity=opp.days_to_maturity,
                metrics=metrics,
                raw_scores={
                    "win_rate": metrics.win_rate,
                    "risk_reward": metrics.risk_reward_ratio,
                    "rom": metrics.rom,
                },
                final_score=85.0 + i * 2,
                liquidity_score=opp.liquidity_score,
                rank=i
            )
            ranked_opportunities.append(ranked_opp)
        
        timestamp2 = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename2 = f"test_excel_ranked_{timestamp2}.xlsx"
        
        report_path2 = exporter.export(
            opportunities=ranked_opportunities,
            filename=filename2,
            include_chart_data=True,
            include_help_sheet=True
        )
        
        if report_path2:
            print(f"SUCCESS: Ranked Excel report saved to: {report_path2}")
        else:
            print("ERROR: Ranked Excel export returned empty path!")
            
    except Exception as e:
        print(f"ERROR: Exception during ranked export: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== Step 5: Verify files exist =====
    print("\n" + "-" * 70)
    print("Verifying output files")
    print("-" * 70)
    
    output_dir = Path("output")
    if output_dir.exists():
        files = list(output_dir.glob("test_excel*.xlsx"))
        if files:
            print(f"Found {len(files)} Excel files in output directory:")
            for f in files:
                size = f.stat().st_size
                print(f"  - {f.name} ({size:,} bytes)")
        else:
            print("No test Excel files found in output directory.")
    else:
        print("Output directory does not exist.")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    test_excel_exporter()