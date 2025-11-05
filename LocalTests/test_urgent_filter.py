"""
Test the 6-hour urgent filter to find live/imminent games like "Oilers vs Stars"
"""

import os
os.environ["EDGE_BPS"] = "-100000"  # Disable edge filter

from datetime import datetime, timezone
import httpx

def main():
    print("=" * 80)
    print("TESTING 6-HOUR URGENT FILTER")
    print("=" * 80)
    
    # Fetch markets
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "closed": "false",
        "limit": 500,
        "order": "id",
        "ascending": "false"
    }
    
    print(f"\n📊 Fetching markets...")
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    markets = response.json()
    print(f"✅ Fetched {len(markets)} total markets")
    
    # Filter for sports
    sports_keywords = [
        "vs", "vs.", "football", "basketball", "baseball", "soccer", "nfl", "nba", 
        "mlb", "nhl", "tennis", "golf", "boxing", "mma", "ufc", "oilers", "stars"
    ]
    
    sports_markets = []
    for market in markets:
        question = market.get("question", "").lower()
        if any(keyword in question for keyword in sports_keywords):
            sports_markets.append(market)
    
    print(f"✅ Found {len(sports_markets)} sports markets")
    
    # Apply 6-hour filter
    now_dt = datetime.now(timezone.utc)
    from datetime import timedelta
    six_hours_from_now = now_dt + timedelta(hours=6)
    
    print(f"\n🔥 APPLYING 6-HOUR FILTER:")
    print(f"⏰ Current time: {now_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"⏰ Cut-off time: {six_hours_from_now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)
    
    urgent_markets = []
    
    for market in sports_markets:
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
                
                # Only include if <= 6 hours
                if hours_until <= 6:
                    market['_time_until'] = time_until
                    market['_hours_until'] = hours_until
                    urgent_markets.append(market)
            except Exception:
                pass
    
    # Sort by urgency
    urgent_markets.sort(key=lambda m: m.get('_time_until', float('inf')))
    
    print(f"\n✅ Found {len(urgent_markets)} URGENT markets (≤6h or live)")
    print("=" * 80)
    
    # Display urgent markets
    if urgent_markets:
        print("\n🔥 URGENT OPPORTUNITIES:")
        print("=" * 80)
        
        for i, market in enumerate(urgent_markets[:20], 1):  # Show first 20
            question = market.get("question", "")
            hours = market['_hours_until']
            
            if hours < 0:
                hours_ago = abs(hours)
                status = f"🔴 LIVE (started {hours_ago:.1f}h ago)"
            elif hours < 1:
                minutes = int(hours * 60)
                status = f"🔴 STARTING IN {minutes} MINUTES!"
            else:
                hours_int = int(hours)
                minutes = int((hours - hours_int) * 60)
                status = f"🟡 Starts in {hours_int}h {minutes}m"
            
            print(f"\n{i}. {question[:70]}")
            print(f"   {status}")
            
            # Show if it matches "Oilers vs Stars"
            if "oilers" in question.lower() or "stars" in question.lower():
                print(f"   ⭐ MATCHES YOUR EXAMPLE!")
    else:
        print("\n❌ No urgent markets found in next 6 hours")
        print("💡 Try checking again during peak sports hours")
    
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Total markets: {len(markets)}")
    print(f"  Sports markets: {len(sports_markets)}")
    print(f"  🔥 Urgent (≤6h): {len(urgent_markets)}")
    print("=" * 80)

if __name__ == "__main__":
    main()

