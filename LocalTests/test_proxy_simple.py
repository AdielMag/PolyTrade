#!/usr/bin/env python3
"""Simple test to check if a proxy address has positions."""

import httpx

proxy_address = "0xc20B377471Ac4d42921F76bA0Fb7cC6aCd1dBA2f"

print("=" * 80)
print("TESTING POLYMARKET PROXY ADDRESS")
print("=" * 80)
print()
print(f"Proxy Address: {proxy_address}")
print()
print("Making API call to Polymarket Data API...")
print()

try:
    url = f"https://data-api.polymarket.com/positions?user={proxy_address}&sizeThreshold=0"
    print(f"URL: {url}")
    print()
    
    response = httpx.get(url, timeout=30.0)
    print(f"Status Code: {response.status_code}")
    print()
    
    positions = response.json()
    print(f"Number of Positions: {len(positions)}")
    print()
    
    if len(positions) > 0:
        print("=" * 80)
        print("✅ SUCCESS! POSITIONS FOUND:")
        print("=" * 80)
        
        total_value = 0
        for i, pos in enumerate(positions, 1):
            current_value = pos.get('currentValue', 0)
            total_value += current_value
            
            print(f"\n  Position {i}:")
            print(f"    Market: {pos.get('title', 'N/A')[:60]}")
            print(f"    Outcome: {pos.get('outcome', 'N/A')}")
            print(f"    Size: {pos.get('size', 0)}")
            print(f"    Current Value: ${current_value:.2f}")
            print(f"    P&L: ${pos.get('cashPnl', 0):+.2f}")
        
        print()
        print("=" * 80)
        print(f"TOTAL PORTFOLIO VALUE: ${total_value:.2f}")
        print("=" * 80)
        print()
        print("✅ This proxy address is CORRECT!")
        print("   Your positions are on this address.")
        print()
        print("Make sure your Cloud Run environment has:")
        print(f"   POLYMARKET_PROXY_ADDRESS={proxy_address}")
        
    else:
        print("=" * 80)
        print("⚠️  NO POSITIONS FOUND")
        print("=" * 80)
        print()
        print("This could mean:")
        print("  1. You don't have any open positions on Polymarket")
        print("  2. This is not the correct proxy address")
        print("  3. Your positions are on a different address")
        print()
        print("To verify, check polymarket.com:")
        print("  1. Go to polymarket.com")
        print("  2. Connect your wallet")
        print("  3. Go to your portfolio/positions")
        print("  4. Open browser DevTools (F12) → Network tab")
        print("  5. Look for API calls to 'positions?user=0x...'")
        print("  6. Compare that address with the one above")
    
except Exception as e:
    print("=" * 80)
    print("❌ ERROR:")
    print("=" * 80)
    print(f"{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)

