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
        await message.answer(f"Balance: ${bal['available_usd']:.2f}\nUse /suggest to view ideas.")
    except Exception as e:
        await message.answer(f"⚠️ Error fetching balance: {str(e)}\n\nPlease try again or contact support.")


@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message) -> None:
    try:
        # Notify user we're fetching data
        status_msg = await message.answer("🔄 Fetching suggestions...")
        
        db = get_client()
        snap = db.collection("suggestions").where("status", "==", "OPEN").order_by("edgeBps", direction="DESCENDING").limit(5).get()
        
        # Delete the status message
        await status_msg.delete()
        
        if not snap:
            bal = get_current()
            await message.answer(f"Balance: ${bal['available_usd']:.2f}\nNo suggestions right now.")
            return
        
        for doc in snap:
            s = doc.to_dict()
            text = suggestion_message(s.get("title", ""), s.get("side", ""), int(s.get("edgeBps", 0)))
            kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
            await message.answer(text, reply_markup=kb)
    except Exception as e:
        # User-friendly error handling
        error_msg = str(e)
        if "index" in error_msg.lower():
            await message.answer(
                "⚠️ Database index required!\n\n"
                "Please create the Firestore index using the link in the error logs, "
                "or contact your administrator.\n\n"
                "This is a one-time setup that takes 1-2 minutes."
            )
        elif "404" in error_msg or "does not exist" in error_msg:
            await message.answer(
                "⚠️ Database not found!\n\n"
                "Please ensure the Firestore database 'polytrade' is created.\n"
                "Contact your administrator."
            )
        else:
            await message.answer(f"⚠️ Error fetching suggestions: {error_msg}\n\nPlease try again later.")


@dp.callback_query(lambda c: c.data and c.data.startswith("amt:"))
async def on_amount_select(callback: types.CallbackQuery) -> None:
    try:
        if not callback.data or len(callback.data.split(":")) < 6:
            await callback.answer("Invalid selection data")
            return
            
        parts = callback.data.split(":")
        suggestion_id, token_id, side, size_type, size_str = parts[1], parts[2], parts[3], parts[4], parts[5]
        size = float(size_str)
        
        # TODO: fetch suggestion doc to get current price
        price = 0.5  # placeholder
        
        kb = confirm_kb(suggestion_id, token_id, side, price, size)
        await callback.message.edit_text(f"Confirm trade: {size} @ {price}", reply_markup=kb)  # type: ignore
        await callback.answer()
    except ValueError:
        await callback.answer("⚠️ Invalid amount format")
    except Exception as e:
        await callback.answer(f"⚠️ Error: {str(e)}")


@dp.callback_query(lambda c: c.data == "cancel")
async def on_cancel(callback: types.CallbackQuery) -> None:
    await callback.message.delete()  # type: ignore
    await callback.answer("Cancelled")


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    try:
        if not callback.data or len(callback.data.split(":")) < 6:
            await callback.answer("Invalid confirmation data")
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
            await callback.message.edit_text(  # type: ignore
                f"✅ Trade placed!\n"
                f"ID: {result.get('trade_id', 'N/A')}\n"
                f"{size} @ {price}"
            )
        else:
            await callback.message.edit_text(  # type: ignore
                f"❌ Trade failed\n"
                f"Status: {result.get('status', 'UNKNOWN')}"
            )
    except ValueError:
        await callback.answer("⚠️ Invalid price or size format")
    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            f"❌ Error placing trade: {str(e)}\n\n"
            f"Please check your wallet credentials and balance."
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

