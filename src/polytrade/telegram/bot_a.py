from __future__ import annotations

import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.i18n import I18n

from ..config import settings
from ..firestore import get_client
from ..balances import get_current
from .formatting import suggestion_message
from .keyboards import amount_presets_kb, confirm_kb
from ..execution import place_trade


app = FastAPI()
bot = Bot(token=settings.bot_a_token or "")
dp = Dispatcher()
i18n = I18n(path="locales", default_locale="en")


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    bal = get_current()
    await message.answer(f"Balance: ${bal['available_usd']:.2f}\nUse /suggest to view ideas.")


@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message) -> None:
    db = get_client()
    snap = db.collection("suggestions").where("status", "==", "OPEN").order_by("edgeBps", direction="DESCENDING").limit(5).get()
    if not snap:
        bal = get_current()
        await message.answer(f"Balance: ${bal['available_usd']:.2f}\nNo suggestions right now.")
        return
    for doc in snap:
        s = doc.to_dict()
        text = suggestion_message(s.get("title", ""), s.get("side", ""), int(s.get("edgeBps", 0)))
        kb = amount_presets_kb(suggestion_id=doc.id, market_id=s.get("marketId", ""), side=s.get("side", ""))
        await message.answer(text, reply_markup=kb)


@dp.callback_query(lambda c: c.data and c.data.startswith("amt:"))
async def on_amount_select(callback: types.CallbackQuery) -> None:
    # amt:<suggestion_id>:<market_id>:<side>:<kind>:<value>
    parts = (callback.data or "").split(":")
    _, suggestion_id, market_id, side, kind, value = parts
    bal = get_current()
    amount = 0.0
    if kind == "pct":
        pct = float(value)
        amount = max(1.0, bal["available_usd"] * (pct / 100.0))
    elif kind == "usd":
        amount = float(value)
    else:
        await callback.message.answer("Send custom USD amount (e.g., 12.5)")
        await callback.answer()
        return
    amount = min(amount, bal["available_usd"])  # cap by balance
    await callback.message.answer(
        f"Confirm trade?\n{side} on {market_id}\nAmount: ${amount:.2f}",
        reply_markup=confirm_kb(suggestion_id, market_id, side, amount),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    # confirm:<suggestion_id>:<market_id>:<side>:<amount>
    _, suggestion_id, market_id, side, amount = (callback.data or "").split(":")
    trade = place_trade(
        suggestion_id=suggestion_id,
        market_id=market_id,
        side=side,
        amount_usd=float(amount),
        user_chat_id=callback.from_user.id,
    )
    await callback.message.answer(f"Trade status: {trade['status']} amount=${trade['amountUsd']:.2f}")
    await callback.answer()


@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = types.Update.model_validate(data)
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


