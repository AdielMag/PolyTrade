from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def amount_presets_kb(suggestion_id: str, token_id: str, side: str) -> InlineKeyboardMarkup:
    """Create amount selection keyboard.
    
    Note: Only passes suggestion_id to stay under Telegram's 64-byte callback_data limit.
    All other data (token_id, side, price) is fetched from Firestore when button is clicked.
    """
    def btn(text: str, data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=data)

    rows = [
        [
            btn("💵 $1", f"amt:{suggestion_id}:1"), 
            btn("💰 $5", f"amt:{suggestion_id}:5"), 
            btn("💎 $10", f"amt:{suggestion_id}:10")
        ],
        [btn("✏️ Custom Amount", f"amt:{suggestion_id}:custom")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(suggestion_id: str, token_id: str, side: str, price: float, size: float) -> InlineKeyboardMarkup:
    """Create confirmation keyboard.
    
    Note: Only passes suggestion_id and size to stay under Telegram's 64-byte limit.
    All other data is fetched from Firestore when button is clicked.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm Trade", callback_data=f"confirm:{suggestion_id}:{size}"), 
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")
            ]
        ]
    )

