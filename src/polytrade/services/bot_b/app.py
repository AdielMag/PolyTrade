from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types

from ...shared.config import settings
from ...shared.balances import get_current
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()
dp = Dispatcher()


def get_bot() -> Bot:
    if not settings.bot_b_token:
        raise RuntimeError("TELEGRAM_BOT_B_TOKEN is not set")
    return Bot(token=settings.bot_b_token)


async def send_notification(chat_id: int, text: str) -> None:
    """Send notification to user with balance header. Handles all errors gracefully."""
    try:
        bal = get_current()
        header = f"Balance: ${bal['available_usd']:.2f}\n"
        bot = get_bot()
        await bot.send_message(chat_id, header + text)
    except RuntimeError as e:
        # Bot token not configured
        from loguru import logger
        logger.error(f"Bot B configuration error: {e}")
    except Exception as e:
        # Any other error (network, invalid chat_id, etc.)
        from loguru import logger
        logger.error(f"Failed to send notification to {chat_id}: {e}")


@app.post("/webhook")
async def telegram_webhook(req: Request) -> dict[str, bool]:
    # Currently, we do not process inbound commands; reserved for future
    return {"ok": True}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

