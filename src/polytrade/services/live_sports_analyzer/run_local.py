#!/usr/bin/env python3
"""
Local runner for the Live Sports Analyzer.

Run this script directly to analyze live sports markets without starting the FastAPI server.
"""

from __future__ import annotations

from live_sports_analysis import run_live_sports_analysis
from ...shared.logging import configure_logging


def main():
    """Run the live sports analyzer locally."""
    configure_logging()
    
    print("\n")
    print("=" * 80)
    print("LIVE SPORTS MARKET ANALYZER - LOCAL RUNNER")
    print("=" * 80)
    print("\n")
    
    # Run analysis with default parameters
    live_markets = run_live_sports_analysis(
        max_workers=10,        # Use 10 concurrent threads for fetching
        lookback_hours=4.0     # Include games started within last 4 hours
    )
    
    print("\n")
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"✅ Found and logged {len(live_markets)} live sports markets")
    print("=" * 80)
    print("\n")
    
    return live_markets


if __name__ == "__main__":
    main()

