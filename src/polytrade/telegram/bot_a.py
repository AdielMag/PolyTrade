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
        kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
        await message.answer(text, reply_markup=kb)


@dp.callback_query(lambda c: c.data and c.data.startswith("amt:"))
async def on_amount_select(callback: types.CallbackQuery) -> None:
    # amt:<suggestion_id>:<token_id>:<side>:<kind>:<value>
    parts = (callback.data or "").split(":")
    _, suggestion_id, token_id, side, kind, value = parts
    size = 1.0
    if kind == "size":
        size = float(value)
    else:
        await callback.message.answer("Send custom size (tokens)")
        await callback.answer()
        return
    price = 0.01  # placeholder; fetch best ask/expected price in analyzer/suggestion
    await callback.message.answer(
        f"Confirm trade?\n{side} token {token_id}\nPrice: {price:.3f}\nSize: {size}",
        reply_markup=confirm_kb(suggestion_id, token_id, side, price, size),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    # confirm:<suggestion_id>:<token_id>:<side>:<price>:<size>
    _, suggestion_id, token_id, side, price, size = (callback.data or "").split(":")
    trade = place_trade(
        suggestion_id=suggestion_id,
        token_id=token_id,
        side=side,
        price=float(price),
        size=float(size),
        user_chat_id=callback.from_user.id,
    )
    await callback.message.answer(f"Trade status: {trade['status']} size={trade['size']}")
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


