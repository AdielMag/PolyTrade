"""
Test script for the Live Sports Analyzer service.

This script demonstrates how to use the new live_sports_analyzer service
to fetch and analyze all live sports markets from Polymarket.
"""

import sys
from pathlib import Path

# Add src to path  
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Suppress httpx logging for cleaner output
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)

from polytrade.services.live_sports_analyzer.live_sports_analysis import run_live_sports_analysis


def main():
    """Run the live sports market analysis."""
    print("=" * 80)
    print("TESTING LIVE SPORTS ANALYZER")
    print("=" * 80)
    print()
    print("This will:")
    print("  1. Fetch ALL sports markets using pagination and multithreading")
    print("  2. Filter for LIVE markets (games that have started)")
    print("  3. Log comprehensive details for each live market")
    print()
    print("=" * 80)
    print()
    
    # Run the analysis
    # Parameters:
    #   - max_workers: Number of concurrent threads (default: 10)
    #   - lookback_hours: How many hours back to include live games (default: 4.0)
    live_markets = run_live_sports_analysis(
        max_workers=10,
        lookback_hours=4.0
    )
    
    print()
    print("=" * 80)
    print(f"✅ FOUND {len(live_markets)} LIVE SPORTS MARKETS")
    print("=" * 80)
    
    if live_markets:
        print()
        print("Sample market data structure:")
        print(f"  Keys available: {list(live_markets[0].keys())[:10]}...")
    
    return live_markets


if __name__ == "__main__":
    main()

