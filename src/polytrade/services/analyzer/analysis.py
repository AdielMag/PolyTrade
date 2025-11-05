from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from loguru import logger

from ...shared.config import settings
from ...shared.firestore import add_doc
from ...shared.polymarket_client import PolymarketClient


def compute_edge_bps(fair: float, ask: float) -> float:
    if ask <= 0:
        return 0.0
    return (fair - ask) * 10000.0 / ask


def _analyze_single_market(
    market: dict[str, Any],
    client: PolymarketClient,
    min_price: float,
    max_price: float,
    now: int,
) -> dict[str, Any] | None:
    """Analyze a single market and return suggestion if it matches criteria.
    
    Returns None if market doesn't match criteria, or dict with suggestion data.
    """
    try:
        market_question = market.get("question", "N/A")
        condition_id = market.get("condition_id", "N/A")
        
        # Check 1: clobTokenIds
        clob_token_ids_raw = market.get("clobTokenIds", [])
        if isinstance(clob_token_ids_raw, str):
            import json
            clob_token_ids = json.loads(clob_token_ids_raw)
        else:
            clob_token_ids = clob_token_ids_raw
        
        if not clob_token_ids or len(clob_token_ids) < 1:
            return None
        
        # Check 2: Liquidity (informational only)
        liquidity = float(market.get("liquidityClob", 0))
        
        # Check 3: Check all tokens to find one with competitive pricing
        best_token_id = None
        best_ask = None
        best_bid = None
        outcome = "YES"
        
        for i, tid in enumerate(clob_token_ids):
            try:
                quotes_temp = client.get_quotes(tid)
                ask_temp = quotes_temp["best_ask"]
                bid_temp = quotes_temp["best_bid"]
                
                # Check if this token's ask price is in our target range
                if min_price <= ask_temp <= max_price:
                    best_token_id = tid
                    best_ask = ask_temp
                    best_bid = bid_temp
                    outcome = "YES" if i == 0 else "NO"
                    break
            except Exception as e:
                # Rate limit or other error - continue to next token
                if "429" in str(e):
                    import time
                    time.sleep(0.1)  # Brief pause on rate limit
                continue
        
        # If no token in range, skip this market
        if best_token_id is None or best_ask is None:
            return None
        
        token_id = best_token_id
        current_ask = best_ask
        current_bid = best_bid
        
        # Check 4: Valid ask price
        if current_ask <= 0:
            return None
        
        # Calculate edge
        mid_price = (current_bid + current_ask) / 2
        fair_value = mid_price
        edge_bps = compute_edge_bps(fair_value, current_ask)
        
        # Create suggestion
        side = f"BUY_{outcome.upper()}" if outcome else "BUY_YES"
        
        # Calculate market probabilities (YES vs NO percentages)
        # The price represents the probability of that outcome
        yes_probability = current_ask if outcome == "YES" else (1.0 - current_ask)
        no_probability = 1.0 - yes_probability
        
        # Get event end date - prefer gameStartTime/eventStartTime (more accurate for sports)
        end_date = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        priority = market.get("_priority", 3)
        
        suggestion = {
            "tokenId": token_id,
            "marketId": condition_id,
            "title": market_question,
            "side": side,
            "edgeBps": int(edge_bps),
            "sizeHint": min(liquidity * 0.01, 10.0) if liquidity > 0 else 1.0,
            "price": current_ask,
            "fairValue": fair_value,
            "liquidity": liquidity,
            "yesProbability": yes_probability,
            "noProbability": no_probability,
            "endDate": end_date,  # When the event finishes
            "priority": priority,  # 1=ending in 24h, 2=later, 3=no date
            "expiresAt": now + 3600,
            "status": "OPEN",
            "createdAt": now,
            "suggestedAt": now
        }
        
        # Try to save to Firestore, but continue if it fails
        try:
            add_doc("suggestions", suggestion)
        except Exception:
            pass  # Silently continue for local testing
        
        return suggestion
        
    except Exception:
        return None


def run_analysis(max_suggestions: int = 5, min_price: float = 0.80, max_price: float = 0.90) -> list[dict[str, Any]]:
    """Analyze markets from Polymarket and create trade suggestions.
    
    Smart analyzer that:
    - Looks for high probability markets (prices between 80-90% = strong favorites)
    - Checks BOTH YES and NO sides of each market
    - Uses multithreading for 5-10x faster processing
    - Uses Polymarket data only (no external sources)
    
    Args:
        max_suggestions: Maximum number of suggestions to return
        min_price: Minimum market price to consider (default 0.80 = 80%)
        max_price: Maximum market price to consider (default 0.90 = 90%)
    """
    logger.info("=" * 80)
    logger.info("🧠 Starting SMART ANALYZER (Polymarket only)")
    logger.info(f"Max suggestions: {max_suggestions}")
    logger.info(f"Price range: {int(min_price*100)}%-{int(max_price*100)}% (high probability markets)")
    logger.info(f"Strategy: Looking for strong favorites - checking BOTH YES and NO sides")
    logger.info(f"⚡ Using multithreading for faster processing")
    logger.info("=" * 80)
    
    # Create client without authentication for read-only market fetching
    client = PolymarketClient(require_auth=False)
    logger.info("Fetching markets from Polymarket Gamma API...")
    markets = client.list_markets()
    logger.info(f"✅ Fetched {len(markets)} markets from Polymarket")
    
    # Filter ONLY for markets ending in the next 6 hours (or already live)
    now = int(time.time())
    urgent_markets = []
    
    from datetime import datetime, timezone, timedelta
    now_dt = datetime.now(timezone.utc)
    six_hours_from_now = now_dt + timedelta(hours=6)
    
    logger.info(f"🔥 FILTERING FOR URGENT MARKETS ONLY (next 6 hours or live)")
    logger.info(f"⏰ Current time: {now_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"⏰ Cut-off time: {six_hours_from_now.strftime('%Y-%m-%d %H:%M UTC')}")
    
    filtered_count = 0
    for market in markets:
        # Prefer gameStartTime/eventStartTime over endDate (more accurate for events)
        end_date_str = market.get("gameStartTime") or market.get("eventStartTime") or market.get("endDate")
        if end_date_str:
            try:
                # Parse ISO format: "2024-06-17T12:00:00Z" or "2024-06-17 12:00:00+00"
                if isinstance(end_date_str, str):
                    if ' ' in end_date_str and '+' in end_date_str:
                        # Format: "2025-11-09 03:00:00+00"
                        end_dt = datetime.fromisoformat(end_date_str.replace('+00', '+00:00'))
                    else:
                        # Format: "2025-11-09T03:00:00Z"
                        end_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    # If it's already a datetime object
                    end_dt = end_date_str
                
                # Calculate time until event
                time_until = (end_dt - now_dt).total_seconds()
                hours_until = time_until / 3600
                
                # ONLY include if:
                # 1. Event is within next 6 hours, OR
                # 2. Event already started (negative time) but market still open (LIVE)
                if hours_until <= 6:  # This includes negative values (already started)
                    market['_time_to_end'] = time_until
                    market['_priority'] = 1
                    urgent_markets.append(market)
                    
                    if hours_until < 0:
                        logger.info(f"🔴 LIVE: {market.get('question', '')[:60]} (started {abs(hours_until):.1f}h ago)")
                    else:
                        logger.info(f"🟡 URGENT: {market.get('question', '')[:60]} (in {hours_until:.1f}h)")
                else:
                    filtered_count += 1
            except Exception as e:
                # Skip markets with invalid dates
                filtered_count += 1
                logger.debug(f"Skipped market due to date parse error: {e}")
        else:
            # Skip markets without dates
            filtered_count += 1
    
    # Sort by urgency (soonest/live first)
    urgent_markets.sort(key=lambda m: m.get('_time_to_end', float('inf')))
    
    logger.info("=" * 80)
    logger.info(f"✅ Found {len(urgent_markets)} URGENT markets (next 6h or live)")
    logger.info(f"❌ Filtered out {filtered_count} non-urgent markets")
    logger.info("=" * 80)
    
    prioritized_markets = urgent_markets
    
    suggestions: list[dict[str, Any]] = []
    
    logger.info(f"⚡ Processing {len(prioritized_markets)} markets in parallel with 10 concurrent threads...")
    logger.info(f"🎯 Target: {max_suggestions} suggestions")
    
    # Use ThreadPoolExecutor for parallel processing
    # 10 concurrent threads = good balance between speed and API rate limits
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all markets for processing (prioritized order)
        future_to_idx = {
            executor.submit(
                _analyze_single_market,
                market,
                client,
                min_price,
                max_price,
                now
            ): (idx, market)
            for idx, market in enumerate(prioritized_markets, 1)
        }
        
        # Collect results as they complete
        completed = 0
        stopped_early = False
        
        for future in as_completed(future_to_idx):
            # Check if we already have enough suggestions (from another thread)
            if len(suggestions) >= max_suggestions:
                stopped_early = True
                break
                
            completed += 1
            idx, market = future_to_idx[future]
            
            # Log progress every 50 markets
            if completed % 50 == 0:
                logger.info(f"⚡ Progress: {completed}/{len(markets)} processed | {len(suggestions)} suggestions found")
            
            try:
                result = future.result()
                if result:
                    suggestions.append(result)
                    priority_flag = "🔴 URGENT (24h)" if result.get('priority') == 1 else ""
                    logger.info(f"🎉 SUGGESTION #{len(suggestions)}: {result['title'][:70]} {priority_flag}")
                    logger.info(f"   Price: ${result['price']:.4f} | Side: {result['side']} | Liquidity: ${result['liquidity']:.2f}")
                    
                    # Stop if we have enough suggestions
                    if len(suggestions) >= max_suggestions:
                        logger.info(f"✅ Reached target of {max_suggestions} suggestions, stopping now!")
                        stopped_early = True
                        break
            except Exception as e:
                logger.debug(f"Error processing market {idx}: {e}")
        
        # Cancel any remaining futures if we stopped early
        if stopped_early:
            logger.info("🛑 Cancelling remaining market processing tasks...")
            for f in future_to_idx:
                if not f.done():
                    f.cancel()
    
    # Final summary
    logger.info("=" * 80)
    logger.info("ANALYSIS SUMMARY:")
    logger.info(f"  Total markets fetched: {len(markets)}")
    logger.info(f"  🔥 Urgent markets (≤6h): {len(prioritized_markets)}")
    logger.info(f"  Markets processed: {min(completed, len(prioritized_markets))}/{len(prioritized_markets)}")
    logger.info(f"  ✅ SUGGESTIONS CREATED: {len(suggestions)}")
    logger.info(f"  Processing method: Parallel (10 threads)")
    logger.info("=" * 80)
    
    return suggestions
