from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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
            f"<b>Total Portfolio: ${bal['total_usd']:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Available: ${bal['available_usd']:.2f}\n"
            f"📝 In Orders: ${bal['locked_usd']:.2f}\n"
            f"💎 Positions: ${bal['positions_usd']:.2f}\n"
        )
        
        # Add detailed open orders if any
        orders = bal.get("orders", [])
        if orders:
            balance_msg += f"\n\n<b>📝 Open Orders ({len(orders)}):</b>\n"
            for i, order in enumerate(orders, 1):
                side_emoji = "📈" if order['side'].upper() == "BUY" else "📉"
                balance_msg += (
                    f"\n{side_emoji} <b>Order #{i}</b>\n"
                    f"├ Side: {order['side'].upper()}\n"
                    f"├ Size: {order['size']:.2f} @ ${order['price']:.4f}\n"
                    f"├ Value: ${order['value']:.2f}\n"
                    f"└ Market: {order.get('market', 'N/A')[:60]}\n"
                )
        
        # Add detailed positions if any
        positions = bal.get("positions", [])
        if positions:
            balance_msg += f"\n\n<b>💎 Active Positions ({len(positions)}):</b>\n"
            for i, pos in enumerate(positions, 1):
                pnl_emoji = "📈" if pos['pnl'] >= 0 else "📉"
                pnl_sign = "+" if pos['pnl'] >= 0 else ""
                balance_msg += (
                    f"\n{pnl_emoji} <b>Position #{i}</b>\n"
                    f"├ Market: {pos['title'][:50]}...\n"
                    f"├ Outcome: <b>{pos['outcome']}</b>\n"
                    f"├ Size: {pos['size']:.2f} shares\n"
                    f"├ Avg Price: ${pos['avgPrice']:.4f}\n"
                    f"├ Current: ${pos['curPrice']:.4f}\n"
                    f"├ Value: ${pos['currentValue']:.2f}\n"
                    f"└ P&L: {pnl_sign}${pos['pnl']:.2f}\n"
                )
        
        if not orders and not positions:
            balance_msg += f"\n\n<i>No open orders or positions</i>\n"
        
        balance_msg += f"\n\n📊 Use /suggest to view trade opportunities"
        
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
        db = get_client()
        for s in suggestions:
            # Query for this suggestion by tokenId to get its document ID
            snap = db.collection("suggestions").where("tokenId", "==", s.get("tokenId", "")).where("status", "==", "OPEN").limit(1).get()
            if snap:
                doc = snap[0]
                text = suggestion_message(s.get("title", ""), s.get("side", ""), int(s.get("edgeBps", 0)))
                kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
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
        if not callback.data or len(callback.data.split(":")) < 6:
            await callback.answer("❌ Invalid selection data")
            return
            
        parts = callback.data.split(":")
        suggestion_id, token_id, side, size_type, size_str = parts[1], parts[2], parts[3], parts[4], parts[5]
        size = float(size_str)
        
        # TODO: fetch suggestion doc to get current price
        price = 0.5  # placeholder
        
        side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
        confirm_msg = (
            f"{side_emoji} <b>Confirm Trade</b>\n\n"
            f"Side: {side.upper()}\n"
            f"Size: {size} contracts\n"
            f"Price: {price:.4f}\n"
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
        if not callback.data or len(callback.data.split(":")) < 6:
            await callback.answer("❌ Invalid confirmation data", show_alert=True)
            return
            
        parts = callback.data.split(":")
        suggestion_id, token_id, side, price_str, size_str = parts[1], parts[2], parts[3], parts[4], parts[5]
        price, size = float(price_str), float(size_str)
        
        # Loading indicator
        await callback.answer("⏳ Placing order...")
        
        # Place the trade
        user_chat_id = callback.from_user.id
        result = place_trade(suggestion_id, token_id, side, price, size, user_chat_id)
        
        if result.get("status") == "OPEN":
            side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
            success_msg = (
                f"✅ <b>Trade Placed Successfully!</b>\n\n"
                f"{side_emoji} Side: {side.upper()}\n"
                f"📊 Size: {size} contracts\n"
                f"💵 Price: {price:.4f}\n"
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

