from __future__ import annotations

import time
from typing import Any

from loguru import logger

from ...shared.config import settings
from ...shared.firestore import get_client, add_doc
from ...shared.polymarket_client import PolymarketClient


def run_monitor() -> dict[str, Any]:
    """Monitor open trades and close positions when SL/TP is hit."""
    logger.info("=" * 80)
    logger.info("Starting monitor run")
    
    client = PolymarketClient()
    db = get_client()
    
    # Get all open trades
    logger.info("Querying open trades from Firestore...")
    trades_query = db.collection("trades").where("status", "==", "OPEN").limit(50).get()
    trades_list = list(trades_query)
    
    logger.info(f"Found {len(trades_list)} open trades to monitor")
    
    processed = 0
    closed = 0
    errors = 0
    
    for idx, doc in enumerate(trades_list, 1):
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
            market_title = trade.get("title", "Unknown Market")
            
            logger.info(f"[{idx}/{len(trades_list)}] Checking trade: {trade_id}")
            logger.info(f"  Market: {market_title[:60]}")
            logger.info(f"  Side: {side} | Size: {size} | Entry: ${entry_price:.4f}")
            logger.info(f"  SL: {sl_pct:.1%} | TP: {tp_pct:.1%}")
            
            # Get current market price
            logger.debug(f"  Fetching quotes for token {token_id}...")
            quotes = client.get_quotes(token_id)
            logger.debug(f"  Got quotes: bid={quotes.get('best_bid')}, ask={quotes.get('best_ask')}")
            
            # Determine current price based on position side
            if side.upper().startswith("BUY"):
                current_price = quotes["best_bid"]  # Can sell at bid
                opposite_side = "SELL"
                logger.debug(f"  Position: LONG (BUY), exit at bid=${current_price:.4f}")
            else:
                current_price = quotes["best_ask"]  # Can buy at ask
                opposite_side = "BUY"
                logger.debug(f"  Position: SHORT (SELL), exit at ask=${current_price:.4f}")
            
            if current_price <= 0 or entry_price <= 0:
                logger.warning(f"  ⚠️ Invalid prices: current=${current_price}, entry=${entry_price}, skipping")
                continue
            
            # Calculate P&L percentage
            pnl_pct = (current_price - entry_price) / entry_price
            pnl_usd = pnl_pct * (size * entry_price)
            
            logger.info(f"  💰 P&L: ${pnl_usd:+.2f} ({pnl_pct:+.2%})")
            logger.info(f"  📊 Current: ${current_price:.4f} vs Entry: ${entry_price:.4f}")
            
            # Check stop loss
            if pnl_pct <= -sl_pct:
                logger.warning(f"  🛑 STOP LOSS TRIGGERED: {pnl_pct:.2%} <= -{sl_pct:.1%}")
                close_reason = "STOP_LOSS"
                should_close = True
            # Check take profit
            elif pnl_pct >= tp_pct:
                logger.info(f"  🎯 TAKE PROFIT TRIGGERED: {pnl_pct:.2%} >= {tp_pct:.1%}")
                close_reason = "TAKE_PROFIT"
                should_close = True
            else:
                logger.debug(f"  ✅ Position within limits (SL: -{sl_pct:.1%}, TP: +{tp_pct:.1%})")
                should_close = False
            
            if should_close:
                logger.info(f"  📤 Placing closing order: {opposite_side} {size} @ ${current_price:.4f}")
                # Place closing order
                close_order = client.place_order(
                    token_id=token_id,
                    side=opposite_side,
                    price=current_price,
                    size=size
                )
                
                if close_order.get("ok"):
                    logger.info(f"  ✅ Order executed successfully")
                    # Update trade in Firestore
                    logger.debug(f"  Updating Firestore with closed status...")
                    doc.reference.update({
                        "status": "CLOSED",
                        "closedAt": int(time.time()),
                        "exitPx": current_price,
                        "pnl": pnl_usd,
                        "pnlPct": pnl_pct,
                        "closeReason": close_reason
                    })
                    
                    # Log event
                    logger.debug(f"  Creating close event in Firestore...")
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
                        logger.debug(f"  Sending notification to user chat {user_chat_id}...")
                        await_send_notification(
                            user_chat_id,
                            trade_id,
                            close_reason,
                            pnl_usd,
                            pnl_pct,
                            market_title
                        )
                    else:
                        logger.debug(f"  No user chat ID, skipping notification")
                    
                    closed += 1
                    logger.info(f"  ✅ Successfully closed trade {trade_id}")
                else:
                    logger.error(f"  ❌ Failed to place close order: {close_order.get('error')}")
                    logger.error(f"     Order details: {opposite_side} {size} @ ${current_price:.4f}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"  ❌ Error monitoring trade {trade_id}: {e}")
            logger.error(f"     Market: {market_title[:60]}")
            import traceback
            logger.error(f"     Traceback: {traceback.format_exc()}")
            errors += 1
            continue
    
    # Final summary
    logger.info("=" * 80)
    logger.info("MONITOR SUMMARY:")
    logger.info(f"  Total trades processed: {processed}")
    logger.info(f"  Trades closed: {closed}")
    logger.info(f"  Errors encountered: {errors}")
    logger.info(f"  Trades still open: {processed - closed - errors}")
    logger.info("=" * 80)
    
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
        
        # Choose emojis based on reason and profit
        if reason == "TAKE_PROFIT":
            status_emoji = "🎉"
            reason_text = "Take Profit Hit!"
        elif reason == "STOP_LOSS":
            status_emoji = "🛑"
            reason_text = "Stop Loss Hit"
        else:
            status_emoji = "🔔"
            reason_text = "Trade Closed"
            
        pnl_emoji = "💰" if pnl_usd >= 0 else "📉"
        pnl_color = "+" if pnl_usd >= 0 else ""
        
        message = (
            f"{status_emoji} <b>{reason_text}</b>\n\n"
            f"🎯 <b>{title}</b>\n\n"
            f"{pnl_emoji} <b>P&L: {pnl_color}${pnl_usd:.2f}</b> ({pnl_pct:+.2%})\n\n"
            f"🆔 Trade ID: <code>{trade_id}</code>"
        )
        
        # Run async notification in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_notification(chat_id, message))
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

