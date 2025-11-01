from __future__ import annotations

import time
from typing import Any

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
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
            # Get balance from CLOB client - returns balance in USDC
            balance_response = self.client.get_balance()
            
            # The response should be a number (float or int) representing USDC balance
            if isinstance(balance_response, (int, float)):
                available = float(balance_response)
            elif isinstance(balance_response, dict):
                # If it returns a dict, extract the balance field
                available = float(balance_response.get("balance", 0.0))
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
        # Use Gamma endpoints via public API in a separate client if needed.
        return []

    def get_quotes(self, market_id: str) -> dict[str, Any]:
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


