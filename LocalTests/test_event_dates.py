"""
Test script to check Polymarket event dates.

This script fetches some markets and inspects their date fields to understand:
1. What does 'endDate' represent?
2. Are there other date fields (like eventStartDate)?
3. How do these dates relate to the actual event time?
"""

import httpx
import json
from datetime import datetime

def main():
    print("=" * 80)
    print("POLYMARKET EVENT DATE ANALYSIS")
    print("=" * 80)
    
    # Fetch markets from Polymarket
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "closed": "false",
        "limit": 20,
        "order": "id",
        "ascending": "false"
    }
    
    print(f"\n📊 Fetching markets from: {url}")
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    markets = response.json()
    
    print(f"✅ Fetched {len(markets)} markets\n")
    
    # Analyze date fields
    print("=" * 80)
    print("ANALYZING DATE FIELDS IN MARKETS:")
    print("=" * 80)
    
    # Check first market in detail
    if markets:
        first_market = markets[0]
        print("\n📋 FIRST MARKET - ALL FIELDS:")
        print("-" * 80)
        for key, value in first_market.items():
            if 'date' in key.lower() or 'time' in key.lower() or key in ['startDate', 'endDate', 'eventStartDate', 'eventEndDate']:
                print(f"  {key}: {value}")
        print("-" * 80)
    
    # Look for sports markets specifically
    print("\n🏈 LOOKING FOR SPORTS MARKETS:")
    print("-" * 80)
    
    sports_keywords = ["vs", "vs.", "nfl", "nba", "football", "basketball"]
    sports_markets_found = 0
    
    for i, market in enumerate(markets):
        question = market.get("question", "")
        
        # Check if it's a sports market
        is_sports = any(keyword in question.lower() for keyword in sports_keywords)
        
        if is_sports and sports_markets_found < 5:  # Show first 5 sports markets
            sports_markets_found += 1
            print(f"\n📌 SPORTS MARKET #{sports_markets_found}:")
            print(f"   Question: {question[:80]}")
            
            # Show all date-related fields
            end_date = market.get("endDate")
            start_date = market.get("startDate")
            
            print(f"   startDate: {start_date}")
            print(f"   endDate: {end_date}")
            
            # Check for other date fields
            for key in market.keys():
                if 'date' in key.lower() or 'time' in key.lower():
                    if key not in ['startDate', 'endDate']:
                        print(f"   {key}: {market[key]}")
            
            # Parse and display endDate in readable format
            if end_date:
                try:
                    dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    now = datetime.now(dt.tzinfo)
                    time_until = dt - now
                    
                    print(f"   📅 End Date: {dt.strftime('%A, %B %d, %Y at %H:%M UTC')}")
                    print(f"   ⏰ Time until end: {time_until.days} days, {time_until.seconds // 3600} hours")
                except Exception as e:
                    print(f"   ⚠️ Could not parse date: {e}")
            
            print("-" * 80)
    
    if sports_markets_found == 0:
        print("   ⚠️ No sports markets found in first 20 markets")
        print("   Showing first 3 markets with dates instead:\n")
        
        for i, market in enumerate(markets[:3]):
            print(f"\n📌 MARKET #{i+1}:")
            print(f"   Question: {market.get('question', '')[:80]}")
            print(f"   endDate: {market.get('endDate')}")
            
            if market.get("endDate"):
                try:
                    dt = datetime.fromisoformat(market['endDate'].replace('Z', '+00:00'))
                    print(f"   📅 {dt.strftime('%A, %B %d, %Y at %H:%M UTC')}")
                except Exception:
                    pass
            print("-" * 80)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    
    # Count how many have endDate
    markets_with_end_date = sum(1 for m in markets if m.get("endDate"))
    print(f"Markets with endDate: {markets_with_end_date}/{len(markets)}")
    
    # Check for other date fields
    date_fields = set()
    for market in markets:
        for key in market.keys():
            if 'date' in key.lower() or 'time' in key.lower():
                date_fields.add(key)
    
    print(f"\nAll date/time fields found: {sorted(date_fields)}")
    
    print("\n💡 INTERPRETATION:")
    print("-" * 80)
    print("The 'endDate' field represents when the market CLOSES for trading.")
    print("This is typically set to a time AFTER the actual event happens.")
    print("For sports games, this might be hours or days after the game ends.")
    print("\nFor real-time trading, you might want to:")
    print("  1. Use endDate to know when the market closes")
    print("  2. Parse the question text for actual game/event times")
    print("  3. Check if there are other APIs that provide event start times")
    print("=" * 80)

if __name__ == "__main__":
    main()

