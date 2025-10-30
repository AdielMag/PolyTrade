from __future__ import annotations

import time
from typing import Any

from .config import settings
from .firestore import add_doc
from .polymarket_client import PolymarketClient


def compute_edge_bps(fair: float, ask: float) -> float:
    if ask <= 0:
        return 0.0
    return (fair - ask) * 10000.0 / ask


def run_analysis(max_suggestions: int = 5) -> list[dict[str, Any]]:
    client = PolymarketClient()
    markets = client.list_markets()

    # Placeholder logic: choose nothing; in real impl, compute fair from order book/market data
    suggestions: list[dict[str, Any]] = []
    now = int(time.time())

    for m in markets[:max_suggestions]:
        token_id = m.get("tokenId", "")
        title = m.get("title", "")
        # Stub: BUY with small edge, placeholder price
        suggestion = {
            "tokenId": token_id,
            "title": title,
            "side": "BUY_YES",
            "edgeBps": settings.edge_bps,
            "sizeHint": 1.0,
            "price": 0.01,
            "expiresAt": now + 3600,
            "status": "OPEN",
        }
        add_doc("suggestions", suggestion)
        suggestions.append(suggestion)

    return suggestions


