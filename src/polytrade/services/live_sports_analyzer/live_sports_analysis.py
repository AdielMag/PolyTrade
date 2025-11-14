from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from loguru import logger

from ...shared.balances import get_current
from ...shared.config import settings
from ...shared.firestore import add_doc
from ...shared.polymarket_client import PolymarketClient

# Optional import for bot_b notifications
try:
    from aiogram import Bot
    from ...shared.config import settings as bot_settings
    BOT_B_AVAILABLE = True
    logger.info("✅ bot_b dependencies imported successfully")
except ImportError as e:
    BOT_B_AVAILABLE = False
    logger.warning(f"⚠️  bot_b not available (aiogram not installed) - notifications will be skipped: {e}")


async def _send_notification_direct(chat_id: int, text: str) -> None:
    """Send notification directly without balance header to avoid Firestore dependency.
    
    Args:
        chat_id: Telegram chat ID
        text: Message text (HTML formatted)
    """
    bot = None
    try:
        if not bot_settings.bot_b_token:
            raise RuntimeError("TELEGRAM_BOT_B_TOKEN is not set")
        
        bot = Bot(token=bot_settings.bot_b_token)
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send direct notification: {e}")
        raise
    finally:
        # Always close the bot session to prevent hanging
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass


def fetch_markets_page(offset: int, limit: int, sports_tag_ids: set[str]) -> list[dict[str, Any]]:
    """Fetch a single page of markets from Polymarket API.
    
    Args:
        offset: Pagination offset
        limit: Number of results per page
        sports_tag_ids: Set of sports tag IDs to filter by
        
    Returns:
        List of sports markets from this page
    """
    try:
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "closed": "false",  # Only active markets
            "limit": limit,
            "offset": offset,
            "order": "volume24hr",  # Sort by trading volume
            "ascending": "false"  # Highest volume first
        }
        
        logger.debug(f"Fetching page at offset {offset} (limit={limit})")
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        all_markets = response.json()
        
        if not all_markets:
            logger.debug(f"Page at offset {offset} returned 0 markets (end of results)")
            return []
        
        logger.debug(f"Page at offset {offset} returned {len(all_markets)} markets")
        
        # Filter for sports markets only
        sports_keywords = [
            "vs", "vs.", "football", "basketball", "baseball", "soccer", "nfl", "nba", 
            "mlb", "nhl", "tennis", "golf", "boxing", "mma", "ufc", "cricket", 
            "rugby", "hockey", "ncaa", "college", "spread", "o/u", "over/under",
            "moneyline", "1h", "1st half", "playoff", "championship", "bowl",
            "game", "match", "series", "tournament"
        ]
        
        markets = []
        for market in all_markets:
            # Check if market has sports tag
            market_tags = market.get("tags", [])
            if isinstance(market_tags, list):
                has_sports_tag = any(
                    str(tag.get("id", "")) in sports_tag_ids 
                    for tag in market_tags 
                    if isinstance(tag, dict)
                )
                if has_sports_tag:
                    markets.append(market)
                    continue
            
            # Fallback: check question for sports keywords
            question = market.get("question", "").lower()
            if any(keyword in question for keyword in sports_keywords):
                markets.append(market)
        
        logger.debug(f"Page at offset {offset}: {len(markets)} sports markets after filtering")
        return markets
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching page at offset {offset}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching page at offset {offset}: {e}")
        return []


def fetch_all_sports_markets(max_workers: int = 10) -> list[dict[str, Any]]:
    """Fetch ALL sports markets from Polymarket using pagination and multithreading.
    
    Args:
        max_workers: Number of concurrent threads for fetching pages
        
    Returns:
        List of all sports markets
    """
    logger.info("=" * 80)
    logger.info("FETCHING ALL SPORTS MARKETS FROM POLYMARKET")
    logger.info("=" * 80)
    
    # First, get sports tag IDs
    logger.info("Fetching sports tag information...")
    sports_tag_ids = set()
    try:
        sports_url = "https://gamma-api.polymarket.com/sports"
        sports_response = httpx.get(sports_url, timeout=10.0)
        sports_response.raise_for_status()
        sports_data = sports_response.json()
        
        if isinstance(sports_data, list):
            for sport in sports_data:
                if "id" in sport:
                    sports_tag_ids.add(str(sport["id"]))
        
        logger.info(f"✅ Found {len(sports_tag_ids)} sports tag IDs")
    except Exception as e:
        logger.warning(f"Could not fetch sports tags, will filter by keywords only: {e}")
    
    # Strategy: Fetch first page to estimate total, then fetch all pages in parallel
    limit = 100  # Results per page
    
    logger.info(f"Fetching first page to estimate total markets...")
    first_page = fetch_markets_page(0, limit, sports_tag_ids)
    
    if not first_page:
        logger.warning("First page returned 0 markets, no data to fetch")
        return []
    
    logger.info(f"First page returned {len(first_page)} sports markets")
    
    # Estimate total pages (we'll fetch until we get empty results)
    # Polymarket typically has 2000-5000 markets, so ~20-50 pages
    estimated_pages = 50  # Fetch up to 50 pages (5000 markets)
    
    logger.info(f"Using multithreading to fetch up to {estimated_pages} pages concurrently...")
    logger.info(f"Workers: {max_workers} | Page size: {limit}")
    
    all_markets = [first_page]  # Start with first page
    
    # Fetch remaining pages in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit page fetch tasks (start from page 1 since we have page 0)
        future_to_page = {
            executor.submit(fetch_markets_page, page * limit, limit, sports_tag_ids): page
            for page in range(1, estimated_pages)
        }
        
        completed = 0
        for future in as_completed(future_to_page):
            completed += 1
            page_num = future_to_page[future]
            
            if completed % 10 == 0:
                logger.info(f"Progress: {completed}/{len(future_to_page)} pages fetched")
            
            try:
                page_markets = future.result()
                if page_markets:
                    all_markets.append(page_markets)
                else:
                    # Empty page means we've reached the end
                    logger.debug(f"Page {page_num} empty, reached end of results")
            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
    
    # Flatten the list of lists
    flattened_markets = []
    for page_markets in all_markets:
        flattened_markets.extend(page_markets)
    
    logger.info("=" * 80)
    logger.info(f"✅ TOTAL SPORTS MARKETS FETCHED: {len(flattened_markets)}")
    logger.info("=" * 80)
    
    return flattened_markets


def filter_live_markets(markets: list[dict[str, Any]], lookback_hours: float = 4.0) -> list[dict[str, Any]]:
    """Filter markets to only include live games (games that have started).
    
    Args:
        markets: List of all markets
        lookback_hours: How many hours back to include (games started within this window)
        
    Returns:
        List of live markets only
    """
    logger.info("=" * 80)
    logger.info("FILTERING FOR LIVE MARKETS (games that have started)")
    logger.info("=" * 80)
    
    now_dt = datetime.now(timezone.utc)
    lookback_time = now_dt - timedelta(hours=lookback_hours)
    
    logger.info(f"⏰ Current time: {now_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"⏰ Lookback window: {lookback_hours}h (games started after {lookback_time.strftime('%Y-%m-%d %H:%M UTC')})")
    
    live_markets = []
    
    for market in markets:
        # Prefer gameStartTime/eventStartTime over endDate
        start_time_str = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        
        if start_time_str:
            try:
                # Parse ISO format
                if isinstance(start_time_str, str):
                    if ' ' in start_time_str and '+' in start_time_str:
                        start_dt = datetime.fromisoformat(start_time_str.replace('+00', '+00:00'))
                    else:
                        start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                else:
                    start_dt = start_time_str
                
                # Calculate time since start
                time_diff = (now_dt - start_dt).total_seconds()
                hours_since_start = time_diff / 3600
                
                # Include if game started (negative time until start = positive time since start)
                # and within lookback window
                if 0 < hours_since_start <= lookback_hours:
                    market['_hours_since_start'] = hours_since_start
                    market['_start_time'] = start_dt
                    live_markets.append(market)
                    logger.debug(f"🔴 LIVE: {market.get('question', '')[:60]} (started {hours_since_start:.1f}h ago)")
                    
            except Exception as e:
                logger.debug(f"Skipped market due to date parse error: {e}")
                continue
    
    # Sort by most recent (games that started most recently first)
    live_markets.sort(key=lambda m: m.get('_hours_since_start', float('inf')))
    
    logger.info("=" * 80)
    logger.info(f"✅ FOUND {len(live_markets)} LIVE MARKETS")
    logger.info(f"❌ Filtered out {len(markets) - len(live_markets)} non-live markets")
    logger.info("=" * 80)
    
    return live_markets


def fetch_market_pricing(market: dict[str, Any], client: PolymarketClient) -> dict[str, Any]:
    """Fetch pricing data for all outcomes in a market.
    
    Args:
        market: Market data
        client: PolymarketClient instance
        
    Returns:
        Dictionary with pricing data for each outcome
    """
    pricing_data = {}
    
    clob_token_ids = market.get("clobTokenIds", [])
    if isinstance(clob_token_ids, str):
        import json
        clob_token_ids = json.loads(clob_token_ids)
    
    outcomes = market.get("outcomes", ["YES", "NO"])
    # Parse outcomes if it's a JSON string
    if isinstance(outcomes, str):
        import json
        try:
            outcomes = json.loads(outcomes)
        except:
            # If not valid JSON, try to extract from string format
            # Sometimes it might be like '["Ireland win", "Draw", "Portugal win"]'
            pass
    if not isinstance(outcomes, list):
        outcomes = ["YES", "NO"]
    
    for i, token_id in enumerate(clob_token_ids):
        try:
            # Get order book quotes
            quotes = client.get_quotes(token_id)
            outcome_name = outcomes[i] if i < len(outcomes) else f"Option_{i+1}"
            
            # Also try to get current price from /price endpoint (more accurate)
            current_buy_price = client.get_price(token_id, "BUY")
            current_sell_price = client.get_price(token_id, "SELL")
            
            # Use /price endpoint if available, otherwise use order book
            best_ask = current_buy_price if current_buy_price > 0 else quotes["best_ask"]
            best_bid = current_sell_price if current_sell_price > 0 else quotes["best_bid"]
            
            pricing_data[outcome_name] = {
                "token_id": token_id,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0.0,
                "source": "price_endpoint" if current_buy_price > 0 else "order_book"
            }
        except Exception as e:
            logger.debug(f"Could not fetch pricing for token {token_id}: {e}")
            outcome_name = outcomes[i] if i < len(outcomes) else f"Option_{i+1}"
            pricing_data[outcome_name] = {
                "token_id": token_id,
                "best_bid": 0.0,
                "best_ask": 0.0,
                "spread": 0.0
            }
            
            # Rate limit handling
            if "429" in str(e):
                time.sleep(0.1)
    
    return pricing_data


def log_market_details(market: dict[str, Any], index: int, total: int, client: PolymarketClient) -> None:
    """Log comprehensive details for a live market.
    
    Args:
        market: Market data
        index: Market index (for display)
        total: Total number of markets
        client: PolymarketClient instance
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"LIVE MARKET #{index}/{total}")
    logger.info("=" * 80)
    
    # Basic info
    question = market.get("question", "N/A")
    condition_id = market.get("condition_id", "N/A")
    
    logger.info(f"📊 TITLE: {question}")
    logger.info(f"🔑 Condition ID: {condition_id}")
    
    # Status
    closed = market.get("closed", False)
    accepting_orders = market.get("acceptingOrders", False)
    active = market.get("active", False)
    
    status_parts = []
    if closed:
        status_parts.append("❌ CLOSED")
    if accepting_orders:
        status_parts.append("✅ ACCEPTING ORDERS")
    if active:
        status_parts.append("🟢 ACTIVE")
    
    status_str = " | ".join(status_parts) if status_parts else "⚠️ Unknown"
    logger.info(f"📍 STATUS: {status_str}")
    
    # Timing
    hours_since_start = market.get("_hours_since_start", 0)
    start_time = market.get("_start_time")
    if start_time:
        logger.info(f"⏰ STARTED: {start_time.strftime('%Y-%m-%d %H:%M UTC')} ({hours_since_start:.1f}h ago)")
    
    # Market metrics
    liquidity = float(market.get("liquidityClob", 0.0))
    volume_24h = float(market.get("volume24hr", 0.0))
    volume = float(market.get("volume", 0.0))
    
    logger.info(f"💧 LIQUIDITY: ${liquidity:,.2f}")
    logger.info(f"📈 VOLUME (24h): ${volume_24h:,.2f}")
    logger.info(f"📈 VOLUME (total): ${volume:,.2f}")
    
    # Outcomes
    outcomes = market.get("outcomes", [])
    clob_token_ids = market.get("clobTokenIds", [])
    
    if isinstance(clob_token_ids, str):
        import json
        clob_token_ids = json.loads(clob_token_ids)
    
    logger.info(f"🎯 OUTCOMES: {len(outcomes)} options")
    for i, outcome in enumerate(outcomes):
        token_id = clob_token_ids[i] if i < len(clob_token_ids) else "N/A"
        logger.info(f"   {i+1}. {outcome} (Token: {token_id})")
    
    # Fetch and log pricing data
    logger.info("")
    logger.info("💰 PRICING DATA (Order Book):")
    logger.info("-" * 80)
    
    pricing_data = fetch_market_pricing(market, client)
    
    for outcome_name, pricing in pricing_data.items():
        bid = pricing["best_bid"]
        ask = pricing["best_ask"]
        spread = pricing["spread"]
        
        logger.info(f"   {outcome_name}:")
        logger.info(f"      Best Bid: ${bid:.4f} ({bid*100:.2f}%)")
        logger.info(f"      Best Ask: ${ask:.4f} ({ask*100:.2f}%)")
        logger.info(f"      Spread:   ${spread:.4f} ({spread*100:.2f}%)")
    
    # Additional metadata
    neg_risk = market.get("negRisk", False)
    if neg_risk:
        logger.info("⚠️  NegRisk market (multiple outcomes)")
    
    tags = market.get("tags", [])
    if tags:
        tag_names = [tag.get("label", tag.get("id", "")) for tag in tags if isinstance(tag, dict)]
        logger.info(f"🏷️  TAGS: {', '.join(tag_names[:5])}")  # Show first 5 tags
    
    logger.info("=" * 80)


def has_existing_position(condition_id: str, market_title: str, balance: dict[str, Any]) -> bool:
    """Check if user already has a position in this market.
    
    Args:
        condition_id: Market condition ID
        market_title: Market question/title
        balance: Balance dict with positions list
        
    Returns:
        True if position exists, False otherwise
    """
    positions = balance.get("positions", [])
    if not positions:
        return False
    
    # Check each position for matching market
    for position in positions:
        pos_title = position.get("title", "")
        # Match by title (most reliable) or condition_id if available
        if pos_title and market_title:
            # Normalize titles for comparison (case-insensitive, strip whitespace)
            if pos_title.strip().lower() == market_title.strip().lower():
                logger.debug(f"Found existing position in market: {market_title[:60]}")
                return True
    
    return False


def buy_market_outcomes(
    market: dict[str, Any],
    pricing_data: dict[str, Any],
    min_ask_price: float,
    max_ask_price: float,
    client: PolymarketClient,
    balance: dict[str, Any],
    trading_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Buy 1 share for each outcome in the market that has ask price in target range.
    
    Args:
        market: Market data dictionary
        pricing_data: Pricing data for all outcomes (from fetch_market_pricing)
        min_ask_price: Minimum ask price (0-1)
        max_ask_price: Maximum ask price (0-1)
        client: Authenticated PolymarketClient
        balance: Current balance dict
        trading_results: List to append trade results to
        
    Returns:
        List of trade results (one per outcome attempted)
    """
    market_title = market.get("question", "Unknown Market")
    condition_id = market.get("condition_id", "")
    neg_risk = market.get("negRisk", False) or market.get("negRiskMarketID") is not None
    
    # Check if user already has position in this market
    if has_existing_position(condition_id, market_title, balance):
        logger.info(f"⏭️  Skipping {market_title[:60]}... - already have position")
        _send_trading_notification_sync(
            f"⏭️ <b>Skipped Market</b>\n\n"
            f"📊 {market_title[:100]}\n\n"
            f"Reason: Already have position in this market"
        )
        return trading_results
    
    # Get outcomes list
    outcomes = market.get("outcomes", ["YES", "NO"])
    if isinstance(outcomes, str):
        import json
        try:
            outcomes = json.loads(outcomes)
        except:
            outcomes = ["YES", "NO"]
    if not isinstance(outcomes, list):
        outcomes = ["YES", "NO"]
    
    # Find all outcomes with ask price in target range
    outcomes_to_buy = []
    for outcome_name, outcome_data in pricing_data.items():
        ask_price = outcome_data.get("best_ask", 0.0)
        token_id = outcome_data.get("token_id", "")
        
        if ask_price > 0 and min_ask_price <= ask_price <= max_ask_price:
            if token_id:
                outcomes_to_buy.append({
                    "outcome_name": outcome_name,
                    "token_id": token_id,
                    "ask_price": ask_price,
                    "cost": ask_price * 1.0  # 1 share
                })
    
    if not outcomes_to_buy:
        logger.debug(f"No outcomes in price range for {market_title[:60]}")
        return trading_results
    
    logger.info("")
    logger.info(f"💰 ATTEMPTING TO BUY {len(outcomes_to_buy)} OUTCOME(S) IN MARKET:")
    logger.info(f"   {market_title[:80]}")
    logger.info(f"   Condition ID: {condition_id}")
    
    # Buy each qualifying outcome
    for outcome_info in outcomes_to_buy:
        outcome_name = outcome_info["outcome_name"]
        token_id = outcome_info["token_id"]
        ask_price = outcome_info["ask_price"]
        cost = outcome_info["cost"]
        
        # Check available balance
        available_usd = balance.get("available_usd", 0.0)
        if available_usd < cost:
            logger.warning(f"❌ Insufficient balance: need ${cost:.4f}, have ${available_usd:.2f}")
            _send_trading_notification_sync(
                f"❌ <b>Buy Failed</b>\n\n"
                f"📊 {market_title[:100]}\n"
                f"🎯 Outcome: {outcome_name}\n"
                f"💰 Cost: ${cost:.4f}\n\n"
                f"Reason: Insufficient balance (have ${available_usd:.2f})"
            )
            trading_results.append({
                "market": market_title,
                "outcome": outcome_name,
                "status": "FAILED",
                "reason": "insufficient_balance",
                "cost": cost,
                "available": available_usd
            })
            continue
        
        # Construct side parameter
        if outcome_name.upper() in ["YES", "NO"]:
            side = f"BUY_{outcome_name.upper()}"
        else:
            # For multi-outcome markets, use outcome name
            side = f"BUY_{outcome_name.upper().replace(' ', '_')}"
        
        # Log buy attempt
        logger.info("")
        logger.info(f"🛒 ATTEMPTING BUY:")
        logger.info(f"   Market: {market_title[:80]}")
        logger.info(f"   Outcome: {outcome_name}")
        logger.info(f"   Token ID: {token_id}")
        logger.info(f"   Side: {side}")
        logger.info(f"   Price: ${ask_price:.4f} ({ask_price*100:.2f}%)")
        logger.info(f"   Size: 1.0 share")
        logger.info(f"   Cost: ${cost:.4f}")
        logger.info(f"   Available balance: ${available_usd:.2f}")
        logger.info(f"   NegRisk: {neg_risk}")
        
        # Send notification before buy attempt
        _send_trading_notification_sync(
            f"🛒 <b>Attempting Buy</b>\n\n"
            f"📊 {market_title[:100]}\n"
            f"🎯 Outcome: {outcome_name}\n"
            f"💰 Price: ${ask_price:.4f} ({ask_price*100:.2f}%)\n"
            f"💵 Cost: ${cost:.4f}\n"
            f"💳 Balance: ${available_usd:.2f}"
        )
        
        # Add delay to avoid rate limiting
        delay = 1.5  # 1.5 second delay between orders
        logger.info(f"⏳ Waiting {delay}s before placing order...")
        time.sleep(delay)
        
        # Place order
        try:
            logger.info(f"📤 Placing order...")
            order_result = client.place_order(
                token_id=token_id,
                side=side,
                price=ask_price,
                size=1.0,
                neg_risk=neg_risk
            )
            
            # Check if order was successful
            if order_result.get("ok"):
                order_id = order_result.get("resp", {}).get("id", "unknown")
                logger.info(f"✅ BUY SUCCESSFUL!")
                logger.info(f"   Order ID: {order_id}")
                logger.info(f"   Cost: ${cost:.4f}")
                
                # Update balance (approximate - will be accurate on next fetch)
                balance["available_usd"] = available_usd - cost
                
                # Save trade to Firestore
                try:
                    trade_data = {
                        "suggestionId": None,  # Auto-trade, no suggestion
                        "tokenId": token_id,
                        "marketId": condition_id,
                        "title": market_title,
                        "side": side,
                        "size": 1.0,
                        "entryPx": ask_price,
                        "status": "OPEN",
                        "pnl": 0.0,
                        "slPct": settings.default_sl_pct,
                        "tpPct": settings.default_tp_pct,
                        "userChatId": settings.bot_b_default_chat_id,
                        "createdAt": int(time.time()),
                        "closedAt": None,
                    }
                    trade_id = add_doc("trades", trade_data)
                    logger.info(f"💾 Trade saved to Firestore: {trade_id}")
                    
                    # Create event
                    add_doc("events", {
                        "tradeId": trade_id,
                        "type": "CREATED",
                        "message": f"Auto-trade: Bought 1 share of {outcome_name} at ${ask_price:.4f}",
                        "createdAt": int(time.time())
                    })
                except Exception as e:
                    error_str = str(e)
                    if "credentials" in error_str.lower() or "authentication" in error_str.lower():
                        logger.error(f"❌ Failed to save trade to Firestore: GCP credentials not configured")
                        logger.error(f"   To fix: Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
                        logger.error(f"   Or run: gcloud auth application-default login")
                    else:
                        logger.error(f"❌ Failed to save trade to Firestore: {e}")
                
                # Send success notification
                _send_trading_notification_sync(
                    f"✅ <b>Buy Successful</b>\n\n"
                    f"📊 {market_title[:100]}\n"
                    f"🎯 Outcome: {outcome_name}\n"
                    f"💰 Cost: ${cost:.4f}\n"
                    f"🆔 Order ID: {order_id}\n"
                    f"💳 Remaining: ${balance['available_usd']:.2f}"
                )
                
                trading_results.append({
                    "market": market_title,
                    "outcome": outcome_name,
                    "status": "SUCCESS",
                    "order_id": order_id,
                    "cost": cost,
                    "remaining_balance": balance["available_usd"]
                })
            else:
                error_msg = order_result.get("resp", {}).get("error", "Unknown error")
                logger.error(f"❌ BUY FAILED: {error_msg}")
                _send_trading_notification_sync(
                    f"❌ <b>Buy Failed</b>\n\n"
                    f"📊 {market_title[:100]}\n"
                    f"🎯 Outcome: {outcome_name}\n\n"
                    f"Reason: {error_msg}"
                )
                trading_results.append({
                    "market": market_title,
                    "outcome": outcome_name,
                    "status": "FAILED",
                    "reason": error_msg,
                    "cost": cost
                })
        except Exception as e:
            error_str = str(e)
            logger.error(f"❌ BUY EXCEPTION: {error_str}")
            
            # Check for Cloudflare blocks
            if "cloudflare" in error_str.lower() or "403" in error_str or "attention required" in error_str.lower():
                reason = "Cloudflare block - too many requests"
            else:
                reason = error_str[:200]  # Truncate long errors
            
            _send_trading_notification_sync(
                f"❌ <b>Buy Failed</b>\n\n"
                f"📊 {market_title[:100]}\n"
                f"🎯 Outcome: {outcome_name}\n\n"
                f"Reason: {reason}"
            )
            
            trading_results.append({
                "market": market_title,
                "outcome": outcome_name,
                "status": "FAILED",
                "reason": reason,
                "cost": cost
            })
    
    return trading_results


def format_markets_notification(found_markets: list[dict[str, Any]]) -> str:
    """Format markets data into a Telegram notification message.
    
    Args:
        found_markets: List of market summary dictionaries
        
    Returns:
        HTML-formatted message string
    """
    if not found_markets:
        return (
            "🔍 <b>Live Sports Analysis</b>\n\n"
            "No markets found matching criteria:\n"
            "• Liquidity > $500\n"
            "• Ask price 93-96%\n"
            "• Live games"
        )
    
    message_parts = [
        f"🔍 <b>Live Sports Markets Found</b>\n",
        f"📊 Found <b>{len(found_markets)}</b> markets matching criteria\n\n"
    ]
    
    # Limit to top 10 markets to avoid message length limits
    markets_to_show = found_markets[:10]
    
    for i, market in enumerate(markets_to_show, 1):
        title = market.get("title", "Unknown Market")
        liquidity = market.get("liquidity", 0)
        volume = market.get("volume", 0)
        outcomes_info = market.get("outcomes_info", [])
        
        message_parts.append(f"<b>{i}. {title}</b>\n")
        
        if outcomes_info:
            for outcome_name, prob, price in outcomes_info:
                message_parts.append(f"   • {outcome_name}: <b>{prob:.2f}%</b> (${price:.4f})\n")
        
        message_parts.append(f"   💧 Liquidity: ${liquidity:,.2f}\n")
        message_parts.append(f"   📈 Volume: ${volume:,.2f}\n\n")
    
    if len(found_markets) > 10:
        message_parts.append(f"... and {len(found_markets) - 10} more markets\n")
    
    return "".join(message_parts)


def run_live_sports_analysis(
    max_workers: int = 10,
    lookback_hours: float = 4.0,
    min_liquidity: float = 500.0,
    min_ask_price: float = 0.93,
    max_ask_price: float = 0.96
) -> list[dict[str, Any]]:
    """Main function to analyze live sports markets on Polymarket.
    
    This function:
    1. Fetches ALL sports markets using pagination and multithreading
    2. Filters for LIVE markets (games that have started)
    3. Filters by liquidity and ask price criteria
    4. Logs comprehensive details including pricing, liquidity, and outcomes
    5. Sends Telegram notification via bot_b
    
    Args:
        max_workers: Number of concurrent threads for fetching
        lookback_hours: How many hours back to include live games
        min_liquidity: Minimum liquidity in USD (default: 500.0)
        min_ask_price: Minimum ask price (0-1, default: 0.93 for 93%)
        max_ask_price: Maximum ask price (0-1, default: 0.96 for 96%)
        
    Returns:
        List of filtered live sports markets with full details
    """
    logger.info("=" * 80)
    logger.info("🚀 LIVE SPORTS MARKET ANALYZER")
    logger.info("=" * 80)
    logger.info(f"Configuration:")
    logger.info(f"  - Max workers: {max_workers}")
    logger.info(f"  - Lookback window: {lookback_hours}h")
    logger.info(f"  - Min liquidity: ${min_liquidity:,.2f}")
    logger.info(f"  - Ask price range: {min_ask_price*100:.0f}%-{max_ask_price*100:.0f}%")
    logger.info("=" * 80)
    
    # Send notification that analysis is starting (in background thread to avoid blocking)
    logger.info("")
    logger.info("=" * 80)
    logger.info("📱 SENDING START NOTIFICATION (background)")
    logger.info("=" * 80)
    
    def send_start_notif_thread():
        try:
            _send_start_notification(max_workers, lookback_hours, min_liquidity, min_ask_price, max_ask_price)
        except Exception as e:
            logger.warning(f"⚠️  Start notification failed: {e}")
    
    notification_thread = threading.Thread(target=send_start_notif_thread, daemon=True)
    notification_thread.start()
    logger.info("📱 Start notification thread started (non-blocking)")
    
    start_time = time.time()
    
    # Step 1: Fetch all sports markets with pagination and multithreading
    all_sports_markets = fetch_all_sports_markets(max_workers=max_workers)
    
    if not all_sports_markets:
        logger.warning("No sports markets found!")
        logger.info("📱 Sending notification: No markets found")
        _send_notification_sync([])
        return []
    
    # Step 2: Filter for live markets only
    live_markets = filter_live_markets(all_sports_markets, lookback_hours=lookback_hours)
    
    if not live_markets:
        logger.warning("No live sports markets found!")
        logger.info(f"Total sports markets: {len(all_sports_markets)}, but none are currently live")
        logger.info("📱 Sending notification: No live markets found")
        # Send notification that no markets found
        _send_notification_sync([])
        return []
    
    # Step 3: Filter by liquidity and ask price
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"FILTERING {len(live_markets)} LIVE MARKETS BY LIQUIDITY AND ASK PRICE")
    logger.info("=" * 80)
    
    # Create client for pricing data (no auth needed for read-only)
    client = PolymarketClient(require_auth=False)
    
    found_markets_summary = []
    filtered_markets = []
    
    for market in live_markets:
        # Check liquidity filter
        liquidity = float(market.get("liquidityClob", 0))
        if liquidity < min_liquidity:
            continue
        
        # Check if market is live (has start time)
        hours_since = market.get('_hours_since_start', 0)
        market_start_time = market.get('_start_time')
        is_live = hours_since > 0 and market_start_time is not None
        
        if not is_live:
            continue
        
        # Fetch pricing and check ask price filter
        clob_token_ids = market.get("clobTokenIds", [])
        if isinstance(clob_token_ids, str):
            import json
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except:
                clob_token_ids = []
        
        if not clob_token_ids:
            continue
        
        try:
            pricing_data = fetch_market_pricing(market, client)
            if not pricing_data:
                continue
            
            # Check if any outcome has ask price in target range
            has_target_price = False
            outcomes_info = []
            best_ask_price = 0.0
            
            outcomes = market.get("outcomes", [])
            if isinstance(outcomes, str):
                import json
                try:
                    outcomes = json.loads(outcomes)
                except:
                    outcomes = []
            if not isinstance(outcomes, list):
                outcomes = []
            
            # Check each outcome's ask price
            for i, outcome in enumerate(outcomes):
                outcome_data = None
                outcome_key = None
                
                # Try to find pricing data for this outcome
                if outcome in pricing_data:
                    outcome_data = pricing_data[outcome]
                    outcome_key = outcome
                else:
                    # Case-insensitive match
                    for key in pricing_data.keys():
                        if str(key).upper() == str(outcome).upper():
                            outcome_data = pricing_data[key]
                            outcome_key = key
                            break
                
                # Match by index if name match failed
                if outcome_data is None and i < len(pricing_data):
                    pricing_keys = list(pricing_data.keys())
                    if i < len(pricing_keys):
                        outcome_key = pricing_keys[i]
                        outcome_data = pricing_data[outcome_key]
                
                if outcome_data:
                    ask = outcome_data.get("best_ask", 0)
                    if ask > 0:
                        prob = ask * 100
                        outcomes_info.append((outcome if outcome else outcome_key, prob, ask))
                        
                        # Check if in target range
                        if min_ask_price <= ask <= max_ask_price:
                            has_target_price = True
                        
                        if ask > best_ask_price:
                            best_ask_price = ask
            
            # If no outcomes matched by name/index, check all pricing data
            if not outcomes_info:
                for key, data in pricing_data.items():
                    ask = data.get("best_ask", 0)
                    if ask > 0:
                        prob = ask * 100
                        outcomes_info.append((key, prob, ask))
                        
                        if min_ask_price <= ask <= max_ask_price:
                            has_target_price = True
                        
                        if ask > best_ask_price:
                            best_ask_price = ask
            
            if has_target_price:
                # Market passed all filters - store pricing data for trading
                market["_pricing_data"] = pricing_data  # Store pricing data with market
                filtered_markets.append(market)
                found_markets_summary.append({
                    "title": market.get("question", "Unknown Market"),
                    "liquidity": liquidity,
                    "volume": float(market.get("volume24hr", 0)),
                    "outcomes_info": outcomes_info,
                    "best_ask_price": best_ask_price
                })
        
        except Exception as e:
            logger.debug(f"Error processing market {market.get('question', 'Unknown')}: {e}")
            continue
    
    # Step 4: Log detailed information for filtered markets
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"LOGGING DETAILS FOR {len(filtered_markets)} FILTERED MARKETS")
    logger.info("=" * 80)
    
    for i, market in enumerate(filtered_markets, 1):
        log_market_details(market, i, len(filtered_markets), client)
    
    # Step 5: Send notification about found markets
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"📱 PREPARING TO SEND NOTIFICATION FOR {len(found_markets_summary)} MARKETS")
    logger.info("=" * 80)
    _send_notification_sync(found_markets_summary)
    
    # Step 6: Auto-trading - Buy 1 share for each qualifying outcome
    logger.info("")
    logger.info("=" * 80)
    logger.info("💰 AUTO-TRADING PHASE")
    logger.info("=" * 80)
    
    # Check balance before attempting to buy
    logger.info("💳 Checking balance...")
    try:
        balance = get_current(force=True)
        available_usd = balance.get("available_usd", 0.0)
        total_usd = balance.get("total_usd", 0.0)
        
        logger.info(f"   Available: ${available_usd:.2f}")
        logger.info(f"   Total: ${total_usd:.2f}")
        
        # Check if wallet credentials are available
        if not settings.wallet_private_key:
            logger.warning("⚠️  WALLET_PRIVATE_KEY not configured - skipping auto-trading")
            _send_trading_notification_sync(
                f"⚠️ <b>Auto-Trading Skipped</b>\n\n"
                f"❌ WALLET_PRIVATE_KEY not configured\n"
                f"Please set WALLET_PRIVATE_KEY environment variable or in .env file"
            )
        elif available_usd < 1.0:
            logger.warning("⚠️  Insufficient balance (< $1) - skipping auto-trading")
            _send_trading_notification_sync(
                f"⚠️ <b>Auto-Trading Skipped</b>\n\n"
                f"💳 Available balance: ${available_usd:.2f}\n"
                f"❌ Minimum required: $1.00"
            )
        else:
            # Initialize authenticated client for trading
            logger.info("🔐 Initializing authenticated client for trading...")
            try:
                trading_client = PolymarketClient(require_auth=True)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to initialize trading client: {error_msg}")
                _send_trading_notification_sync(
                    f"❌ <b>Auto-Trading Failed</b>\n\n"
                    f"Failed to initialize authenticated client:\n"
                    f"{error_msg}\n\n"
                    f"Please check:\n"
                    f"• WALLET_PRIVATE_KEY is set\n"
                    f"• POLYMARKET_PROXY_ADDRESS is set\n"
                    f"• Credentials are valid"
                )
                raise
            
            # Trading results tracking
            trading_results = []
            total_attempted = 0
            total_successful = 0
            total_failed = 0
            total_spent = 0.0
            
            # Buy outcomes for each filtered market
            logger.info("")
            logger.info(f"🛒 PROCESSING {len(filtered_markets)} MARKETS FOR TRADING")
            logger.info("=" * 80)
            
            for i, market in enumerate(filtered_markets, 1):
                market_title = market.get("question", "Unknown Market")
                logger.info("")
                logger.info(f"[{i}/{len(filtered_markets)}] Processing: {market_title[:80]}")
                
                # Get stored pricing data
                pricing_data = market.get("_pricing_data", {})
                if not pricing_data:
                    logger.warning(f"   ⚠️  No pricing data available - skipping")
                    continue
                
                # Buy outcomes for this market
                results_before = len(trading_results)
                trading_results = buy_market_outcomes(
                    market=market,
                    pricing_data=pricing_data,
                    min_ask_price=min_ask_price,
                    max_ask_price=max_ask_price,
                    client=trading_client,
                    balance=balance,
                    trading_results=trading_results
                )
                
                # Update counters
                new_results = trading_results[results_before:]
                total_attempted += len(new_results)
                for result in new_results:
                    if result.get("status") == "SUCCESS":
                        total_successful += 1
                        total_spent += result.get("cost", 0.0)
                    else:
                        total_failed += 1
                
                # Update balance after each market (approximate, will refresh periodically)
                if i % 5 == 0:  # Refresh balance every 5 markets
                    balance = get_current(force=True)
                    logger.debug(f"   💳 Refreshed balance: ${balance.get('available_usd', 0.0):.2f}")
            
            # Final trading summary
            logger.info("")
            logger.info("=" * 80)
            logger.info("💰 TRADING SUMMARY")
            logger.info("=" * 80)
            logger.info(f"📊 Markets processed: {len(filtered_markets)}")
            logger.info(f"🎯 Outcomes attempted: {total_attempted}")
            logger.info(f"✅ Successful buys: {total_successful}")
            logger.info(f"❌ Failed buys: {total_failed}")
            logger.info(f"💵 Total spent: ${total_spent:.2f}")
            
            # Get final balance
            final_balance = get_current(force=True)
            logger.info(f"💳 Final available balance: ${final_balance.get('available_usd', 0.0):.2f}")
            logger.info("=" * 80)
            
            # Send final trading summary notification
            if total_attempted > 0:
                success_rate = (total_successful / total_attempted * 100) if total_attempted > 0 else 0
                _send_trading_notification_sync(
                    f"📊 <b>Trading Summary</b>\n\n"
                    f"✅ Successful: {total_successful}/{total_attempted} ({success_rate:.1f}%)\n"
                    f"❌ Failed: {total_failed}\n"
                    f"💵 Total spent: ${total_spent:.2f}\n"
                    f"💳 Remaining: ${final_balance.get('available_usd', 0.0):.2f}"
                )
    except Exception as e:
        logger.error(f"❌ Error during auto-trading phase: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        _send_trading_notification_sync(
            f"❌ <b>Auto-Trading Error</b>\n\n"
            f"Error: {str(e)[:200]}"
        )
    
    # Final summary
    elapsed = time.time() - start_time
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ ANALYSIS COMPLETE")
    logger.info("=" * 80)
    logger.info(f"📊 Total sports markets fetched: {len(all_sports_markets)}")
    logger.info(f"🔴 Live markets found: {len(live_markets)}")
    logger.info(f"✅ Filtered markets (liquidity + ask price): {len(filtered_markets)}")
    logger.info(f"⏱️  Time elapsed: {elapsed:.2f}s")
    logger.info("=" * 80)
    
    return filtered_markets


def _send_start_notification(
    max_workers: int,
    lookback_hours: float,
    min_liquidity: float,
    min_ask_price: float,
    max_ask_price: float
) -> None:
    """Send notification that analysis is starting.
    
    Args:
        max_workers: Number of concurrent threads
        lookback_hours: Hours to look back for live games
        min_liquidity: Minimum liquidity threshold
        min_ask_price: Minimum ask price (0-1)
        max_ask_price: Maximum ask price (0-1)
    """
    logger.info("📱 Preparing start notification...")
    
    if not BOT_B_AVAILABLE:
        logger.debug("❌ bot_b not available - skipping start notification")
        return
    
    logger.info("✅ bot_b module is available for start notification")
    
    try:
        chat_id = settings.bot_b_default_chat_id
        logger.info(f"🔍 Checking BOT_B_DEFAULT_CHAT_ID for start notification: {chat_id}")
        
        if not chat_id:
            logger.debug("❌ BOT_B_DEFAULT_CHAT_ID not configured - skipping start notification")
            return
        
        logger.info(f"✅ Chat ID configured: {chat_id}")
        
        message = (
            "🚀 <b>Live Sports Analysis Started</b>\n\n"
            f"⚙️ <b>Configuration:</b>\n"
            f"• Max workers: {max_workers}\n"
            f"• Lookback window: {lookback_hours}h\n"
            f"• Min liquidity: ${min_liquidity:,.2f}\n"
            f"• Ask price range: {min_ask_price*100:.0f}%-{max_ask_price*100:.0f}%\n\n"
            "🔍 Searching for markets..."
        )
        
        logger.info(f"📝 Formatted start notification message ({len(message)} characters)")
        logger.debug(f"Message: {message}")
        
        logger.info("🔄 Creating async event loop for start notification...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            logger.info(f"📤 Sending start notification to chat {chat_id}...")
            # Add timeout to prevent hanging - use direct notification to avoid Firestore
            loop.run_until_complete(asyncio.wait_for(_send_notification_direct(chat_id, message), timeout=10.0))
            logger.info(f"✅ Start notification sent successfully to chat {chat_id}")
        except asyncio.TimeoutError:
            logger.error("❌ Start notification timed out after 10 seconds")
        except Exception as e:
            logger.error(f"❌ Error sending start notification: {e}")
        finally:
            # Always close the loop, even if there was an error
            try:
                # Cancel any pending tasks
                try:
                    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    for task in pending:
                        task.cancel()
                    # Wait briefly for tasks to be cancelled (with timeout)
                    if pending:
                        loop.run_until_complete(asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=2.0
                        ))
                except Exception as cleanup_error:
                    logger.debug(f"Error during task cleanup: {cleanup_error}")
            finally:
                try:
                    loop.close()
                    logger.info("🔄 Event loop closed")
                except Exception:
                    pass
        
        logger.info("=" * 80)
    
    except RuntimeError as e:
        logger.error(f"❌ Runtime error sending start notification: {e}")
        logger.error("   This usually means TELEGRAM_BOT_B_TOKEN is not set")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"❌ Failed to send start notification: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.info("=" * 80)


def _send_trading_notification_sync(message: str) -> None:
    """Send a trading-related notification via Telegram.
    
    Args:
        message: HTML-formatted message to send
    """
    logger.info("📱 Preparing trading notification...")
    
    if not BOT_B_AVAILABLE:
        logger.debug("❌ bot_b not available - skipping trading notification")
        return
    
    try:
        chat_id = settings.bot_b_default_chat_id
        if not chat_id:
            logger.debug("❌ BOT_B_DEFAULT_CHAT_ID not configured - skipping trading notification")
            return
        
        logger.info(f"📤 Sending trading notification to chat {chat_id}...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(asyncio.wait_for(_send_notification_direct(chat_id, message), timeout=10.0))
            logger.info(f"✅ Trading notification sent successfully")
        except asyncio.TimeoutError:
            logger.error("❌ Trading notification timed out after 10 seconds")
        except Exception as e:
            logger.error(f"❌ Error sending trading notification: {e}")
        finally:
            try:
                # Cancel pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                loop.close()
    except Exception as e:
        logger.error(f"❌ Error in trading notification: {e}")


def _send_notification_sync(found_markets: list[dict[str, Any]]) -> None:
    """Send notification via bot_b (synchronous wrapper).
    
    Args:
        found_markets: List of market summary dictionaries
    """
    logger.info("=" * 80)
    logger.info("📱 ATTEMPTING TO SEND NOTIFICATION")
    logger.info("=" * 80)
    
    if not BOT_B_AVAILABLE:
        logger.warning("❌ bot_b not available - skipping notification")
        logger.info("   Reason: bot_b module could not be imported (aiogram may not be installed)")
        return
    
    logger.info("✅ bot_b module is available")
    
    try:
        chat_id = settings.bot_b_default_chat_id
        logger.info(f"🔍 Checking BOT_B_DEFAULT_CHAT_ID: {chat_id}")
        
        if not chat_id:
            logger.warning("❌ BOT_B_DEFAULT_CHAT_ID not configured - skipping notification")
            logger.info("   To enable notifications, set BOT_B_DEFAULT_CHAT_ID in your environment variables")
            return
        
        logger.info(f"✅ Chat ID configured: {chat_id}")
        logger.info(f"📊 Found markets count: {len(found_markets)}")
        
        message = format_markets_notification(found_markets)
        logger.info(f"📝 Formatted notification message ({len(message)} characters)")
        logger.debug(f"Message preview: {message[:200]}...")
        
        logger.info("🔄 Creating async event loop for notification...")
        # Run async notification in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            logger.info(f"📤 Sending notification to chat {chat_id}...")
            # Add timeout to prevent hanging - use direct notification to avoid Firestore
            loop.run_until_complete(asyncio.wait_for(_send_notification_direct(chat_id, message), timeout=10.0))
            logger.info(f"✅ Notification sent successfully to chat {chat_id}")
        except asyncio.TimeoutError:
            logger.error("❌ Notification timed out after 10 seconds")
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
        finally:
            # Always close the loop, even if there was an error
            try:
                # Cancel any pending tasks
                try:
                    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    for task in pending:
                        task.cancel()
                    # Wait briefly for tasks to be cancelled (with timeout)
                    if pending:
                        loop.run_until_complete(asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=2.0
                        ))
                except Exception as cleanup_error:
                    logger.debug(f"Error during task cleanup: {cleanup_error}")
            finally:
                try:
                    loop.close()
                    logger.info("🔄 Event loop closed")
                except Exception:
                    pass
        
        logger.info("=" * 80)
    
    except RuntimeError as e:
        logger.error(f"❌ Runtime error sending notification: {e}")
        logger.error("   This usually means TELEGRAM_BOT_B_TOKEN is not set")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"❌ Failed to send notification: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.info("=" * 80)

