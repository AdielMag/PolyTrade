#!/usr/bin/env python3
"""Script to find your Polymarket proxy wallet address."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("=" * 80)
    print("FINDING YOUR POLYMARKET PROXY WALLET ADDRESS")
    print("=" * 80)
    print()
    
    # Check for .env
    if not os.path.exists('.env'):
        print("❌ No .env file found!")
        print()
        print("Please create a .env file with:")
        print("  WALLET_PRIVATE_KEY=0x...")
        print()
        return
    
    try:
        from polytrade.shared.polymarket_client import PolymarketClient
        from polytrade.shared.config import settings
        
        print("📋 Loading configuration...")
        print(f"   WALLET_PRIVATE_KEY: {'✅ Set' if settings.wallet_private_key else '❌ Missing'}")
        print(f"   Current PROXY_ADDRESS: {settings.proxy_address or 'Not set'}")
        print()
        
        print("🔧 Creating Polymarket client...")
        client = PolymarketClient()
        print("✅ Client created successfully")
        print()
        
        # Get the wallet address
        wallet_address = client.client.get_address()
        print("=" * 80)
        print("YOUR ADDRESSES:")
        print("=" * 80)
        print(f"💼 Wallet Address (EOA):  {wallet_address}")
        print(f"   This is derived from your private key")
        print()
        
        # Try to get proxy address from the client
        # The proxy/funder address is what you configure during setup
        if hasattr(client.client, 'funder') and client.client.funder:
            proxy = client.client.funder
            print(f"🏦 Proxy Address (Funder): {proxy}")
            print(f"   This is your Polymarket proxy wallet")
            print()
            print("✅ Found your proxy address!")
            print()
            print("=" * 80)
            print("ADD THIS TO YOUR .ENV FILE:")
            print("=" * 80)
            print(f"POLYMARKET_PROXY_ADDRESS={proxy}")
            print("=" * 80)
        else:
            print("⚠️  No proxy/funder address found in client")
            print()
            print("=" * 80)
            print("HOW TO FIND YOUR PROXY ADDRESS:")
            print("=" * 80)
            print()
            print("Option 1: Check Polymarket website")
            print("  1. Go to polymarket.com")
            print("  2. Connect your wallet")
            print("  3. Open browser DevTools (F12)")
            print("  4. Go to Network tab")
            print("  5. Navigate to your portfolio/positions")
            print("  6. Look for API calls to 'positions?user=0x...'")
            print("  7. The 0x... address in the URL is your proxy address")
            print()
            print("Option 2: Check your transactions on Polygonscan")
            print("  1. Go to polygonscan.com")
            print(f"  2. Search for your wallet: {wallet_address}")
            print("  3. Look at 'Internal Transactions'")
            print("  4. Find Polymarket-related transactions")
            print("  5. Look for the proxy wallet contract address")
            print()
            print("Option 3: Make a trade on Polymarket first")
            print("  If you haven't made any trades yet, you might not have")
            print("  a proxy wallet created. Your first trade will create it.")
            print()
        
        # Test if we can fetch positions with current addresses
        print()
        print("=" * 80)
        print("TESTING API ACCESS:")
        print("=" * 80)
        print()
        
        import httpx
        
        # Test wallet address
        print(f"Testing wallet address: {wallet_address}")
        try:
            response = httpx.get(
                f"https://data-api.polymarket.com/positions?user={wallet_address}&sizeThreshold=0",
                timeout=10.0
            )
            positions_wallet = response.json()
            print(f"  Result: {len(positions_wallet)} positions found")
            if len(positions_wallet) > 0:
                print(f"  ✅ Your positions are on your WALLET address!")
                print()
                print("=" * 80)
                print("YOU DON'T NEED POLYMARKET_PROXY_ADDRESS!")
                print("Your positions are directly on your wallet address.")
                print("=" * 80)
        except Exception as e:
            print(f"  Error: {e}")
        
        print()
        
        # Test proxy address if we have one
        if settings.proxy_address and settings.proxy_address.strip():
            proxy = settings.proxy_address
            print(f"Testing configured proxy: {proxy}")
            try:
                response = httpx.get(
                    f"https://data-api.polymarket.com/positions?user={proxy}&sizeThreshold=0",
                    timeout=10.0
                )
                positions_proxy = response.json()
                print(f"  Result: {len(positions_proxy)} positions found")
                if len(positions_proxy) > 0:
                    print(f"  ✅ Found {len(positions_proxy)} positions on proxy address!")
                else:
                    print(f"  ⚠️  No positions on this proxy address")
            except Exception as e:
                print(f"  Error: {e}")
        
        print()
        print("=" * 80)
        
    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR:")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)


if __name__ == "__main__":
    main()

