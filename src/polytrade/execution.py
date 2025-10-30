from __future__ import annotations

import time
from typing import Any

from .config import settings
from .firestore import add_doc
from .polymarket_client import PolymarketClient


def place_trade(suggestion_id: str, market_id: str, side: str, amount_usd: float, user_chat_id: int | None) -> dict[str, Any]:
    client = PolymarketClient()
    order = client.place_order(market_id=market_id, side=side, amount_usd=amount_usd)
    trade = {
        "suggestionId": suggestion_id,
        "marketId": market_id,
        "side": side,
        "amountUsd": amount_usd,
        "entryPx": order.get("avg_price", 0.0),
        "status": "OPEN" if order.get("ok") else "FAILED",
        "pnl": 0.0,
        "slPct": settings.default_sl_pct,
        "tpPct": settings.default_tp_pct,
        "userChatId": user_chat_id,
        "createdAt": int(time.time()),
        "closedAt": None,
    }
    trade_id = add_doc("trades", trade)
    add_doc("events", {"tradeId": trade_id, "type": "CREATED", "message": "Trade opened", "createdAt": int(time.time())})
    return {"trade_id": trade_id, **trade}


