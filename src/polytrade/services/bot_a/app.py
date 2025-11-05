from __future__ import annotations

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from ...shared.config import settings
from ...shared.firestore import get_client
from ...shared.balances import get_current
from .formatting import suggestion_message
from .keyboards import amount_presets_kb, confirm_kb
from ...shared.execution import place_trade
from ...shared.logging import configure_logging
from ..analyzer.analysis import run_analysis

configure_logging()

app = FastAPI()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# States for custom input
class CustomRangeStates(StatesGroup):
    waiting_for_range = State()
    waiting_for_time_window = State()


# Workaround for webhook-based FSM: track users waiting for custom input
# In webhook mode, MemoryStorage doesn't persist between requests
_users_waiting_for_custom_range: set[int] = set()
_users_waiting_for_time_window: set[int] = set()

# Store user's selected time window (user_id -> hours)
_user_time_windows: dict[int, float] = {}


def get_bot() -> Bot:
    if not settings.bot_a_token:
        # Return a bot with an obviously invalid token is risky; better to raise when used
        raise RuntimeError("TELEGRAM_BOT_A_TOKEN is not set")
    return Bot(token=settings.bot_a_token)


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    try:
        # Force fresh balance fetch from Polymarket
        bal = get_current(force=True)
        
        # Build the main balance message
        balance_msg = (
            f"💰 <b>Portfolio Balance</b>\n\n"
            f"<b>Total: ${bal['total_usd']:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Available: ${bal['available_usd']:.2f}\n"
            f"📝 In Orders: ${bal['locked_usd']:.2f}\n"
            f"💎 Positions: ${bal['positions_usd']:.2f}\n"
        )
        
        # Add detailed open orders if any (limit to 5 per message)
        orders = bal.get("orders", [])
        max_orders_to_show = 5
        if orders:
            orders_to_show = orders[:max_orders_to_show]
            balance_msg += f"\n\n<b>📝 Open Orders ({len(orders)}):</b>\n"
            for i, order in enumerate(orders_to_show, 1):
                side_emoji = "📈" if order['side'].upper() == "BUY" else "📉"
                market_name = order.get('market', 'N/A')
                if len(market_name) > 35:
                    market_name = market_name[:32] + "..."
                balance_msg += (
                    f"\n{side_emoji} <b>#{i}</b> {order['side'][:3]} "
                    f"{order['size']:.1f}@${order['price']:.3f} "
                    f"(${order['value']:.2f})\n"
                    f"  {market_name}\n"
                )
            if len(orders) > max_orders_to_show:
                balance_msg += f"<i>...and {len(orders) - max_orders_to_show} more</i>\n"
        
        # Add detailed positions if any (limit to 5 per message)
        positions = bal.get("positions", [])
        max_positions_to_show = 5
        if positions:
            positions_to_show = positions[:max_positions_to_show]
            balance_msg += f"\n\n<b>💎 Positions ({len(positions)}):</b>\n"
            for i, pos in enumerate(positions_to_show, 1):
                pnl_emoji = "📈" if pos['pnl'] >= 0 else "📉"
                pnl_sign = "+" if pos['pnl'] >= 0 else ""
                market_name = pos['title']
                if len(market_name) > 35:
                    market_name = market_name[:32] + "..."
                balance_msg += (
                    f"\n{pnl_emoji} <b>#{i}</b> {pos['outcome']}: "
                    f"${pos['currentValue']:.2f} "
                    f"({pnl_sign}${pos['pnl']:.2f})\n"
                    f"  {market_name}\n"
                    f"  {pos['size']:.1f}sh @ ${pos['avgPrice']:.3f}→${pos['curPrice']:.3f}\n"
                )
            if len(positions) > max_positions_to_show:
                balance_msg += f"<i>...and {len(positions) - max_positions_to_show} more</i>\n"
        
        if not orders and not positions:
            balance_msg += f"\n\n<i>No open orders or positions</i>\n"
        
        balance_msg += f"\n\n📊 /suggest for trade opportunities"
        
        # Ensure message is under Telegram's 4096 character limit
        if len(balance_msg) > 4000:
            # If still too long, truncate positions/orders more aggressively
            balance_msg = (
                f"💰 <b>Portfolio Balance</b>\n\n"
                f"<b>Total: ${bal['total_usd']:.2f}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Available: ${bal['available_usd']:.2f}\n"
                f"📝 In Orders: ${bal['locked_usd']:.2f} ({len(orders)} orders)\n"
                f"💎 Positions: ${bal['positions_usd']:.2f} ({len(positions)} positions)\n\n"
                f"<i>Too many items to display details.\n"
                f"Summary view only.</i>\n\n"
                f"📊 /suggest for trade opportunities"
            )
        
        await message.answer(balance_msg, parse_mode="HTML")
    except Exception as e:
        await message.answer(
            f"⚠️ <b>Error fetching balance</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Please try again or contact support.",
            parse_mode="HTML"
        )


@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message) -> None:
    """Ask user for their desired time window first."""
    try:
        # Create inline keyboard with time window options
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔴 6 Hours (Live & Urgent)", callback_data="time:6")
            ],
            [
                InlineKeyboardButton(text="🟡 12 Hours (Today's Games)", callback_data="time:12")
            ],
            [
                InlineKeyboardButton(text="🟢 24 Hours (Next Day)", callback_data="time:24")
            ],
            [
                InlineKeyboardButton(text="🔍 Custom Window", callback_data="time:custom")
            ]
        ])
        
        await message.answer(
            "⏰ <b>Select Time Window</b>\n\n"
            "How far ahead do you want to look?\n\n"
            "• <b>6 Hours</b> - Live games & starting soon\n"
            "• <b>12 Hours</b> - Today's schedule\n"
            "• <b>24 Hours</b> - Tomorrow's games too\n"
            "• <b>Custom</b> - Set your own window\n\n"
            "💡 Shorter windows = more urgent opportunities!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"⚠️ <b>Error</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )


@dp.callback_query(lambda c: c.data and c.data.startswith("time:"))
async def on_time_window_select(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle time window selection, then ask for probability range."""
    try:
        if not callback.data:
            await callback.answer("❌ Invalid selection")
            return
        
        parts = callback.data.split(":")
        user_id = callback.from_user.id
        
        # Handle custom time window
        if len(parts) >= 2 and parts[1] == "custom":
            await callback.message.edit_text(
                "⏰ <b>Custom Time Window</b>\n\n"
                "Enter the number of hours to look ahead:\n"
                "👉 Enter a number (e.g., <code>8</code> for 8 hours)\n\n"
                "<b>Examples:</b>\n"
                "• <code>3</code> - Next 3 hours only\n"
                "• <code>8</code> - Next 8 hours\n"
                "• <code>48</code> - Next 2 days\n\n"
                "💡 Valid range: 1-72 hours\n\n"
                "📝 Type hours now:",
                parse_mode="HTML"
            )
            
            # Set state to wait for custom time window input
            await state.set_state(CustomRangeStates.waiting_for_time_window)
            _users_waiting_for_time_window.add(user_id)
            logger.info(f"User {user_id} is now waiting for custom time window input")
            
            await callback.answer()
            return
        
        if len(parts) < 2:
            await callback.answer("❌ Invalid time window format")
            return
        
        # Parse time window
        try:
            hours = float(parts[1])
        except ValueError:
            await callback.answer("❌ Invalid time window")
            return
        
        # Store user's time window selection
        _user_time_windows[user_id] = hours
        logger.info(f"User {user_id} selected {hours}h time window")
        
        # Now show probability range selection
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 80-90% (Strong Favorites)", callback_data="range:80:90")
            ],
            [
                InlineKeyboardButton(text="⚖️ 60-75% (Moderate)", callback_data="range:60:75")
            ],
            [
                InlineKeyboardButton(text="🎲 40-60% (Balanced)", callback_data="range:40:60")
            ],
            [
                InlineKeyboardButton(text="📊 20-40% (Underdogs)", callback_data="range:20:40")
            ],
            [
                InlineKeyboardButton(text="🔍 Custom Range", callback_data="range:custom")
            ]
        ])
        
        await callback.message.edit_text(
            f"⏰ Time window: <b>{int(hours)}h</b> ✅\n\n"
            f"🎯 <b>Select Probability Range</b>\n\n"
            "Choose what type of bets you want to see:\n\n"
            "• <b>80-90%</b> - Heavy favorites (safer)\n"
            "• <b>60-75%</b> - Moderate favorites\n"
            "• <b>40-60%</b> - Balanced/toss-up games\n"
            "• <b>20-40%</b> - Underdogs (riskier)",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in time window selection: {e}")
        await callback.answer(f"⚠️ Error: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("range:"))
async def on_range_select(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle range selection and run analyzer."""
    try:
        if not callback.data:
            await callback.answer("❌ Invalid selection")
            return
        
        user_id = callback.from_user.id
        
        # Get user's time window (default to 6 hours if not set)
        time_window_hours = _user_time_windows.get(user_id, 6.0)
        
        parts = callback.data.split(":")
        
        # Handle custom range - ask user for input
        if len(parts) >= 2 and parts[1] == "custom":
            await callback.message.edit_text(
                "🔢 <b>Custom Probability Range</b>\n\n"
                "Enter your desired range in the format:\n"
                "👉 <code>min-max</code>\n\n"
                "<b>Examples:</b>\n"
                "• <code>70-85</code> - Markets between 70-85%\n"
                "• <code>30-50</code> - Markets between 30-50%\n"
                "• <code>15-25</code> - Markets between 15-25%\n\n"
                "💡 Valid range: 1-99%\n"
                "⚠️ Min must be less than max\n\n"
                "📝 Type your range now:",
                parse_mode="HTML"
            )
            
            # Set state to wait for custom range input
            await state.set_state(CustomRangeStates.waiting_for_range)
            
            # Also track in our workaround dict (for webhook mode)
            user_id = callback.from_user.id
            _users_waiting_for_custom_range.add(user_id)
            logger.info(f"User {user_id} is now waiting for custom range input")
            
            await callback.answer()
            return
        
        if len(parts) < 3:
            await callback.answer("❌ Invalid range format")
            return
        
        min_pct = int(parts[1])
        max_pct = int(parts[2])
        min_price = min_pct / 100.0
        max_price = max_pct / 100.0
        
        # Update message to show analyzing
        await callback.message.edit_text(
            f"🔍 <b>Analyzing {min_pct}-{max_pct}% markets...</b>\n\n"
            f"⏰ Time window: <b>{int(time_window_hours)}h</b>\n"
            f"⏳ Fetching data from Polymarket\n"
            f"⚡ Using multithreading\n\n"
            f"<i>Please wait 10-20 seconds...</i>",
            parse_mode="HTML"
        )
        
        # Run analyzer with user's selected range and time window
        logger.info(f"User requested suggestions: {min_pct}-{max_pct}% in next {time_window_hours}h")
        suggestions = run_analysis(
            max_suggestions=5, 
            min_price=min_price, 
            max_price=max_price,
            time_window_hours=time_window_hours
        )
        
        logger.info(f"✅ Analyzer completed - generated {len(suggestions)} suggestions")
        
        # Delete the analyzing message
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        if not suggestions:
            logger.info("❌ No suggestions generated")
            no_suggestions_msg = (
                f"📭 <b>No suggestions found</b>\n\n"
                f"No markets in the <b>{min_pct}-{max_pct}%</b> range were found.\n\n"
                f"💡 Try a different range:\n"
                f"• Use /suggest to try again\n"
                f"• Try a wider range (e.g., 40-60%)\n\n"
                f"📊 Use /balance to check your portfolio"
            )
            await callback.message.answer(no_suggestions_msg, parse_mode="HTML")
            return
        
        # Get the suggestion IDs from firestore to pass to keyboards
        # The suggestions returned by run_analysis have been saved to firestore
        # We need to query them back to get their document IDs
        logger.info(f"📤 Sending {len(suggestions)} suggestions to user...")
        db = get_client()
        sent_count = 0
        
        for i, s in enumerate(suggestions, 1):
            try:
                # Query for this suggestion by tokenId to get its document ID
                snap = db.collection("suggestions").where("tokenId", "==", s.get("tokenId", "")).where("status", "==", "OPEN").limit(1).get()
                if snap:
                    doc = snap[0]
                    text = suggestion_message(
                        s.get("title", ""), 
                        s.get("side", ""), 
                        s.get("yesProbability", 0.5), 
                        s.get("noProbability", 0.5),
                        s.get("endDate", None)
                    )
                    kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
                    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
                    sent_count += 1
                    logger.info(f"✅ Sent suggestion {i}/{len(suggestions)}")
            except Exception as send_err:
                logger.error(f"❌ Error sending suggestion {i}: {send_err}")
        
        logger.info(f"✅ Finished sending {sent_count}/{len(suggestions)} suggestions to user")
        await callback.answer()  # Acknowledge the callback
        return  # Explicitly return to end the function
    except Exception as e:
        logger.error(f"Error in range selection: {e}")
        await callback.answer(f"⚠️ Error: {str(e)}", show_alert=True)


@dp.message(CustomRangeStates.waiting_for_time_window)
async def process_custom_time_window(message: types.Message, state: FSMContext) -> None:
    """Process user's custom time window input."""
    try:
        user_id = message.from_user.id
        
        # Check if user is in our workaround set
        if user_id not in _users_waiting_for_time_window:
            logger.warning(f"User {user_id} sent message but not in time window waiting set")
            return
        
        logger.info(f"Processing custom time window from user {user_id}: {message.text}")
        user_input = message.text.strip()
        
        # Parse input as number
        try:
            hours = float(user_input)
        except ValueError:
            await message.answer(
                "❌ <b>Invalid number</b>\n\n"
                "Please enter a valid number of hours.\n"
                "Example: <code>8</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        # Validate range
        if hours < 1 or hours > 72:
            await message.answer(
                "❌ <b>Out of range</b>\n\n"
                "Please enter between 1 and 72 hours.\n"
                "Example: <code>8</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        # Clear state and store time window
        await state.clear()
        _users_waiting_for_time_window.discard(user_id)
        _user_time_windows[user_id] = hours
        logger.info(f"User {user_id} set custom time window: {hours}h")
        
        # Show probability range selection
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 80-90% (Strong Favorites)", callback_data="range:80:90")
            ],
            [
                InlineKeyboardButton(text="⚖️ 60-75% (Moderate)", callback_data="range:60:75")
            ],
            [
                InlineKeyboardButton(text="🎲 40-60% (Balanced)", callback_data="range:40:60")
            ],
            [
                InlineKeyboardButton(text="📊 20-40% (Underdogs)", callback_data="range:20:40")
            ],
            [
                InlineKeyboardButton(text="🔍 Custom Range", callback_data="range:custom")
            ]
        ])
        
        await message.answer(
            f"⏰ Time window: <b>{hours:.0f}h</b> ✅\n\n"
            f"🎯 <b>Select Probability Range</b>\n\n"
            "Choose what type of bets you want to see:\n\n"
            "• <b>80-90%</b> - Heavy favorites (safer)\n"
            "• <b>60-75%</b> - Moderate favorites\n"
            "• <b>40-60%</b> - Balanced/toss-up games\n"
            "• <b>20-40%</b> - Underdogs (riskier)",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error processing custom time window: {e}")
        await message.answer(
            f"⚠️ <b>Error</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Please try /suggest again.",
            parse_mode="HTML"
        )
        await state.clear()
        _users_waiting_for_time_window.discard(user_id)


@dp.message(CustomRangeStates.waiting_for_range)
async def process_custom_range(message: types.Message, state: FSMContext) -> None:
    """Process user's custom range input."""
    try:
        user_id = message.from_user.id
        
        # Check if user is in our workaround set (for webhook mode)
        if user_id not in _users_waiting_for_custom_range:
            logger.warning(f"User {user_id} sent message but not in waiting set")
            return
        
        logger.info(f"Processing custom range input from user {user_id}: {message.text}")
        user_input = message.text.strip()
        
        # Parse input format: "min-max"
        if '-' not in user_input:
            await message.answer(
                "❌ <b>Invalid format</b>\n\n"
                "Please use format: <code>min-max</code>\n"
                "Example: <code>70-85</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        parts = user_input.split('-')
        if len(parts) != 2:
            await message.answer(
                "❌ <b>Invalid format</b>\n\n"
                "Please use format: <code>min-max</code>\n"
                "Example: <code>70-85</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        try:
            min_pct = int(parts[0].strip())
            max_pct = int(parts[1].strip())
        except ValueError:
            await message.answer(
                "❌ <b>Invalid numbers</b>\n\n"
                "Please enter valid percentages.\n"
                "Example: <code>70-85</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        # Validate range
        if min_pct < 1 or max_pct > 99:
            await message.answer(
                "❌ <b>Out of range</b>\n\n"
                "Percentages must be between 1 and 99.\n"
                "Example: <code>70-85</code>\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        if min_pct >= max_pct:
            await message.answer(
                "❌ <b>Invalid range</b>\n\n"
                "Min must be less than max.\n"
                "Example: <code>70-85</code> (not <code>85-70</code>)\n\n"
                "Try again:",
                parse_mode="HTML"
            )
            return
        
        # Clear state and remove from workaround set
        await state.clear()
        _users_waiting_for_custom_range.discard(user_id)
        logger.info(f"User {user_id} removed from waiting set")
        
        # Get user's time window (default to 6 hours)
        time_window_hours = _user_time_windows.get(user_id, 6.0)
        
        # Convert to decimal
        min_price = min_pct / 100.0
        max_price = max_pct / 100.0
        
        # Show analyzing message
        analyzing_msg = await message.answer(
            f"🔍 <b>Analyzing {min_pct}-{max_pct}% markets...</b>\n\n"
            f"⏰ Time window: <b>{int(time_window_hours)}h</b>\n"
            f"⏳ Fetching data from Polymarket\n"
            f"📊 Custom range selected\n"
            f"⚡ Using multithreading\n\n"
            f"<i>Please wait 10-20 seconds...</i>",
            parse_mode="HTML"
        )
        
        # Run analyzer with custom range and time window
        logger.info(f"User requested custom range: {min_pct}-{max_pct}% in next {time_window_hours}h")
        suggestions = run_analysis(
            max_suggestions=5, 
            min_price=min_price, 
            max_price=max_price,
            time_window_hours=time_window_hours
        )
        logger.info(f"✅ Analyzer completed - generated {len(suggestions)} suggestions")
        
        # Delete analyzing message
        try:
            await analyzing_msg.delete()
        except Exception:
            pass
        
        if not suggestions:
            logger.info("❌ No suggestions generated")
            await message.answer(
                f"📭 <b>No suggestions found</b>\n\n"
                f"No markets in the <b>{min_pct}-{max_pct}%</b> range were found.\n\n"
                f"💡 Try a different range:\n"
                f"• Use /suggest to try again\n"
                f"• Try a wider range (e.g., 40-60%)\n\n"
                f"📊 Use /balance to check your portfolio",
                parse_mode="HTML"
            )
            return
        
        # Send suggestions
        logger.info(f"📤 Sending {len(suggestions)} suggestions to user...")
        db = get_client()
        sent_count = 0
        
        for i, s in enumerate(suggestions, 1):
            try:
                snap = db.collection("suggestions").where("tokenId", "==", s.get("tokenId", "")).where("status", "==", "OPEN").limit(1).get()
                if snap:
                    doc = snap[0]
                    text = suggestion_message(
                        s.get("title", ""), 
                        s.get("side", ""), 
                        s.get("yesProbability", 0.5), 
                        s.get("noProbability", 0.5),
                        s.get("endDate", None)
                    )
                    kb = amount_presets_kb(suggestion_id=doc.id, token_id=s.get("tokenId", ""), side=s.get("side", ""))
                    await message.answer(text, reply_markup=kb, parse_mode="HTML")
                    sent_count += 1
                    logger.info(f"✅ Sent suggestion {i}/{len(suggestions)}")
            except Exception as send_err:
                logger.error(f"❌ Error sending suggestion {i}: {send_err}")
        
        logger.info(f"✅ Finished sending {sent_count}/{len(suggestions)} suggestions to user")
        
    except Exception as e:
        logger.error(f"Error processing custom range: {e}")
        await message.answer(
            f"⚠️ <b>Error</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Please try /suggest again.",
            parse_mode="HTML"
        )
        await state.clear()
        # Clean up workaround set on error
        user_id = message.from_user.id
        _users_waiting_for_custom_range.discard(user_id)


@dp.callback_query(lambda c: c.data and c.data.startswith("amt:"))
async def on_amount_select(callback: types.CallbackQuery) -> None:
    try:
        if not callback.data:
            await callback.answer("❌ Invalid selection data")
            return
            
        parts = callback.data.split(":")
        if len(parts) < 3:
            await callback.answer("❌ Invalid selection data")
            return
            
        suggestion_id = parts[1]
        size_str = parts[2]
        
        # Handle custom amount (not implemented yet)
        if size_str == "custom":
            await callback.answer("⚠️ Custom amount not yet implemented", show_alert=True)
            return
        
        size = float(size_str)
        
        # Fetch suggestion from Firestore to get all details
        db = get_client()
        suggestion_doc = db.collection("suggestions").document(suggestion_id).get()
        
        if not suggestion_doc.exists:
            await callback.answer("❌ Suggestion not found or expired", show_alert=True)
            return
        
        suggestion = suggestion_doc.to_dict()
        token_id = suggestion.get("tokenId", "")
        side = suggestion.get("side", "BUY_YES")
        price = suggestion.get("price", 0.5)
        
        side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
        confirm_msg = (
            f"{side_emoji} <b>Confirm Trade</b>\n\n"
            f"Market: {suggestion.get('title', 'N/A')[:60]}\n"
            f"Side: {side.upper()}\n"
            f"Size: {size} contracts\n"
            f"Price: ${price:.4f}\n"
            f"Total: ${size * price:.2f}\n\n"
            f"Ready to place this order?"
        )
        
        kb = confirm_kb(suggestion_id, token_id, side, price, size)
        await callback.message.edit_text(confirm_msg, reply_markup=kb, parse_mode="HTML")  # type: ignore
        await callback.answer()
    except ValueError:
        await callback.answer("⚠️ Invalid amount format", show_alert=True)
    except Exception as e:
        await callback.answer(f"⚠️ Error: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data == "cancel")
async def on_cancel(callback: types.CallbackQuery) -> None:
    await callback.message.delete()  # type: ignore
    await callback.answer("❌ Cancelled", show_alert=False)


@dp.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: types.CallbackQuery) -> None:
    """Handle trade confirmation with comprehensive error handling."""
    loading_msg_sent = False
    
    try:
        # Validate callback data
        if not callback.data:
            await callback.answer("❌ Invalid confirmation data", show_alert=True)
            logger.error("Confirm callback received with no data")
            return
            
        parts = callback.data.split(":")
        if len(parts) < 3:
            await callback.answer("❌ Invalid confirmation format", show_alert=True)
            logger.error(f"Invalid confirm format: {callback.data}")
            return
        
        # Parse parameters
        try:
            suggestion_id = parts[1]
            size = float(parts[2])
            
            if size <= 0:
                raise ValueError("Size must be positive")
                
        except (ValueError, IndexError) as e:
            await callback.answer("❌ Invalid trade size", show_alert=True)
            logger.error(f"Error parsing trade parameters: {e}")
            return
        
        # Show loading message
        try:
            await callback.answer("⏳ Processing...")
            await callback.message.edit_text(
                "⏳ <b>Processing Trade...</b>\n\n"
                "🔄 Connecting to Polymarket\n"
                "📊 Validating order details\n"
                "💰 Preparing transaction\n\n"
                "<i>Please wait...</i>",
                parse_mode="HTML"
            )
            loading_msg_sent = True
        except Exception as e:
            logger.error(f"Error showing loading message: {e}")
            # Continue anyway
        
        # Fetch suggestion from Firestore
        try:
            db = get_client()
            suggestion_doc = db.collection("suggestions").document(suggestion_id).get()
            
            if not suggestion_doc.exists:
                error_msg = (
                    "❌ <b>Suggestion Not Found</b>\n\n"
                    "This trade suggestion has expired or been removed.\n\n"
                    "💡 Use /suggest to get fresh opportunities!"
                )
                if loading_msg_sent:
                    await callback.message.edit_text(error_msg, parse_mode="HTML")
                else:
                    await callback.message.answer(error_msg, parse_mode="HTML")
                return
                
            suggestion = suggestion_doc.to_dict()
            
        except Exception as e:
            logger.error(f"Error fetching suggestion from Firestore: {e}")
            error_msg = (
                "❌ <b>Database Error</b>\n\n"
                f"Could not retrieve trade details.\n\n"
                f"<code>{str(e)}</code>\n\n"
                "💡 Try again in a few moments."
            )
            if loading_msg_sent:
                await callback.message.edit_text(error_msg, parse_mode="HTML")
            else:
                await callback.message.answer(error_msg, parse_mode="HTML")
            return
        
        # Validate suggestion data
        token_id = suggestion.get("tokenId", "")
        side = suggestion.get("side", "BUY_YES")
        price = suggestion.get("price", 0.5)
        
        if not token_id:
            error_msg = (
                "❌ <b>Invalid Suggestion Data</b>\n\n"
                "Missing token ID. This suggestion may be corrupted.\n\n"
                "💡 Use /suggest to get new opportunities."
            )
            if loading_msg_sent:
                await callback.message.edit_text(error_msg, parse_mode="HTML")
            else:
                await callback.message.answer(error_msg, parse_mode="HTML")
            return
        
        # Place the trade
        try:
            user_chat_id = callback.from_user.id
            logger.info(f"Placing trade: suggestion={suggestion_id}, size={size}, user={user_chat_id}")
            
            result = place_trade(suggestion_id, token_id, side, price, size, user_chat_id)
            
            logger.info(f"Trade result: {result}")
            
        except Exception as e:
            logger.error(f"Error in place_trade: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            error_msg = (
                f"❌ <b>Trade Execution Error</b>\n\n"
                f"<code>{str(e)}</code>\n\n"
                f"💡 <b>Possible causes:</b>\n"
                f"• Wallet not configured\n"
                f"• Insufficient balance\n"
                f"• Market closed/paused\n"
                f"• Network connectivity issue\n\n"
                f"📧 Contact support if this persists."
            )
            if loading_msg_sent:
                await callback.message.edit_text(error_msg, parse_mode="HTML")
            else:
                await callback.message.answer(error_msg, parse_mode="HTML")
            return
        
        # Handle trade result
        if result.get("status") == "OPEN":
            side_emoji = "📈" if side.upper().startswith("BUY") else "📉"
            success_msg = (
                f"✅ <b>Trade Placed Successfully!</b>\n\n"
                f"Market: {suggestion.get('title', 'N/A')[:60]}\n"
                f"{side_emoji} Side: {side.upper()}\n"
                f"📊 Size: {size} contracts\n"
                f"💵 Price: ${price:.4f}\n"
                f"💰 Total: ${size * price:.2f}\n\n"
                f"🆔 Trade ID: <code>{result.get('trade_id', 'N/A')}</code>\n\n"
                f"✨ Your order is now live on Polymarket!"
            )
            await callback.message.edit_text(success_msg, parse_mode="HTML")
            
        elif result.get("status") == "FAILED":
            error_detail = result.get("error", "Unknown error")
            fail_msg = (
                f"❌ <b>Trade Failed</b>\n\n"
                f"<code>{error_detail}</code>\n\n"
                f"💡 <b>What to check:</b>\n"
                f"• Wallet balance\n"
                f"• Market still open\n"
                f"• Price hasn't changed drastically\n\n"
                f"Try /suggest for new opportunities."
            )
            await callback.message.edit_text(fail_msg, parse_mode="HTML")
            
        else:
            # Unknown status
            status = result.get('status', 'UNKNOWN')
            unknown_msg = (
                f"⚠️ <b>Unknown Trade Status</b>\n\n"
                f"Status: <code>{status}</code>\n\n"
                f"The trade may or may not have executed.\n"
                f"Please check your /balance to verify.\n\n"
                f"📧 Contact support with this info."
            )
            await callback.message.edit_text(unknown_msg, parse_mode="HTML")
            
    except Exception as e:
        # Catch-all for any unexpected errors
        logger.error(f"Unexpected error in on_confirm: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        try:
            error_msg = (
                f"❌ <b>Unexpected Error</b>\n\n"
                f"<code>{str(e)[:200]}</code>\n\n"
                f"💡 <b>Troubleshooting:</b>\n"
                f"• Try /balance to check your account\n"
                f"• Use /suggest for new opportunities\n"
                f"• Wait a moment and try again\n\n"
                f"📧 Contact support if this persists."
            )
            
            if loading_msg_sent:
                await callback.message.edit_text(error_msg, parse_mode="HTML")
            else:
                await callback.message.answer(error_msg, parse_mode="HTML")
        except Exception as nested_e:
            logger.error(f"Error sending error message: {nested_e}")
            # Last resort - try simple callback answer
            try:
                await callback.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
            except Exception:
                pass


@dp.message()
async def handle_unknown(message: types.Message, state: FSMContext) -> None:
    """Handle unknown commands and messages.
    
    Note: This is a catch-all handler, so it should ignore messages
    when the user is in an FSM state (e.g., entering custom range).
    """
    user_id = message.from_user.id
    
    # Check workaround sets first (for webhook mode)
    if user_id in _users_waiting_for_time_window:
        logger.info(f"User {user_id} is waiting for custom time window, skipping unknown handler")
        await process_custom_time_window(message, state)
        return
    
    if user_id in _users_waiting_for_custom_range:
        logger.info(f"User {user_id} is waiting for custom range, skipping unknown handler")
        # User is waiting for custom range input, let the state handler process it
        # Forward to process_custom_range directly
        await process_custom_range(message, state)
        return
    
    # Check if user is in any state - if so, don't handle (let state handler process it)
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(f"User {user_id} is in state {current_state}, skipping unknown handler")
        # User is in a state, this message should be handled by the state handler
        return
    
    await message.answer(
        f"❓ <b>Command not found</b>\n\n"
        f"I don't understand that command.\n\n"
        f"<b>Available commands:</b>\n"
        f"• /balance - View your portfolio\n"
        f"• /suggest - Get trade suggestions\n\n"
        f"💡 Try one of these commands!",
        parse_mode="HTML"
    )


@app.post("/webhook")
async def telegram_webhook(req: Request) -> dict[str, bool]:
    try:
        data = await req.json()
        update = types.Update.model_validate(data)
        bot = get_bot()
        
        # Process the update through the dispatcher with storage
        await dp.feed_update(bot=bot, update=update)
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"ok": False}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

