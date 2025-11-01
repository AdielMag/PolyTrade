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

configure_logging()

app = FastAPI()
dp = Dispatcher()


def get_bot() -> Bot:
    if not settings.bot_a_token:
        # Return a bot with an obviously invalid token is risky; better to raise when used
        raise RuntimeError("TELEGRAM_BOT_A_TOKEN is not set")
    return Bot(token=settings.bot_a_token)


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    try:
        # Force fresh balance fetch from Polymarket
        bal = get_current(force=True)
        welcome_msg = (
            f"🎯 <b>Welcome to PolyTrade Bot!</b>\n\n"
            f"💰 <b>Portfolio</b>\n"
            f"   Total: ${bal['total_usd']:.2f}\n"
            f"   Available: ${bal['available_usd']:.2f}\n"
            f"   In Orders: ${bal['locked_usd']:.2f}\n\n"
            f"📊 Use /suggest to view trade opportunities\n"
            f"💡 Get AI-powered market analysis and execute trades instantly!"
        )
        await message.answer(welcome_msg, parse_mode="HTML")
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
        # Notify user we're fetching data
        status_msg = await message.answer("🔄 <b>Analyzing markets...</b>", parse_mode="HTML")
        
        db = get_client()
        snap = db.collection("suggestions").where("status", "==", "OPEN").order_by("edgeBps", direction="DESCENDING").limit(5).get()
        
        # Delete the status message
        await status_msg.delete()
        
        if not snap:
            bal = get_current()
            no_suggestions_msg = (
                f"💰 <b>Portfolio: ${bal['total_usd']:.2f}</b>\n"
                f"   Available: ${bal['available_usd']:.2f}\n"
                f"   In Orders: ${bal['locked_usd']:.2f}\n\n"
                f"📭 <b>No suggestions available right now</b>\n\n"
                f"The analyzer is constantly scanning markets.\n"
                f"Check back soon for new opportunities! 🎯"
            )
            await message.answer(no_suggestions_msg, parse_mode="HTML")
            return
        
        for doc in snap:
            s = doc.to_dict()
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

