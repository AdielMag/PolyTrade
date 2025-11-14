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

    client = None
    try:
        from loguru import logger
        # Note: ClobClient (used by PolymarketClient) uses requests library, not httpx
        # It cannot share our httpx connection pool, so we need available sockets
        # The calling code should close all httpx clients before calling this
        logger.info("💳 Initializing PolymarketClient for balance fetch...")
        logger.info("   (ClobClient uses requests library - needs available sockets)")
        client = PolymarketClient()
        logger.info("✅ PolymarketClient initialized, fetching balance...")
        raw = client.get_balance()
        logger.info(f"✅ Balance fetched successfully: {raw}")
        
        balance = Balance(
            available_usd=float(raw.get("available_usd", 0.0)),
            locked_usd=float(raw.get("locked_usd", 0.0)),
            positions_usd=float(raw.get("positions_usd", 0.0)),
            total_usd=float(raw.get("total_usd", 0.0)),
            updated_at=now,
            positions=raw.get("positions", []),
            orders=raw.get("orders", []),
        )
        
        logger.info(f"💰 Balance summary:")
        logger.info(f"   Available: ${balance['available_usd']:.2f}")
        logger.info(f"   Locked: ${balance['locked_usd']:.2f}")
        logger.info(f"   Positions: ${balance['positions_usd']:.2f}")
        logger.info(f"   Total: ${balance['total_usd']:.2f}")
        
        set_doc(_CACHE_DOC[0], _CACHE_DOC[1], balance)  # store cache
        return balance
    except Exception as e:
        # Log the error for debugging
        from loguru import logger
        import traceback
        logger.error("=" * 80)
        logger.error("❌ FAILED TO FETCH BALANCE FROM POLYMARKET")
        logger.error("=" * 80)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Full traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)
        
        # Fallback to cached value or zeros if client initialization fails
        cached = get_doc(*_CACHE_DOC)
        if cached:
            logger.info(f"   Using cached balance from Firestore (updated at: {cached.get('updated_at', 0)})")
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
        logger.warning("   No cached balance available - returning zeros")
        logger.warning("   💡 Make sure WALLET_PRIVATE_KEY and POLYMARKET_PROXY_ADDRESS are configured")
        return Balance(
            available_usd=0.0,
            locked_usd=0.0,
            positions_usd=0.0,
            total_usd=0.0,
            updated_at=now,
            positions=[],
            orders=[],
        )
    finally:
        # Always close the client to free connections
        if client:
            try:
                client.close()
            except Exception:
                pass

