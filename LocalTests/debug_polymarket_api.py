#!/usr/bin/env python3
"""
Debug script to see what the Polymarket Gamma API actually returns.
"""
import httpx
import json

url = "https://gamma-api.polymarket.com/markets"
params = {
    "active": "true",
    "closed": "false", 
    "tag": "sports",
    "limit": 5  # Just get 5 for inspection
}

print("=" * 80)
print("🔍 DEBUGGING POLYMARKET GAMMA API")
print("=" * 80)
print()
print(f"URL: {url}")
print(f"Params: {json.dumps(params, indent=2)}")
print()

try:
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    markets = response.json()
    
    print(f"✅ Response received - {len(markets)} markets")
    print()
    
    if markets:
        print("=" * 80)
        print("FIRST MARKET (FULL JSON):")
        print("=" * 80)
        print(json.dumps(markets[0], indent=2))
        print()
        
        print("=" * 80)
        print("AVAILABLE FIELDS IN FIRST MARKET:")
        print("=" * 80)
        for key in markets[0].keys():
            value = markets[0][key]
            value_type = type(value).__name__
            if isinstance(value, (list, dict)):
                value_preview = f"{value_type} with {len(value)} items"
            else:
                value_str = str(value)
                value_preview = value_str[:50] + "..." if len(value_str) > 50 else value_str
            print(f"  {key:20s} : {value_type:10s} = {value_preview}")
        
        print()
        print("=" * 80)
        print("CHECKING ALL MARKETS FOR 'tokens' FIELD:")
        print("=" * 80)
        for i, market in enumerate(markets, 1):
            has_tokens = 'tokens' in market
            has_clob_token_ids = 'clobTokenIds' in market
            has_outcomes = 'outcomes' in market
            
            print(f"Market #{i}: {market.get('question', 'N/A')[:60]}")
            print(f"  tokens: {has_tokens}")
            print(f"  clobTokenIds: {has_clob_token_ids}")
            print(f"  outcomes: {has_outcomes}")
            
            if has_clob_token_ids:
                print(f"  clobTokenIds value: {market.get('clobTokenIds')}")
            if has_outcomes:
                print(f"  outcomes value: {market.get('outcomes')}")
            print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    print(traceback.format_exc())

