from __future__ import annotations

import time
from typing import Any

from .config import settings
from .firestore import get_client, add_doc
from .polymarket_client import PolymarketClient


def run_monitor() -> dict[str, Any]:
    client = PolymarketClient()
    db = get_client()
    q = db.collection("trades").where("status", "==", "OPEN").limit(50).get()
    closed = 0
    for doc in q:
        trade = doc.to_dict()
        market_id = trade.get("marketId")
        side = trade.get("side")
        amount = float(trade.get("amountUsd", 0.0))
        # Placeholder logic: immediately close nothing; add SL/TP rules here
        # For demo, do nothing
        _ = (market_id, side, amount)
        # Example close:
        # res = client.close_position(market_id, side, amount)
        # if res.get("ok"):
        #     doc.reference.update({"status": "CLOSED", "closedAt": int(time.time())})
        #     add_doc("events", {"tradeId": doc.id, "type": "CLOSED", "message": "Closed by monitor", "createdAt": int(time.time())})
        #     closed += 1
    return {"processed": len(q), "closed": closed, "ts": int(time.time())}


