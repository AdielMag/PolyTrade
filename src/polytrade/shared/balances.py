from __future__ import annotations

import time
from typing import TypedDict

from .firestore import get_doc, set_doc
from .polymarket_client import PolymarketClient


class Position(TypedDict):
    title: str
    outcome: str
    size: float
    avgPrice: float
    curPrice: float
    currentValue: float
    pnl: float


class Order(TypedDict):
    market: str
    asset_id: str
    side: str
    size: float
    price: float
    value: float
    order_id: str


class Balance(TypedDict):
    available_usd: float
    locked_usd: float
    positions_usd: float
    total_usd: float
    updated_at: int
    positions: list[Position]
    orders: list[Order]


_CACHE_DOC = ("balances_cache", "global")
_TTL_SECONDS = 30


def get_current(force: bool = False) -> Balance:
    now = int(time.time())
    if not force:
        cached = get_doc(*_CACHE_DOC)
        if cached and (now - int(cached.get("updated_at", 0))) <= _TTL_SECONDS:
            return Balance(
                available_usd=float(cached.get("available_usd", 0.0)),
                locked_usd=float(cached.get("locked_usd", 0.0)),
                positions_usd=float(cached.get("positions_usd", 0.0)),
                total_usd=float(cached.get("total_usd", 0.0)),
                updated_at=int(cached.get("updated_at", 0)),
                positions=cached.get("positions", []),
                orders=cached.get("orders", []),
            )

    try:
        client = PolymarketClient()
        raw = client.get_balance()
        balance = Balance(
            available_usd=float(raw.get("available_usd", 0.0)),
            locked_usd=float(raw.get("locked_usd", 0.0)),
            positions_usd=float(raw.get("positions_usd", 0.0)),
            total_usd=float(raw.get("total_usd", 0.0)),
            updated_at=now,
            positions=raw.get("positions", []),
            orders=raw.get("orders", []),
        )
        set_doc(_CACHE_DOC[0], _CACHE_DOC[1], balance)  # store cache
        return balance
    except Exception:
        # Fallback to cached value or zeros if client initialization fails
        cached = get_doc(*_CACHE_DOC)
        if cached:
            return Balance(
                available_usd=float(cached.get("available_usd", 0.0)),
                locked_usd=float(cached.get("locked_usd", 0.0)),
                positions_usd=float(cached.get("positions_usd", 0.0)),
                total_usd=float(cached.get("total_usd", 0.0)),
                updated_at=int(cached.get("updated_at", 0)),
                positions=cached.get("positions", []),
                orders=cached.get("orders", []),
            )
        # Return zeros if no cache available
        return Balance(
            available_usd=0.0,
            locked_usd=0.0,
            positions_usd=0.0,
            total_usd=0.0,
            updated_at=now,
            positions=[],
            orders=[],
        )

