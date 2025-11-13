"""
Quick test script - just copy-paste this into your Python interpreter or run directly.
This will test the Live Sports Analyzer without any complex setup.
"""

if __name__ == "__main__":
    import sys
    import os
    
    # Fix encoding for Windows console
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    # Add src to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    
    print("\n" + "=" * 80)
    print("QUICK TEST: Live Sports Analyzer")
    print("=" * 80 + "\n")
    
    try:
        # Import the analyzer
        print("⏳ Importing modules...")
        from polytrade.services.live_sports_analyzer.live_sports_analysis import run_live_sports_analysis
        print("✅ Import successful!\n")
        
        # Run the analysis with filter parameters
        print("🚀 Starting analysis...")
        print("   This will fetch ALL sports markets and find live ones")
        print("   Using pagination + multithreading for speed")
        print("   Filters: Liquidity > $500, Ask price 93-96%\n")
        
        filtered_markets = run_live_sports_analysis(
            max_workers=15,         # 10 concurrent threads
            lookback_hours=4.0,      # Games started within last 4 hours
            min_liquidity=500.0,    # Minimum liquidity $500
            min_ask_price=0.93,     # Minimum ask price 93%
            max_ask_price=0.96      # Maximum ask price 96%
        )
        
        print("\n" + "=" * 80)
        print(f"✅ Analysis complete - found {len(filtered_markets)} markets matching all criteria")
        print("   (All filtering and notifications handled by the analysis function)")
        print("=" * 80 + "\n")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nMake sure you're running from the project root directory!")
        print("Current directory:", os.getcwd())
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

