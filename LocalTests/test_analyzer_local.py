#!/usr/bin/env python3
"""
Local test script to run the analyzer and debug suggestion generation.

This script runs the analyzer locally to see:
1. How many markets are fetched
2. How many pass each filter
3. What suggestions are generated
4. Why markets might be filtered out

Usage:
    python LocalTests/test_analyzer_local.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Set environment variable to disable edge filter
os.environ["EDGE_BPS"] = "-10000"

# Add src directory to path so we can import polytrade modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from polytrade.services.analyzer.analysis import run_analysis
from polytrade.shared.logging import configure_logging

def main():
    """Run the analyzer locally and display results."""
    print("=" * 80)
    print("🔍 RUNNING ANALYZER LOCALLY")
    print("=" * 80)
    print()
    
    # Configure logging to see detailed output
    configure_logging()
    
    print("📊 Starting analysis...")
    print("   This will fetch markets and analyze them.")
    print("   Check the logs above for detailed filtering information.")
    print()
    
    try:
        # Run the analyzer
        suggestions = run_analysis(max_suggestions=5)
        
        print()
        print("=" * 80)
        print("📋 RESULTS SUMMARY")
        print("=" * 80)
        print()
        
        if not suggestions:
            print("❌ NO SUGGESTIONS GENERATED")
            print()
            print("Possible reasons:")
            print("  1. No markets matched the price range (0.70-0.85)")
            print("  2. Liquidity too low (check MIN_LIQUIDITY_USD setting)")
            print("  3. Edge too small (check EDGE_BPS setting)")
            print("  4. No sports markets available")
            print("  5. API returned no markets")
            print()
            print("💡 Check the detailed logs above to see why markets were filtered out")
        else:
            print(f"✅ GENERATED {len(suggestions)} SUGGESTION(S)")
            print()
            
            for i, suggestion in enumerate(suggestions, 1):
                print(f"📌 Suggestion #{i}:")
                print(f"   Title: {suggestion.get('title', 'N/A')[:70]}")
                print(f"   Token ID: {suggestion.get('tokenId', 'N/A')}")
                print(f"   Side: {suggestion.get('side', 'N/A')}")
                print(f"   Edge: {suggestion.get('edgeBps', 0)} bps")
                print(f"   Price: ${suggestion.get('price', 0):.4f}")
                print(f"   Fair Value: ${suggestion.get('fairValue', 0):.4f}")
                print(f"   Liquidity: ${suggestion.get('liquidity', 0):.2f}")
                print(f"   Size Hint: ${suggestion.get('sizeHint', 0):.2f}")
                print(f"   Status: {suggestion.get('status', 'N/A')}")
                print()
        
        print("=" * 80)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 80)
        
        return 0 if suggestions else 1
        
    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR RUNNING ANALYZER")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        print()
        
        import traceback
        print("Full traceback:")
        print(traceback.format_exc())
        
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

