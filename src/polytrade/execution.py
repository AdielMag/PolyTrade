from __future__ import annotations

import time
from typing import Any

from .config import settings
from .firestore import add_doc
from .polymarket_client import PolymarketClient


def place_trade(suggestion_id: str, token_id: str, side: str, price: float, size: float, user_chat_id: int | None) -> dict[str, Any]:
    client = PolymarketClient()
    order = client.place_order(token_id=token_id, side=side, price=price, size=size)
    trade = {
        "suggestionId": suggestion_id,
        "tokenId": token_id,
        "side": side,
        "size": size,
        "entryPx": price,
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


