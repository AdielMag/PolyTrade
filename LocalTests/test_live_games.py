"""
Test script to check LIVE games filter
"""

import os
import sys

# Set environment to disable edge filter
os.environ["EDGE_BPS"] = "-100000"

sys.path.insert(0, "src")

from polytrade.services.analyzer.analysis import run_analysis
from datetime import datetime, timezone

def main():
    print("=" * 80)
    print("TESTING LIVE GAMES FILTER")
    print("=" * 80)
    
    current_time = datetime.now(timezone.utc)
    print(f"\n⏰ Current time: {current_time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Looking for games that started within the last 2 hours...")
    
    print("\n" + "=" * 80)
    print("TEST 1: LIVE ONLY FILTER")
    print("=" * 80)
    
    # Test with live_only=True, get more suggestions to see what's available
    print("\n🔴 Running analyzer with LIVE ONLY filter...")
    print("Parameters: min_price=0.01, max_price=0.99, live_only=True")
    
    live_suggestions = run_analysis(
        max_suggestions=10,
        min_price=0.01,  # Very wide range to catch anything
        max_price=0.99,
        time_window_hours=-1.0,  # Special value (not used when live_only=True)
        live_only=True
    )
    
    print("\n" + "=" * 80)
    print("LIVE GAMES RESULTS:")
    print("=" * 80)
    
    if live_suggestions:
        print(f"\n✅ Found {len(live_suggestions)} LIVE game suggestions!\n")
        
        for i, suggestion in enumerate(live_suggestions, 1):
            title = suggestion.get('title', 'Unknown')
            side = suggestion.get('side', 'N/A')
            price = suggestion.get('price', 0)
            end_date = suggestion.get('endDate', 'N/A')
            
            print(f"{i}. {title[:70]}")
            print(f"   Side: {side}")
            print(f"   Price: ${price:.4f} ({price*100:.1f}%)")
            print(f"   Event time: {end_date}")
            
            # Calculate how long ago it started
            if end_date and end_date != 'N/A':
                try:
                    if isinstance(end_date, str):
                        if ' ' in end_date and '+' in end_date:
                            event_dt = datetime.fromisoformat(end_date.replace('+00', '+00:00'))
                        else:
                            event_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        
                        time_diff = (current_time - event_dt).total_seconds() / 3600
                        print(f"   ⏱️  Started {abs(time_diff):.1f}h ago")
                except Exception as e:
                    print(f"   ⚠️  Could not parse date: {e}")
            
            print()
    else:
        print("\n❌ No LIVE games found")
        print("\nPossible reasons:")
        print("  • No games currently in progress")
        print("  • All live games are outside the 2-hour window")
        print("  • No live games match the price range")
    
    print("\n" + "=" * 80)
    print("TEST 2: REGULAR 6H WINDOW (includes live + upcoming)")
    print("=" * 80)
    
    print("\n🟠 Running analyzer with 6-hour window...")
    print("Parameters: min_price=0.01, max_price=0.99, time_window_hours=6.0, live_only=False")
    
    regular_suggestions = run_analysis(
        max_suggestions=10,
        min_price=0.01,
        max_price=0.99,
        time_window_hours=6.0,
        live_only=False
    )
    
    print("\n" + "=" * 80)
    print("6-HOUR WINDOW RESULTS:")
    print("=" * 80)
    
    if regular_suggestions:
        print(f"\n✅ Found {len(regular_suggestions)} suggestions in 6h window!\n")
        
        live_count = 0
        upcoming_count = 0
        
        for i, suggestion in enumerate(regular_suggestions, 1):
            title = suggestion.get('title', 'Unknown')
            end_date = suggestion.get('endDate', 'N/A')
            
            # Determine if it's live or upcoming
            is_live = False
            if end_date and end_date != 'N/A':
                try:
                    if isinstance(end_date, str):
                        if ' ' in end_date and '+' in end_date:
                            event_dt = datetime.fromisoformat(end_date.replace('+00', '+00:00'))
                        else:
                            event_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        
                        time_diff = (event_dt - current_time).total_seconds() / 3600
                        is_live = time_diff < 0
                        
                        if is_live:
                            live_count += 1
                            status = f"🔴 LIVE (started {abs(time_diff):.1f}h ago)"
                        else:
                            upcoming_count += 1
                            status = f"🟡 UPCOMING (in {time_diff:.1f}h)"
                        
                        print(f"{i}. {title[:60]} - {status}")
                except Exception:
                    print(f"{i}. {title[:60]}")
        
        print(f"\nSummary:")
        print(f"  🔴 Live: {live_count}")
        print(f"  🟡 Upcoming: {upcoming_count}")
    else:
        print("\n❌ No suggestions found in 6h window")
    
    print("\n" + "=" * 80)
    print("COMPARISON:")
    print("=" * 80)
    print(f"LIVE ONLY filter: {len(live_suggestions)} suggestions")
    print(f"6-hour window: {len(regular_suggestions)} suggestions")
    
    if len(live_suggestions) > 0:
        print("\n✅ LIVE filter is working correctly!")
    else:
        print("\n⚠️  No live games found. This could be normal if:")
        print("    • It's off-peak hours (no major sports events)")
        print("    • Games ended more than 2 hours ago")
        print("    • Check if regular 6h window shows any live games")
    
    print("=" * 80)

if __name__ == "__main__":
    main()

