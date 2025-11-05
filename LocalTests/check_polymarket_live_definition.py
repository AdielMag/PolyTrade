"""
Check what Polymarket means by "live" markets
Could be: high volume, accepting orders, high liquidity, etc.
"""

import httpx
from datetime import datetime, timezone

def main():
    print("=" * 80)
    print("INVESTIGATING POLYMARKET 'LIVE' MARKET DEFINITION")
    print("=" * 80)
    
    # Fetch markets
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "closed": "false",
        "limit": 500,
        "order": "volume24hr",  # Try ordering by volume
        "ascending": "false"
    }
    
    print(f"\n📊 Fetching top volume markets...")
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    markets = response.json()
    
    # Filter for sports
    sports_keywords = ["vs", "vs.", "football", "basketball", "nfl", "nba", "spread", "o/u"]
    sports_markets = [m for m in markets if any(kw in m.get("question", "").lower() for kw in sports_keywords)]
    
    print(f"✅ Found {len(sports_markets)} sports markets")
    
    print("\n" + "=" * 80)
    print("TOP 20 SPORTS MARKETS BY 24H VOLUME (Possible 'Live' candidates):")
    print("=" * 80)
    
    now = datetime.now(timezone.utc)
    
    for i, market in enumerate(sports_markets[:20], 1):
        question = market.get('question', 'Unknown')
        volume_24hr = market.get('volume24hr', 0) or 0
        liquidity = market.get('liquidityClob', 0) or market.get('liquidity', 0) or 0
        accepting_orders = market.get('acceptingOrders', False)
        active = market.get('active', False)
        
        # Get game time
        game_start = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        time_str = "Unknown"
        if game_start:
            try:
                if isinstance(game_start, str):
                    if ' ' in game_start and '+' in game_start:
                        game_dt = datetime.fromisoformat(game_start.replace('+00', '+00:00'))
                    else:
                        game_dt = datetime.fromisoformat(game_start.replace('Z', '+00:00'))
                    
                    hours_diff = (game_dt - now).total_seconds() / 3600
                    if hours_diff > 0:
                        time_str = f"in {hours_diff:.1f}h"
                    else:
                        time_str = f"started {abs(hours_diff):.1f}h ago"
            except Exception:
                pass
        
        print(f"\n{i}. {question[:65]}")
        print(f"   24h Volume: ${volume_24hr:,.0f}")
        print(f"   Liquidity: ${liquidity:,.0f}")
        print(f"   Game time: {time_str}")
        print(f"   Accepting orders: {'✅ YES' if accepting_orders else '❌ NO'}")
        print(f"   Active: {'✅ YES' if active else '❌ NO'}")
    
    print("\n" + "=" * 80)
    print("HYPOTHESIS:")
    print("=" * 80)
    print("Polymarket 'Live' markets might mean:")
    print("  1. High 24-hour trading volume (active betting)")
    print("  2. Markets accepting orders")
    print("  3. Markets with high liquidity")
    print("  4. Popular/trending markets")
    print("")
    print("NOT necessarily:")
    print("  ❌ Games currently being played")
    print("")
    print("Our LIVE filter is correct for 'games in progress'")
    print("But Polymarket's website 'live' might mean 'actively trading'")
    print("=" * 80)

if __name__ == "__main__":
    main()

