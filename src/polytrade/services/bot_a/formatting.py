from __future__ import annotations

from ...shared.balances import get_current


def balance_header() -> str:
    bal = get_current()
    return (
        f"💰 Portfolio: ${bal['total_usd']:.2f}\n"
        f"   💵 Available: ${bal['available_usd']:.2f}\n"
        f"   📝 In Orders: ${bal['locked_usd']:.2f}\n"
        f"   💎 Positions: ${bal['positions_usd']:.2f}\n"
    )


def suggestion_message(title: str, side: str, edge_bps: int) -> str:
    side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
    edge_color = "🟢" if edge_bps > 200 else "🟡" if edge_bps > 100 else "🔵"
    
    return (
        balance_header() + 
        f"\n{edge_color} <b>Trade Opportunity</b>\n\n"
        f"🎯 <b>{title}</b>\n\n"
        f"{side_emoji} Side: <b>{side.upper()}</b>\n"
        f"📊 Edge: <b>{edge_bps}</b> bps\n\n"
        f"💡 Select position size below:"
    )

