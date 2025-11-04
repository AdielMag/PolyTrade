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


def suggestion_message(title: str, side: str, yes_prob: float, no_prob: float, end_date: str = None) -> str:
    """Format a suggestion message with market probabilities."""
    side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
    
    # Determine which side we're suggesting
    if "YES" in side.upper():
        suggested_side = "YES"
        suggested_prob = yes_prob
    else:
        suggested_side = "NO"
        suggested_prob = no_prob
    
    # Format end date if available
    end_date_str = ""
    if end_date:
        try:
            from datetime import datetime
            # Parse ISO format: "2024-06-17T12:00:00Z"
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            end_date_str = f"\n⏰ Event ends: <b>{dt.strftime('%b %d, %Y %H:%M UTC')}</b>"
        except Exception:
            pass  # Skip if date parsing fails
    
    return (
        f"🎯 <b>Trade Opportunity</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{side_emoji} <b>Suggested: BUY {suggested_side}</b>\n\n"
        f"📊 <b>Market Odds:</b>\n"
        f"  ✅ YES: <b>{yes_prob*100:.0f}%</b>\n"
        f"  ❌ NO: <b>{no_prob*100:.0f}%</b>\n\n"
        f"💰 You're buying <b>{suggested_side}</b> at <b>{suggested_prob*100:.0f}%</b>"
        f"{end_date_str}\n\n"
        f"💡 Select position size below:"
    )

