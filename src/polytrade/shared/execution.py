from __future__ import annotations

import random
import time
from typing import Any

from loguru import logger

from .config import settings
from .firestore import add_doc
from .polymarket_client import PolymarketClient


def place_trade(suggestion_id: str, token_id: str, side: str, price: float, size: float, user_chat_id: int | None, neg_risk: bool = False) -> dict[str, Any]:
    """Place a trade on Polymarket.
    
    Args:
        suggestion_id: Firestore suggestion document ID
        token_id: Polymarket token ID
        side: Trade side ("BUY_YES", "BUY_NO", etc.)
        price: Limit price (0.0-1.0)
        size: Number of contracts
        user_chat_id: Telegram user chat ID
        neg_risk: True for NegRisk markets (multi-outcome markets)
                 See: https://docs.polymarket.com/quickstart/orders/first-order
    """
    # Add random delay to avoid Cloudflare rate limiting
    delay = random.uniform(1.5, 3.0)  # 1.5-3 second delay
    logger.info(f"⏳ Adding {delay:.1f}s delay before trade to avoid rate limiting...")
    time.sleep(delay)
    
    client = PolymarketClient()
    order = client.place_order(token_id=token_id, side=side, price=price, size=size, neg_risk=neg_risk)
    trade = {
        "suggestionId": suggestion_id,
        "tokenId": token_id,
        "marketId": "",  # Will be populated from suggestion
        "title": "",  # Will be populated from suggestion  
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

