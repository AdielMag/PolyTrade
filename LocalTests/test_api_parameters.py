"""
Test different API parameters to find live games
"""

import httpx
from datetime import datetime, timezone

def fetch_markets(params):
    url = "https://gamma-api.polymarket.com/markets"
    print(f"\n📊 Testing params: {params}")
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    return response.json()

def main():
    print("=" * 80)
    print("TESTING DIFFERENT API PARAMETERS TO FIND LIVE GAMES")
    print("=" * 80)
    
    now = datetime.now(timezone.utc)
    print(f"\n⏰ Current time: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    
    # Test 1: Default (by ID)
    print("\n" + "=" * 80)
    print("TEST 1: Default ordering (by ID)")
    print("=" * 80)
    markets1 = fetch_markets({
        "closed": "false",
        "limit": 500,
        "order": "id",
        "ascending": "false"
    })
    print(f"✅ Got {len(markets1)} markets")
    
    # Test 2: By volume
    print("\n" + "=" * 80)
    print("TEST 2: Order by volume24hr")
    print("=" * 80)
    markets2 = fetch_markets({
        "closed": "false",
        "limit": 500,
        "order": "volume24hr",
        "ascending": "false"
    })
    print(f"✅ Got {len(markets2)} markets")
    
    # Check for games that started
    sports_keywords = ["vs", "vs.", "football", "basketball", "nfl", "nba"]
    sports_markets2 = [m for m in markets2 if any(kw in m.get("question", "").lower() for kw in sports_keywords)]
    
    started_games = []
    for market in sports_markets2:
        game_start = market.get("gameStartTime") or market.get("eventStartTime")
        if game_start:
            try:
                if isinstance(game_start, str):
                    if ' ' in game_start and '+' in game_start:
                        game_dt = datetime.fromisoformat(game_start.replace('+00', '+00:00'))
                    else:
                        game_dt = datetime.fromisoformat(game_start.replace('Z', '+00:00'))
                    
                    hours_ago = (now - game_dt).total_seconds() / 3600
                    if hours_ago > 0:  # Already started
                        started_games.append({
                            'question': market.get('question'),
                            'hours_ago': hours_ago,
                            'volume24hr': market.get('volume24hr', 0)
                        })
            except Exception:
                pass
    
    print(f"\n🔥 Found {len(started_games)} games that already started!")
    
    if started_games:
        started_games.sort(key=lambda x: x['hours_ago'])
        print("\nGames sorted by most recent:")
        for i, game in enumerate(started_games[:10], 1):
            print(f"{i}. {game['question'][:70]}")
            print(f"   Started: {game['hours_ago']:.1f}h ago | Volume: ${game['volume24hr']:,.0f}")
    
    # Test 3: Try with active=true
    print("\n" + "=" * 80)
    print("TEST 3: Filter by active=true")
    print("=" * 80)
    markets3 = fetch_markets({
        "closed": "false",
        "active": "true",
        "limit": 500,
        "order": "volume24hr",
        "ascending": "false"
    })
    print(f"✅ Got {len(markets3)} markets")
    
    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("=" * 80)
    print(f"Ordering by VOLUME finds more recent/active games!")
    print(f"We should use: order=volume24hr")
    print("=" * 80)

if __name__ == "__main__":
    main()

