from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from loguru import logger

from ...shared.config import settings
from ...shared.firestore import get_client
from ...shared.balances import get_current
from .formatting import suggestion_message
from .keyboards import amount_presets_kb, confirm_kb
from ...shared.execution import place_trade
from ...shared.logging import configure_logging
from ..analyzer.analysis import run_analysis

configure_logging()

app = FastAPI()
dp = Dispatcher()


def get_bot() -> Bot:
    if not settings.bot_a_token:
        # Return a bot with an obviously invalid token is risky; better to raise when used
        raise RuntimeError("TELEGRAM_BOT_A_TOKEN is not set")
    return Bot(token=settings.bot_a_token)


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    try:
        # Force fresh balance fetch from Polymarket
        bal = get_current(force=True)
        
        # Build the main balance message
        balance_msg = (
            f"💰 <b>Portfolio Balance</b>\n\n"
            f"<b>Total: ${bal['total_usd']:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Available: ${bal['available_usd']:.2f}\n"
            f"📝 In Orders: ${bal['locked_usd']:.2f}\n"
            f"💎 Positions: ${bal['positions_usd']:.2f}\n"
        )
        
        # Add detailed open orders if any (limit to 5 per message)
        orders = bal.get("orders", [])
        max_orders_to_show = 5
        if orders:
            orders_to_show = orders[:max_orders_to_show]
            balance_msg += f"\n\n<b>📝 Open Orders ({len(orders)}):</b>\n"
            for i, order in enumerate(orders_to_show, 1):
                side_emoji = "📈" if order['side'].upper() == "BUY" else "📉"
                market_name = order.get('market', 'N/A')
                if len(market_name) > 35:
                    market_name = market_name[:32] + "..."
                balance_msg += (
                    f"\n{side_emoji} <b>#{i}</b> {order['side'][:3]} "
                    f"{order['size']:.1f}@${order['price']:.3f} "
                    f"(${order['value']:.2f})\n"
                    f"  {market_name}\n"
                )
            if len(orders) > max_orders_to_show:
                balance_msg += f"<i>...and {len(orders) - max_orders_to_show} more</i>\n"
        
        # Add detailed positions if any (limit to 5 per message)
        positions = bal.get("positions", [])
        max_positions_to_show = 5
        if positions:
            positions_to_show = positions[:max_positions_to_show]
            balance_msg += f"\n\n<b>💎 Positions ({len(positions)}):</b>\n"
            for i, pos in enumerate(positions_to_show, 1):
                pnl_emoji = "📈" if pos['pnl'] >= 0 else "📉"
                pnl_sign = "+" if pos['pnl'] >= 0 else ""
                market_name = pos['title']
                if len(market_name) > 35:
                    market_name = market_name[:32] + "..."
                balance_msg += (
                    f"\n{pnl_emoji} <b>#{i}</b> {pos['outcome']}: "
                    f"${pos['currentValue']:.2f} "
                    f"({pnl_sign}${pos['pnl']:.2f})\n"
                    f"  {market_name}\n"
                    f"  {pos['size']:.1f}sh @ ${pos['avgPrice']:.3f}→${pos['curPrice']:.3f}\n"
                )
            if len(positions) > max_positions_to_show:
                balance_msg += f"<i>...and {len(positions) - max_positions_to_show} more</i>\n"
        
        if not orders and not positions:
            balance_msg += f"\n\n<i>No open orders or positions</i>\n"
        
        balance_msg += f"\n\n📊 /suggest for trade opportunities"
        
        # Ensure message is under Telegram's 4096 character limit
        if len(balance_msg) > 4000:
            # If still too long, truncate positions/orders more aggressively
            balance_msg = (
                f"💰 <b>Portfolio Balance</b>\n\n"
                f"<b>Total: ${bal['total_usd']:.2f}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Available: ${bal['available_usd']:.2f}\n"
                f"📝 In Orders: ${bal['locked_usd']:.2f} ({len(orders)} orders)\n"
                f"💎 Positions: ${bal['positions_usd']:.2f} ({len(positions)} positions)\n\n"
                f"<i>Too many items to display details.\n"
                f"Summary view only.</i>\n\n"
                f"📊 /suggest for trade opportunities"
            )
        
        await message.answer(balance_msg, parse_mode="HTML")
    except Exception as e:
        await message.answer(
            f"⚠️ <b>Error fetching balance</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Please try again or contact support.",
            parse_mode="HTML"
        )


@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message) -> None:
    try:
        # Notify user we're analyzing markets
        status_msg = await message.answer("🔄 <b>Analyzing markets...</b>\n\nThis may take a moment...", parse_mode="HTML")
        
        # Run analyzer on demand to get fresh suggestions
        suggestions = run_analysis(max_suggestions=5)
        
        # Delete the status message
        await status_msg.delete()
        
        if not suggestions:
            no_suggestions_msg = (
                f"📭 <b>No suggestions available right now</b>\n\n"
                f"No markets matching our criteria were found.\n"
                f"Try again later for new opportunities! 🎯\n\n"
                f"💡 Use /balance to check your portfolio"
            )
            await message.answer(no_suggestions_msg, parse_mode="HTML")
            return
        
        # Get the suggestion IDs from firestore to pass to keyboards
        # The suggestions returned by run_analysis have been saved to firestore
        # We need to query them back to get their document IDs
        logger.info(f"📤 Sending {len(suggestions)} suggestions to user...")
        db = get_client()
        sent_count = 0
        
        for i, s in enumerate(suggestions, 1):
            try:
                # Query for this suggestion by tokenId to get its document ID
                snap = db.collection("suggestions").where("tokenId", "==", s.get("tokenId", "")).where("status", "==", "OPEN").limit(1).get()
                if snap:
                    doc = snap[0]
                    text = suggestion_message(
                        s.get("title", ""), 
                        s.get("side", ""), 
                        s.get("yesProbability", 0.5), 
                        s.get("noProbability", 0.5),
                        s.get("endDate", None)
                    )
                    kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
                    await message.answer(text, reply_markup=kb, parse_mode="HTML")
                    sent_count += 1
                    logger.info(f"✅ Sent suggestion {i}/{len(suggestions)}")
            except Exception as send_err:
                logger.error(f"❌ Error sending suggestion {i}: {send_err}")
        
        logger.info(f"✅ Finished sending {sent_count}/{len(suggestions)} suggestions to user")
        return  # Explicitly return to end the function
    except Exception as e:
        # User-friendly error handling
        error_msg = str(e)
        if "index" in error_msg.lower():
            await message.answer(
                "⚠️ <b>Database Index Required</b>\n\n"
                "The database needs to be configured. Please:\n"
                "• Create the Firestore index using the link in error logs\n"
                "• Or contact your administrator\n\n"
                "⏱ This is a one-time setup (1-2 minutes)",
                parse_mode="HTML"
            )
        elif "404" in error_msg or "does not exist" in error_msg:
            await message.answer(
                "⚠️ <b>Database Not Found</b>\n\n"
                "Please ensure the Firestore database 'polytrade' is created.\n"
                "📧 Contact your administrator for setup.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⚠️ <b>Error Fetching Suggestions</b>\n\n"
                f"<code>{error_msg}</code>\n\n"
                f"Please try again later. 🔄",
                parse_mode="HTML"
            )


@dp.callback_query(lambda c: c.data and c.data.startswith("amt:"))
async def on_amount_select(callback: types.CallbackQuery) -> None:
    try:
        if not callback.data:
            await callback.answer("❌ Invalid selection data")
            return
            
        parts = callback.data.split(":")
        if len(parts) < 3:
            await callback.answer("❌ Invalid selection data")
            return
            
        suggestion_id = parts[1]
        size_str = parts[2]
        
        # Handle custom amount (not implemented yet)
        if size_str == "custom":
            await callback.answer("⚠️ Custom amount not yet implemented", show_alert=True)
            return
        
        size = float(size_str)
        
        # Fetch suggestion from Firestore to get all details
        db = get_client()
        suggestion_doc = db.collection("suggestions").document(suggestion_id).get()
        
        if not suggestion_doc.exists:
            await callback.answer("❌ Suggestion not found or expired", show_alert=True)
            return
        
        suggestion = suggestion_doc.to_dict()
        token_id = suggestion.get("tokenId", "")
        side = suggestion.get("side", "BUY_YES")
        price = suggestion.get("price", 0.5)
        
        side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
        confirm_msg = (
            f"{side_emoji} <b>Confirm Trade</b>\n\n"
            f"Market: {suggestion.get('title', 'N/A')[:60]}\n"
            f"Side: {side.upper()}\n"
            f"Size: {size} contracts\n"
            f"Price: ${price:.4f}\n"
            f"Total: ${size * price:.2f}\n\n"
            f"Ready to place this order?"
        )
        
        kb = confirm_kb(suggestion_id, token_id, side, price, size)
        await callback.message.edit_text(confirm_msg, reply_markup=kb, parse_mode="HTML")  # type: ignore
        await callback.answer()
    except ValueError:
        await callback.answer("⚠️ Invalid amount format", show_alert=True)
    except Exception as e:
        await callback.answer(f"⚠️ Error: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data == "cancel")
async def on_cancel(callback: types.CallbackQuery) -> None:
    await callback.message.delete()  # type: ignore
    await callback.answer("❌ Cancelled", show_alert=False)


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    try:
        if not callback.data:
            await callback.answer("❌ Invalid confirmation data", show_alert=True)
            return
            
        parts = callback.data.split(":")
        if len(parts) < 3:
            await callback.answer("❌ Invalid confirmation data", show_alert=True)
            return
            
        suggestion_id = parts[1]
        size = float(parts[2])
        
        # Fetch suggestion from Firestore to get all details
        db = get_client()
        suggestion_doc = db.collection("suggestions").document(suggestion_id).get()
        
        if not suggestion_doc.exists:
            await callback.answer("❌ Suggestion not found or expired", show_alert=True)
            return
        
        suggestion = suggestion_doc.to_dict()
        token_id = suggestion.get("tokenId", "")
        side = suggestion.get("side", "BUY_YES")
        price = suggestion.get("price", 0.5)
        
        # Loading indicator
        await callback.answer("⏳ Placing order...")
        
        # Place the trade
        user_chat_id = callback.from_user.id
        result = place_trade(suggestion_id, token_id, side, price, size, user_chat_id)
        
        if result.get("status") == "OPEN":
            side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
            success_msg = (
                f"✅ <b>Trade Placed Successfully!</b>\n\n"
                f"Market: {suggestion.get('title', 'N/A')[:60]}\n"
                f"{side_emoji} Side: {side.upper()}\n"
                f"📊 Size: {size} contracts\n"
                f"💵 Price: ${price:.4f}\n"
                f"💰 Total: ${size * price:.2f}\n\n"
                f"🆔 Trade ID: <code>{result.get('trade_id', 'N/A')}</code>\n\n"
                f"✨ Your order is now live on Polymarket!"
            )
            await callback.message.edit_text(success_msg, parse_mode="HTML")  # type: ignore
        else:
            await callback.message.edit_text(  # type: ignore
                f"❌ <b>Trade Failed</b>\n\n"
                f"Status: {result.get('status', 'UNKNOWN')}\n\n"
                f"Please try again or contact support.",
                parse_mode="HTML"
            )
    except ValueError:
        await callback.answer("⚠️ Invalid price or size format", show_alert=True)
    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            f"❌ <b>Error Placing Trade</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"💡 <b>Troubleshooting:</b>\n"
            f"• Check your wallet credentials\n"
            f"• Ensure sufficient balance\n"
            f"• Try again in a few moments\n\n"
            f"📧 Contact support if the issue persists.",
            parse_mode="HTML"
        )


@dp.message()
async def handle_unknown(message: types.Message) -> None:
    """Handle unknown commands and messages."""
    await message.answer(
        f"❓ <b>Command not found</b>\n\n"
        f"I don't understand that command.\n\n"
        f"<b>Available commands:</b>\n"
        f"• /balance - View your portfolio\n"
        f"• /suggest - Get trade suggestions\n\n"
        f"💡 Try one of these commands!",
        parse_mode="HTML"
    )


@app.post("/webhook")
async def telegram_webhook(req: Request) -> dict[str, bool]:
    data = await req.json()
    update = types.Update.model_validate(data)
    bot = get_bot()
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

