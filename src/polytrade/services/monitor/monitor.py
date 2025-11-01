from __future__ import annotations

import time
from typing import Any

from loguru import logger

from ...shared.config import settings
from ...shared.firestore import get_client, add_doc
from ...shared.polymarket_client import PolymarketClient


def run_monitor() -> dict[str, Any]:
    """Monitor open trades and close positions when SL/TP is hit."""
    client = PolymarketClient()
    db = get_client()
    
    # Get all open trades
    trades_query = db.collection("trades").where("status", "==", "OPEN").limit(50).get()
    
    processed = 0
    closed = 0
    errors = 0
    
    for doc in trades_query:
        processed += 1
        trade = doc.to_dict()
        trade_id = doc.id
        
        try:
            # Extract trade details
            token_id = trade.get("tokenId", "")
            side = trade.get("side", "")
            size = float(trade.get("size", 0))
            entry_price = float(trade.get("entryPx", 0))
            sl_pct = float(trade.get("slPct", 0.15))
            tp_pct = float(trade.get("tpPct", 0.25))
            user_chat_id = trade.get("userChatId")
            
            # Get current market price
            quotes = client.get_quotes(token_id)
            
            # Determine current price based on position side
            if side.upper().startswith("BUY"):
                current_price = quotes["best_bid"]  # Can sell at bid
                opposite_side = "SELL"
            else:
                current_price = quotes["best_ask"]  # Can buy at ask
                opposite_side = "BUY"
            
            if current_price <= 0 or entry_price <= 0:
                continue
            
            # Calculate P&L percentage
            pnl_pct = (current_price - entry_price) / entry_price
            pnl_usd = pnl_pct * (size * entry_price)
            
            # Check stop loss
            if pnl_pct <= -sl_pct:
                logger.info(f"Stop loss hit for trade {trade_id}: {pnl_pct:.2%}")
                close_reason = "STOP_LOSS"
                should_close = True
            # Check take profit
            elif pnl_pct >= tp_pct:
                logger.info(f"Take profit hit for trade {trade_id}: {pnl_pct:.2%}")
                close_reason = "TAKE_PROFIT"
                should_close = True
            else:
                should_close = False
            
            if should_close:
                # Place closing order
                close_order = client.place_order(
                    token_id=token_id,
                    side=opposite_side,
                    price=current_price,
                    size=size
                )
                
                if close_order.get("ok"):
                    # Update trade in Firestore
                    doc.reference.update({
                        "status": "CLOSED",
                        "closedAt": int(time.time()),
                        "exitPx": current_price,
                        "pnl": pnl_usd,
                        "pnlPct": pnl_pct,
                        "closeReason": close_reason
                    })
                    
                    # Log event
                    add_doc("events", {
                        "tradeId": trade_id,
                        "type": "CLOSED",
                        "reason": close_reason,
                        "pnl": pnl_usd,
                        "pnlPct": pnl_pct,
                        "message": f"Closed by {close_reason}",
                        "createdAt": int(time.time())
                    })
                    
                    # Send notification via Bot B
                    if user_chat_id:
                        await_send_notification(
                            user_chat_id,
                            trade_id,
                            close_reason,
                            pnl_usd,
                            pnl_pct,
                            trade.get("title", "Trade")
                        )
                    
                    closed += 1
                    logger.info(f"Successfully closed trade {trade_id}")
                else:
                    logger.error(f"Failed to close trade {trade_id}: {close_order.get('error')}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"Error monitoring trade {trade_id}: {e}")
            errors += 1
            continue
    
    return {
        "processed": processed,
        "closed": closed,
        "errors": errors,
        "ts": int(time.time())
    }


def await_send_notification(chat_id: int, trade_id: str, reason: str, pnl_usd: float, pnl_pct: float, title: str) -> None:
    """Send trade close notification via Bot B (synchronous wrapper)."""
    try:
        import asyncio
        from ..bot_b.app import send_notification
        
        pnl_emoji = "✅" if pnl_usd >= 0 else "❌"
        message = (
            f"{pnl_emoji} Trade Closed: {reason}\n\n"
            f"Market: {title}\n"
            f"P&L: ${pnl_usd:.2f} ({pnl_pct:+.2%})\n"
            f"Trade ID: {trade_id}"
        )
        
        # Run async notification in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_notification(chat_id, message))
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

