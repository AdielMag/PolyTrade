"""
Debug why live games aren't showing up in 80-90% range
Check actual prices and liquidity of live markets
"""

import os
os.environ["EDGE_BPS"] = "-100000"  # Disable edge filter

import sys
sys.path.insert(0, "src")

from polytrade.shared.polymarket_client import PolymarketClient
from datetime import datetime, timezone, timedelta
import time

def main():
    print("=" * 80)
    print("DEBUGGING LIVE GAME PRICES (80-90% RANGE)")
    print("=" * 80)
    
    client = PolymarketClient(require_auth=False)
    
    print("\n📊 Fetching markets...")
    markets = client.list_markets()
    print(f"✅ Fetched {len(markets)} markets")
    
    # Find live games (within 6 hours or already started)
    now_dt = datetime.now(timezone.utc)
    six_hours_from_now = now_dt + timedelta(hours=6)
    
    live_markets = []
    
    for market in markets:
        end_date_str = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        if end_date_str:
            try:
                if isinstance(end_date_str, str):
                    if ' ' in end_date_str and '+' in end_date_str:
                        end_dt = datetime.fromisoformat(end_date_str.replace('+00', '+00:00'))
                    else:
                        end_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    end_dt = end_date_str
                
                time_until = (end_dt - now_dt).total_seconds()
                hours_until = time_until / 3600
                
                if hours_until <= 6:
                    market['_hours_until'] = hours_until
                    live_markets.append(market)
            except Exception:
                pass
    
    print(f"✅ Found {len(live_markets)} live/urgent markets")
    
    # Analyze each live market
    print("\n" + "=" * 80)
    print("ANALYZING LIVE MARKETS:")
    print("=" * 80)
    
    in_range_count = 0
    
    for i, market in enumerate(live_markets[:15], 1):  # Check first 15
        question = market.get("question", "")
        hours = market.get('_hours_until', 0)
        
        if hours < 0:
            status = f"🔴 LIVE (started {abs(hours):.1f}h ago)"
        else:
            status = f"🟡 Starting in {hours:.1f}h"
        
        print(f"\n{i}. {question[:70]}")
        print(f"   {status}")
        
        # Get tokens and check prices
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", ["YES", "NO"])
        liquidity = market.get("liquidityClob", 0) or market.get("liquidity", 0)
        
        print(f"   💧 Liquidity: ${liquidity:,.2f}")
        
        if not clob_token_ids:
            print(f"   ❌ No token IDs")
            continue
        
        if liquidity < 1000:
            print(f"   ❌ Low liquidity (< $1000)")
            continue
        
        # Check each outcome
        for token_id, outcome in zip(clob_token_ids, outcomes):
            try:
                quotes = client.get_quotes(token_id)
                ask = quotes.get("best_ask", 0)
                bid = quotes.get("best_bid", 0)
                
                if ask > 0:
                    ask_pct = ask * 100
                    
                    # Check if in 80-90% range
                    in_range = 80 <= ask_pct <= 90
                    
                    if in_range:
                        in_range_count += 1
                        print(f"   ✅ {outcome}: ${ask:.4f} ({ask_pct:.1f}%) - IN RANGE!")
                    else:
                        print(f"   📊 {outcome}: ${ask:.4f} ({ask_pct:.1f}%)")
                    
                    # Also show bid
                    if bid > 0:
                        print(f"      Bid: ${bid:.4f} ({bid*100:.1f}%)")
                
                time.sleep(0.05)  # Rate limit protection
                
            except Exception as e:
                print(f"   ⚠️ Error getting quotes for {outcome}: {e}")
    
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Live/urgent markets: {len(live_markets)}")
    print(f"  Markets analyzed: {min(15, len(live_markets))}")
    print(f"  ✅ Markets with prices in 80-90% range: {in_range_count}")
    print("=" * 80)
    
    if in_range_count == 0:
        print("\n💡 NO MARKETS IN 80-90% RANGE")
        print("   Try different ranges:")
        print("   • 60-75% (moderate favorites)")
        print("   • 40-60% (balanced games)")
        print("   • 20-40% (underdogs)")

if __name__ == "__main__":
    main()

