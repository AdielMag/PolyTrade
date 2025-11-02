#!/usr/bin/env python3
"""Test script to debug get_balance locally."""

import sys
import os
from unittest.mock import Mock, patch
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_with_mock_data():
    """Test with mocked API responses to see the logic flow."""
    print("=" * 80)
    print("TESTING get_balance() WITH MOCK DATA")
    print("=" * 80)
    print()
    
    from polytrade.shared.polymarket_client import PolymarketClient
    from polytrade.shared import config
    
    # Mock the settings
    config.settings.wallet_private_key = "0x" + "1" * 64  # Fake private key
    config.settings.proxy_address = "0x1234567890123456789012345678901234567890"  # Mock proxy
    
    # Create mock ClobClient
    with patch('polytrade.shared.polymarket_client.ClobClient') as MockClobClient:
        mock_clob_instance = Mock()
        MockClobClient.return_value = mock_clob_instance
        
        # Mock the methods
        mock_clob_instance.create_or_derive_api_creds.return_value = {"key": "test"}
        mock_clob_instance.set_api_creds.return_value = None
        mock_clob_instance.get_address.return_value = "0x9876543210987654321098765432109876543210"
        
        # Mock balance response (15.59 USD in microUSDC)
        mock_clob_instance.get_balance_allowance.return_value = {
            "balance": 15587491  # $15.59 in microUSDC
        }
        
        # Mock orders response (no open orders)
        mock_clob_instance.get_orders.return_value = []
        
        # Mock positions API response
        mock_positions_response = [
            {
                "proxyWallet": "0x1234567890123456789012345678901234567890",
                "asset": "0xtoken1",
                "conditionId": "0xcondition1",
                "size": 100,
                "avgPrice": 0.70,
                "initialValue": 70,
                "currentValue": 75.50,
                "cashPnl": 5.50,
                "percentPnl": 7.86,
                "curPrice": 0.755,
                "title": "Will Team X win the championship?",
                "outcome": "YES",
                "redeemable": False,
                "mergeable": False
            },
            {
                "proxyWallet": "0x1234567890123456789012345678901234567890",
                "asset": "0xtoken2",
                "conditionId": "0xcondition2",
                "size": 50,
                "avgPrice": 0.60,
                "initialValue": 30,
                "currentValue": 32.50,
                "cashPnl": 2.50,
                "percentPnl": 8.33,
                "curPrice": 0.65,
                "title": "Will candidate Y win the election?",
                "outcome": "NO",
                "redeemable": False,
                "mergeable": False
            }
        ]
        
        # Mock httpx.get for positions
        with patch('httpx.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = json.dumps(mock_positions_response)
            mock_response.json.return_value = mock_positions_response
            mock_response.headers = {"content-type": "application/json"}
            mock_get.return_value = mock_response
            
            # Now test
            try:
                client = PolymarketClient()
                balance = client.get_balance()
                
                print()
                print("=" * 80)
                print("✅ SUCCESS! BALANCE RETRIEVED:")
                print("=" * 80)
                print(f"💵 Available USD:  ${balance.get('available_usd', 0):.2f}")
                print(f"📝 Locked USD:     ${balance.get('locked_usd', 0):.2f}")
                print(f"💎 Positions USD:  ${balance.get('positions_usd', 0):.2f}")
                print(f"📊 Total USD:      ${balance.get('total_usd', 0):.2f}")
                print("=" * 80)
                print()
                
                # Verify the values
                expected_available = 15.59
                expected_locked = 0.0
                expected_positions = 75.50 + 32.50  # 108.00
                expected_total = expected_available + expected_locked + expected_positions
                
                print("VERIFICATION:")
                print(f"  Available matches: {abs(balance.get('available_usd', 0) - expected_available) < 0.01}")
                print(f"  Positions matches: {abs(balance.get('positions_usd', 0) - expected_positions) < 0.01}")
                print(f"  Total matches: {abs(balance.get('total_usd', 0) - expected_total) < 0.01}")
                print()
                
                if abs(balance.get('positions_usd', 0) - expected_positions) < 0.01:
                    print("✅ POSITIONS LOGIC IS WORKING CORRECTLY!")
                else:
                    print(f"❌ POSITIONS MISMATCH: Expected ${expected_positions:.2f}, Got ${balance.get('positions_usd', 0):.2f}")
                
            except Exception as e:
                print()
                print("=" * 80)
                print("❌ ERROR:")
                print("=" * 80)
                print(f"{type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                print("=" * 80)


def test_with_real_credentials():
    """Test with real credentials if .env exists."""
    import os
    
    print()
    print("=" * 80)
    print("TESTING WITH REAL CREDENTIALS")
    print("=" * 80)
    print()
    
    if not os.path.exists('.env'):
        print("❌ No .env file found. Skipping real credentials test.")
        print("   To test with real data, create a .env file with:")
        print("   - WALLET_PRIVATE_KEY=0x...")
        print("   - POLYMARKET_PROXY_ADDRESS=0x...")
        return
    
    # Reload the settings from .env to override mock values
    from polytrade.shared import config
    # Point to the root .env file
    root_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    config.settings = config.Settings(_env_file=root_env_path)
    
    from polytrade.shared.polymarket_client import PolymarketClient
    from polytrade.shared.logging import configure_logging
    
    configure_logging()
    
    try:
        print("Creating PolymarketClient...")
        client = PolymarketClient()
        print("✅ Client created successfully")
        print()
        
        print("Calling get_balance()...")
        balance = client.get_balance()
        
        print()
        print("=" * 80)
        print("✅ REAL DATA RETRIEVED:")
        print("=" * 80)
        print(f"💵 Available USD:  ${balance.get('available_usd', 0):.2f}")
        print(f"📝 Locked USD:     ${balance.get('locked_usd', 0):.2f}")
        print(f"💎 Positions USD:  ${balance.get('positions_usd', 0):.2f}")
        print(f"📊 Total USD:      ${balance.get('total_usd', 0):.2f}")
        print("=" * 80)
        
    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR WITH REAL CREDENTIALS:")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)


if __name__ == "__main__":
    # Test with mock data first (always works)
    test_with_mock_data()
    
    # Then try with real credentials if available
    test_with_real_credentials()
    
    print()
    print("=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)

