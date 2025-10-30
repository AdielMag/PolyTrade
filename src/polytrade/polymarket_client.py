from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from .config import settings


class PolymarketClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.polymarket_api_base
        self.api_key = api_key or settings.polymarket_api_key
        self._client = httpx.Client(timeout=10)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_balance(self) -> dict[str, float]:
        # Placeholder endpoint; adapt to actual Polymarket balance endpoint
        # Falls back to 0 when not available
        try:
            # Example: resp = self._client.get(f"{self.base_url}/v1/balance", headers=self._headers())
            # return resp.json()
            return {"available_usd": 0.0, "locked_usd": 0.0}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"balance fetch failed: {exc}")
            return {"available_usd": 0.0, "locked_usd": 0.0}

    def list_markets(self) -> list[dict[str, Any]]:
        # Placeholder; implement actual markets endpoint
        try:
            # resp = self._client.get(f"{self.base_url}/v1/markets", headers=self._headers())
            # return resp.json()
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"markets fetch failed: {exc}")
            return []

    def get_quotes(self, market_id: str) -> dict[str, Any]:
        # Placeholder; implement actual quote endpoint
        return {"best_bid": 0.0, "best_ask": 0.0, "ts": int(time.time())}

    def place_order(self, market_id: str, side: str, amount_usd: float) -> dict[str, Any]:
        # Placeholder; implement actual order placement
        logger.info(f"place_order market={market_id} side={side} amount={amount_usd}")
        return {"ok": True, "order_id": "demo-order", "avg_price": 0.5}

    def close_position(self, market_id: str, side: str, amount_usd: float) -> dict[str, Any]:
        logger.info(f"close_position market={market_id} side={side} amount={amount_usd}")
        return {"ok": True}


