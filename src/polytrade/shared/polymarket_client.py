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
        """Get current USDC balance from Polymarket CLOB."""
        try:
            # Get balance allowance from CLOB client for COLLATERAL (USDC)
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            balance_response = self.client.get_balance_allowance(params)
            
            # The response should be a dict with balance and allowance fields
            if isinstance(balance_response, dict):
                # Extract the balance field - this is the USDC balance
                available = float(balance_response.get("balance", 0.0))
            elif isinstance(balance_response, (int, float)):
                # Fallback if it returns a number
                available = float(balance_response)
            else:
                logger.warning(f"Unexpected balance response type: {type(balance_response)}")
                available = 0.0
            
            logger.info(f"Retrieved balance: ${available:.2f}")
            
            return {
                "available_usd": available,
                "locked_usd": 0.0  # TODO: Add logic for in-orders balance if API provides it
            }
        except Exception as e:
            logger.error(f"Failed to fetch balance from Polymarket: {e}")
            # Return zeros as fallback to prevent crashes
            return {"available_usd": 0.0, "locked_usd": 0.0}

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
            
            response = httpx.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            markets = response.json()
            
            logger.info(f"Fetched {len(markets)} sports markets from Gamma API")
            return markets if isinstance(markets, list) else []
            
        except Exception as e:
            logger.error(f"Failed to fetch markets from Gamma API: {e}")
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

