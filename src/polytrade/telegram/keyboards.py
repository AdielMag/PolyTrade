from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def amount_presets_kb(suggestion_id: str, market_id: str, side: str) -> InlineKeyboardMarkup:
    def btn(text: str, data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=data)

    rows = [
        [btn("5%", f"amt:{suggestion_id}:{market_id}:{side}:pct:5"), btn("10%", f"amt:{suggestion_id}:{market_id}:{side}:pct:10"), btn("25%", f"amt:{suggestion_id}:{market_id}:{side}:pct:25")],
        [btn("50%", f"amt:{suggestion_id}:{market_id}:{side}:pct:50"), btn("Max", f"amt:{suggestion_id}:{market_id}:{side}:pct:100")],
        [btn("$10", f"amt:{suggestion_id}:{market_id}:{side}:usd:10"), btn("$25", f"amt:{suggestion_id}:{market_id}:{side}:usd:25"), btn("$50", f"amt:{suggestion_id}:{market_id}:{side}:usd:50")],
        [btn("Custom", f"amt:{suggestion_id}:{market_id}:{side}:custom:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(suggestion_id: str, market_id: str, side: str, amount_usd: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm", callback_data=f"confirm:{suggestion_id}:{market_id}:{side}:{amount_usd}"), InlineKeyboardButton(text="Cancel", callback_data="cancel")]
        ]
    )


