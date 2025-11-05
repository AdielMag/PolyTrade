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
    
    # Format event time if available
    end_date_str = ""
    if end_date:
        try:
            from datetime import datetime
            # Parse ISO format: "2024-06-17T12:00:00Z" or "2024-06-17 12:00:00+00:00"
            if isinstance(end_date, str):
                # Handle both formats from API
                if ' ' in end_date and '+' in end_date:
                    # Format: "2025-11-09 03:00:00+00"
                    dt = datetime.fromisoformat(end_date.replace('+00', '+00:00'))
                else:
                    # Format: "2025-11-09T03:00:00Z"
                    dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                
                # Calculate time until event
                from datetime import timezone
                now = datetime.now(timezone.utc)
                time_until = dt - now
                
                if time_until.total_seconds() > 0:
                    hours = int(time_until.total_seconds() // 3600)
                    minutes = int((time_until.total_seconds() % 3600) // 60)
                    if hours == 0:
                        end_date_str = f"\n⏰ 🔴 <b>STARTING IN {minutes} MINUTES!</b>"
                    elif hours < 6:
                        end_date_str = f"\n⏰ 🟡 <b>Starts in {hours}h {minutes}m</b> ({dt.strftime('%H:%M UTC')})"
                    else:
                        end_date_str = f"\n⏰ Game starts: <b>{dt.strftime('%b %d, %H:%M UTC')}</b> (in {hours}h)"
                else:
                    # Game already started - it's LIVE!
                    hours_ago = abs(int(time_until.total_seconds() // 3600))
                    minutes_ago = abs(int((time_until.total_seconds() % 3600) // 60))
                    if hours_ago == 0:
                        end_date_str = f"\n⏰ 🔴 <b>LIVE NOW!</b> (started {minutes_ago}m ago)"
                    else:
                        end_date_str = f"\n⏰ 🔴 <b>LIVE NOW!</b> (started {hours_ago}h {minutes_ago}m ago)"
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

