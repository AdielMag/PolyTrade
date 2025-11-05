"""
Check what markets are actually live on Polymarket right now
"""

import httpx
from datetime import datetime, timezone

def main():
    print("=" * 80)
    print("CHECKING LIVE MARKETS ON POLYMARKET")
    print("=" * 80)
    
    now = datetime.now(timezone.utc)
    print(f"\n⏰ Current time: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    
    # Fetch sports markets
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "closed": "false",
        "limit": 500,
        "order": "id",
        "ascending": "false"
    }
    
    print(f"\n📊 Fetching markets from Polymarket...")
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    markets = response.json()
    
    # Filter for sports
    sports_keywords = ["vs", "vs.", "football", "basketball", "nfl", "nba"]
    sports_markets = [m for m in markets if any(kw in m.get("question", "").lower() for kw in sports_keywords)]
    
    print(f"✅ Found {len(sports_markets)} sports markets")
    
    # Check which ones have gameStartTime in the past (should be live)
    print("\n" + "=" * 80)
    print("CHECKING FOR MARKETS WHERE GAME ALREADY STARTED:")
    print("=" * 80)
    
    past_games = []
    
    for market in sports_markets:
        game_start = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        
        if game_start:
            try:
                if isinstance(game_start, str):
                    if ' ' in game_start and '+' in game_start:
                        game_dt = datetime.fromisoformat(game_start.replace('+00', '+00:00'))
                    else:
                        game_dt = datetime.fromisoformat(game_start.replace('Z', '+00:00'))
                    
                    time_diff_hours = (now - game_dt).total_seconds() / 3600
                    
                    # Game started in the past (negative hours_until means started)
                    if time_diff_hours > 0:  # Game already started
                        past_games.append({
                            'market': market,
                            'hours_ago': time_diff_hours,
                            'game_start': game_dt
                        })
            except Exception as e:
                pass
    
    print(f"\n✅ Found {len(past_games)} markets where game already started\n")
    
    if past_games:
        # Sort by most recent
        past_games.sort(key=lambda x: x['hours_ago'])
        
        print("GAMES THAT ALREADY STARTED (most recent first):")
        print("-" * 80)
        
        for i, game_info in enumerate(past_games[:20], 1):  # Show first 20
            market = game_info['market']
            hours_ago = game_info['hours_ago']
            
            question = market.get('question', 'Unknown')
            closed = market.get('closed', False)
            accepting_orders = market.get('acceptingOrders', False)
            active = market.get('active', False)
            
            status_flags = []
            if closed:
                status_flags.append("❌ CLOSED")
            if accepting_orders:
                status_flags.append("✅ ACCEPTING ORDERS")
            if active:
                status_flags.append("🟢 ACTIVE")
            
            status_str = " | ".join(status_flags) if status_flags else "⚠️ Unknown status"
            
            print(f"\n{i}. {question[:65]}")
            print(f"   Started: {hours_ago:.1f}h ago")
            print(f"   Status: {status_str}")
            print(f"   Game start time: {game_info['game_start'].strftime('%Y-%m-%d %H:%M UTC')}")
            
            # Check if within our 2-hour window
            if 0 < hours_ago <= 2:
                print(f"   ✅ WITHIN 2-HOUR WINDOW - Should appear in LIVE filter!")
    else:
        print("❌ No games found that already started")
        print("\nShowing next 5 upcoming games:")
        
        upcoming = []
        for market in sports_markets:
            game_start = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
            if game_start:
                try:
                    if isinstance(game_start, str):
                        if ' ' in game_start and '+' in game_start:
                            game_dt = datetime.fromisoformat(game_start.replace('+00', '+00:00'))
                        else:
                            game_dt = datetime.fromisoformat(game_start.replace('Z', '+00:00'))
                        
                        hours_until = (game_dt - now).total_seconds() / 3600
                        if hours_until > 0:
                            upcoming.append({
                                'question': market.get('question', 'Unknown'),
                                'hours_until': hours_until,
                                'game_start': game_dt
                            })
                except Exception:
                    pass
        
        upcoming.sort(key=lambda x: x['hours_until'])
        for i, game in enumerate(upcoming[:5], 1):
            print(f"{i}. {game['question'][:60]} - in {game['hours_until']:.1f}h")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

