from __future__ import annotations

import time
from typing import Any

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from .config import settings


class PolymarketClient:
    def __init__(self) -> None:
        if not settings.wallet_private_key:
            raise RuntimeError("WALLET_PRIVATE_KEY is required")
        self.client = ClobClient(
            settings.clob_host,
            key=settings.wallet_private_key,
            chain_id=settings.chain_id,
            signature_type=settings.signature_type,
            funder=settings.proxy_address,
        )
        # derive and set API creds
        self.client.set_api_creds(self.client.create_or_derive_api_creds())

    def get_balance(self) -> dict[str, float]:
        """Get current USDC balance and portfolio value from Polymarket CLOB."""
        logger.info("=" * 80)
        logger.info("Fetching balance and portfolio value from Polymarket...")
        try:
            # Get balance allowance from CLOB client for COLLATERAL (USDC)
            logger.debug("Creating BalanceAllowanceParams with AssetType.COLLATERAL")
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            
            logger.debug("Calling get_balance_allowance()...")
            balance_response = self.client.get_balance_allowance(params)
            logger.debug(f"get_balance_allowance() response type: {type(balance_response)}")
            logger.debug(f"get_balance_allowance() response: {balance_response}")
            
            # The response should be a dict with balance and allowance fields
            if isinstance(balance_response, dict):
                # Extract the balance field - this is in the smallest unit (6 decimals for USDC)
                raw_balance = float(balance_response.get("balance", 0.0))
                logger.debug(f"Extracted balance from dict: {raw_balance}")
            elif isinstance(balance_response, (int, float)):
                # Fallback if it returns a number
                raw_balance = float(balance_response)
                logger.debug(f"Balance is a number: {raw_balance}")
            else:
                logger.warning(f"Unexpected balance response type: {type(balance_response)}")
                raw_balance = 0.0
            
            # Convert from smallest unit to USD (USDC has 6 decimal places)
            available_usd = raw_balance / 1_000_000
            logger.info(f"Converted raw balance {raw_balance} microUSDC -> ${available_usd:.2f} USD")
            
            # Get open orders to calculate locked funds
            locked_usd = 0.0
            positions_usd = 0.0
            
            try:
                logger.info("=" * 80)
                logger.info("Fetching open orders and positions...")
                
                # 1. Get open orders (pending unfilled orders)
                logger.debug("Calling get_orders() to fetch pending orders...")
                orders_response = self.client.get_orders()
                
                logger.debug(f"get_orders() response type: {type(orders_response)}")
                logger.debug(f"get_orders() response: {orders_response}")
                
                # Handle different response formats for orders
                orders = []
                if isinstance(orders_response, dict):
                    if "data" in orders_response:
                        orders = orders_response.get("data", [])
                    else:
                        orders = [orders_response] if orders_response else []
                elif isinstance(orders_response, list):
                    orders = orders_response
                
                if orders:
                    logger.info(f"📝 Processing {len(orders)} open orders")
                    for i, order in enumerate(orders):
                        try:
                            size = float(order.get("size", 0.0))
                            price = float(order.get("price", 0.0))
                            order_value = size * price
                            locked_usd += order_value
                            
                            logger.debug(
                                f"  Order {i+1}: size={size}, price={price:.4f}, "
                                f"value=${order_value:.2f}, side={order.get('side', 'N/A')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(f"  Order {i+1}: Could not parse - {e}")
                            continue
                    
                    logger.info(f"  🔒 Total locked in open orders: ${locked_usd:.2f}")
                else:
                    logger.info("  ✅ No open orders (all filled or canceled)")
                
                # 2. Get positions (actual holdings from filled orders)
                logger.info("")
                logger.info("Fetching positions from Data API...")
                
                import httpx
                
                # Get wallet address from the client
                wallet_address = self.client.get_address()
                logger.debug(f"Using wallet address: {wallet_address}")
                
                positions_url = f"https://data-api.polymarket.com/positions?user={wallet_address}"
                logger.debug(f"Positions API URL: {positions_url}")
                
                pos_response = httpx.get(positions_url, timeout=30.0)
                pos_response.raise_for_status()
                positions = pos_response.json()
                
                logger.info(f"📊 Received {len(positions)} positions from Data API")
                logger.debug(f"Positions response type: {type(positions)}")
                
                if positions and isinstance(positions, list):
                    for i, pos in enumerate(positions):
                        try:
                            # Position value is current market value
                            size = float(pos.get("size", 0.0))
                            current_price = float(pos.get("price", 0.0))  # Current market price
                            position_value = size * current_price
                            positions_usd += position_value
                            
                            logger.debug(
                                f"  Position {i+1}: asset={pos.get('asset', 'N/A')[:20]}, "
                                f"size={size}, price=${current_price:.4f}, "
                                f"value=${position_value:.2f}"
                            )
                        except (ValueError, TypeError, KeyError) as e:
                            logger.warning(f"  Position {i+1}: Could not parse - {e}")
                            continue
                    
                    logger.info(f"  💎 Total value of positions: ${positions_usd:.2f}")
                else:
                    logger.info("  ✅ No open positions")
                    
                logger.info("=" * 80)
                    
            except httpx.HTTPError as e:
                logger.error(f"❌ HTTP error fetching positions: {e}")
                positions_usd = 0.0
            except Exception as e:
                logger.error(f"❌ Failed to fetch orders/positions: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                locked_usd = 0.0
                positions_usd = 0.0
            
            # Total portfolio value = available + locked + positions
            total_usd = available_usd + locked_usd + positions_usd
            
            logger.info("=" * 80)
            logger.info("💰 PORTFOLIO SUMMARY:")
            logger.info(f"  Available USDC:     ${available_usd:.2f}")
            logger.info(f"  Locked in Orders:   ${locked_usd:.2f}")
            logger.info(f"  Position Value:     ${positions_usd:.2f}")
            logger.info(f"  ─────────────────────────────")
            logger.info(f"  📊 TOTAL PORTFOLIO: ${total_usd:.2f}")
            logger.info("=" * 80)
            
            return {
                "available_usd": available_usd,
                "locked_usd": locked_usd,
                "positions_usd": positions_usd,
                "total_usd": total_usd
            }
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"❌ FAILED to fetch balance from Polymarket: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error("=" * 80)
            # Return zeros as fallback to prevent crashes
            return {"available_usd": 0.0, "locked_usd": 0.0, "positions_usd": 0.0, "total_usd": 0.0}

    def list_markets(self) -> list[dict[str, Any]]:
        """Fetch active sports markets from Polymarket Gamma API."""
        try:
            import httpx
            
            # Gamma API endpoint for markets
            url = "https://gamma-api.polymarket.com/markets"
            params = {
                "active": "true",
                "closed": "false", 
                "tag": "sports",  # Filter for sports markets only
                "limit": 100
            }
            
            logger.info(f"Fetching markets from Gamma API: {url}")
            logger.debug(f"Request params: {params}")
            
            response = httpx.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            markets = response.json()
            
            logger.info(f"✅ Fetched {len(markets)} sports markets from Gamma API ")
            
            # Log structure of first market to understand the schema
            if markets and isinstance(markets, list) and len(markets) > 0:
                first_market = markets[0]
                logger.debug("=" * 80)
                logger.debug("FIRST MARKET STRUCTURE:")
                logger.debug(f"  Keys: {list(first_market.keys())}")
                logger.debug(f"  Question: {first_market.get('question', 'N/A')[:80]}")
                logger.debug(f"  Has 'tokens' field: {'tokens' in first_market}")
                
                if 'tokens' in first_market:
                    tokens = first_market.get('tokens', [])
                    logger.debug(f"  Tokens count: {len(tokens)}")
                    if tokens:
                        logger.debug(f"  First token keys: {list(tokens[0].keys()) if tokens else 'N/A'}")
                else:
                    # Check for alternative field names
                    logger.debug(f"  ⚠️ No 'tokens' field found. Checking alternatives...")
                    potential_fields = ['outcomes', 'markets', 'options', 'sides', 'clobTokenIds']
                    for field in potential_fields:
                        if field in first_market:
                            logger.debug(f"  Found alternative field '{field}': {type(first_market[field])}")
                            if isinstance(first_market[field], list) and first_market[field]:
                                logger.debug(f"    First item: {first_market[field][0]}")
                
                # Log full first market for debugging (truncated)
                import json
                market_json = json.dumps(first_market, indent=2)
                if len(market_json) > 1000:
                    market_json = market_json[:1000] + "\n... (truncated)"
                logger.debug(f"  Full first market:\n{market_json}")
                logger.debug("=" * 80)
                
                # Count how many markets have tokens
                with_tokens = sum(1 for m in markets if m.get('tokens'))
                without_tokens = len(markets) - with_tokens
                logger.info(f"  Markets with 'tokens' field: {with_tokens}")
                logger.info(f"  Markets WITHOUT 'tokens' field: {without_tokens}")
            
            return markets if isinstance(markets, list) else []
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch markets from Gamma API: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []

    def get_quotes(self, token_id: str) -> dict[str, Any]:
        """Get current best bid/ask prices from CLOB order book."""
        try:
            # Use CLOB client to get order book
            book = self.client.get_order_book(token_id)
            
            # Extract best bid and ask
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 0.0
            
            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "ts": int(time.time())
            }
            
        except Exception as e:
            logger.error(f"Failed to get quotes for token {token_id}: {e}")
            return {"best_bid": 0.0, "best_ask": 0.0, "ts": int(time.time())}

    def place_order(self, token_id: str, side: str, price: float, size: float) -> dict[str, Any]:
        side_const = BUY if side.upper().startswith("BUY") else SELL
        order_args = OrderArgs(price=price, size=size, side=side_const, token_id=token_id)
        signed = self.client.create_order(order_args)
        resp = self.client.post_order(signed, OrderType.GTC)
        logger.info(f"order response: {resp}")
        return {"ok": True, "resp": resp}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        try:
            resp = self.client.cancel_order(order_id)
            return {"ok": True, "resp": resp}
        except Exception as exc:  # noqa: BLE001
            logger.error(f"cancel failed: {exc}")
            return {"ok": False, "error": str(exc)}

