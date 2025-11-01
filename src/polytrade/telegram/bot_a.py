from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from ..config import settings
from ..firestore import get_client
from ..balances import get_current
from .formatting import suggestion_message
from .keyboards import amount_presets_kb, confirm_kb
from ..execution import place_trade
from ..logging import configure_logging

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
        # amt:<suggestion_id>:<token_id>:<side>:<kind>:<value>
        parts = (callback.data or "").split(":")
        if len(parts) != 6:
            await callback.answer("❌ Invalid callback data", show_alert=True)
            return
        _, suggestion_id, token_id, side, kind, value = parts
        size = 1.0
        if kind == "size":
            size = float(value)
        else:
            await callback.message.answer("📝 Send custom size (tokens)")
            await callback.answer()
            return
        price = 0.01  # placeholder; fetch best ask/expected price in analyzer/suggestion
        await callback.message.answer(
            f"Confirm trade?\n{side} token {token_id}\nPrice: {price:.3f}\nSize: {size}",
            reply_markup=confirm_kb(suggestion_id, token_id, side, price, size),
        )
        await callback.answer()
    except ValueError as e:
        await callback.answer(f"❌ Invalid value: {str(e)}", show_alert=True)
    except Exception as e:
        await callback.answer(f"⚠️ Error: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    try:
        # confirm:<suggestion_id>:<token_id>:<side>:<price>:<size>
        parts = (callback.data or "").split(":")
        if len(parts) != 6:
            await callback.answer("❌ Invalid callback data", show_alert=True)
            return
        _, suggestion_id, token_id, side, price, size = parts
        
        # Notify user we're placing the trade
        await callback.answer("🔄 Placing trade...", show_alert=False)
        status_msg = await callback.message.answer("⏳ Placing your trade...")
        
        trade = place_trade(
            suggestion_id=suggestion_id,
            token_id=token_id,
            side=side,
            price=float(price),
            size=float(size),
            user_chat_id=callback.from_user.id,
        )
        
        # Delete status message
        await status_msg.delete()
        
        if trade['status'] == 'OPEN':
            await callback.message.answer(
                f"✅ Trade placed successfully!\n\n"
                f"Status: {trade['status']}\n"
                f"Size: {trade['size']}\n"
                f"Entry Price: {trade['entryPx']}"
            )
        elif trade['status'] == 'FAILED':
            await callback.message.answer(
                f"❌ Trade failed!\n\n"
                f"Status: {trade['status']}\n"
                f"Please check your balance and try again."
            )
        else:
            await callback.message.answer(f"Trade status: {trade['status']} size={trade['size']}")
            
    except ValueError as e:
        await callback.answer(f"❌ Invalid value: {str(e)}", show_alert=True)
    except RuntimeError as e:
        await callback.message.answer(f"⚠️ Configuration error: {str(e)}")
    except Exception as e:
        await callback.message.answer(
            f"⚠️ Error placing trade: {str(e)}\n\n"
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


