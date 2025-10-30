from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types

from ..config import settings
from ..balances import get_current


app = FastAPI()
bot = Bot(token=settings.bot_b_token or "")
dp = Dispatcher()


async def send_notification(chat_id: int, text: str) -> None:
    bal = get_current()
    header = f"Balance: ${bal['available_usd']:.2f}\n"
    await bot.send_message(chat_id, header + text)


@app.post("/webhook")
async def telegram_webhook(req: Request):
    # Currently, we do not process inbound commands; reserved for future
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


