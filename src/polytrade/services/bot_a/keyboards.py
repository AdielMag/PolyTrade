from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def amount_presets_kb(suggestion_id: str, token_id: str, side: str) -> InlineKeyboardMarkup:
    def btn(text: str, data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=data)

    rows = [
        [
            btn("💵 $1", f"amt:{suggestion_id}:{token_id}:{side}:size:1"), 
            btn("💰 $5", f"amt:{suggestion_id}:{token_id}:{side}:size:5"), 
            btn("💎 $10", f"amt:{suggestion_id}:{token_id}:{side}:size:10")
        ],
        [btn("✏️ Custom Amount", f"amt:{suggestion_id}:{token_id}:{side}:custom:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(suggestion_id: str, token_id: str, side: str, price: float, size: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm Trade", callback_data=f"confirm:{suggestion_id}:{token_id}:{side}:{price}:{size}"), 
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")
            ]
        ]
    )

