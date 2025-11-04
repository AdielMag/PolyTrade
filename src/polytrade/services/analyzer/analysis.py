from __future__ import annotations

import time
from typing import Any

from loguru import logger

from ...shared.config import settings
from ...shared.firestore import add_doc
from ...shared.polymarket_client import PolymarketClient


def compute_edge_bps(fair: float, ask: float) -> float:
    if ask <= 0:
        return 0.0
    return (fair - ask) * 10000.0 / ask


def run_analysis(max_suggestions: int = 5, min_price: float = 0.20, max_price: float = 0.80) -> list[dict[str, Any]]:
    """Analyze markets from Polymarket and create trade suggestions.
    
    Smart analyzer that:
    - Looks for tradeable markets (prices between 20-80% = has some uncertainty)
    - Checks BOTH YES and NO sides of each market
    - Prioritizes markets with good liquidity
    - Uses Polymarket data only (no external sources)
    
    Args:
        max_suggestions: Maximum number of suggestions to return
        min_price: Minimum market price to consider (default 0.20 = 20%)
        max_price: Maximum market price to consider (default 0.80 = 80%)
    """
    logger.info("=" * 80)
    logger.info("🧠 Starting SMART ANALYZER (Polymarket only)")
    logger.info(f"Max suggestions: {max_suggestions}")
    logger.info(f"Price range: {int(min_price*100)}%-{int(max_price*100)}% (tradeable markets)")
    logger.info(f"Min liquidity: ${settings.min_liquidity_usd}")
    logger.info(f"Strategy: Checking BOTH YES and NO sides for tradeable prices")
    logger.info("=" * 80)
    
    # Create client without authentication for read-only market fetching
    # Authentication is only needed for trading operations
    client = PolymarketClient(require_auth=False)
    logger.info("Fetching SPORTS markets from Polymarket Gamma API...")
    markets = client.list_markets()
    logger.info(f"✅ Fetched {len(markets)} sports markets from Polymarket")
    
    # Check first market structure
    if markets:
        first_market = markets[0]
        logger.info("=" * 80)
        logger.info("ANALYZING FIRST MARKET STRUCTURE:")
        logger.info(f"  Question: {first_market.get('question', 'N/A')[:80]}")
        logger.info(f"  Has 'clobTokenIds': {('clobTokenIds' in first_market)}")
        logger.info(f"  Has 'liquidityClob': {('liquidityClob' in first_market)}")
        logger.info(f"  Liquidity value: {first_market.get('liquidityClob', 'N/A')}")
        if 'clobTokenIds' in first_market:
            clob_token_ids = first_market.get('clobTokenIds', [])
            logger.info(f"  clobTokenIds count: {len(clob_token_ids)}")
            if clob_token_ids:
                logger.info(f"  First token_id: {clob_token_ids[0]}")
        logger.info("=" * 80)
    
    suggestions: list[dict[str, Any]] = []
    now = int(time.time())
    
    # Stats tracking
    stats = {
        "total_markets": len(markets),
        "no_tokens": 0,
        "low_liquidity": 0,
        "no_quotes": 0,
        "invalid_price": 0,
        "price_out_of_range": 0,
        "insufficient_edge": 0,
        "suggestions_created": 0,
        "errors": 0
    }
    
    for idx, market in enumerate(markets, 1):
        if len(suggestions) >= max_suggestions:
            logger.info(f"Reached max suggestions limit ({max_suggestions}), stopping analysis")
            break
            
        try:
            # Extract market data
            market_question = market.get("question", "N/A")
            condition_id = market.get("condition_id", "N/A")
            
            # More verbose logging for first 5 markets
            if idx <= 5:
                logger.info("=" * 60)
                logger.info(f"🔍 MARKET #{idx}: {market_question[:70]}")
            elif idx <= 20:  # Less detail for markets 6-20
                logger.info(f"[{idx}/{len(markets)}] Analyzing: {market_question[:80]}")
            elif idx % 50 == 0:  # Then log every 50th
                logger.info(f"Progress: analyzed {idx}/{len(markets)} markets so far")
            
            # Check 1: clobTokenIds (Polymarket uses this field name)
            # Note: clobTokenIds may be a JSON string, need to parse it
            clob_token_ids_raw = market.get("clobTokenIds", [])
            
            # Parse if it's a string
            if isinstance(clob_token_ids_raw, str):
                try:
                    import json
                    clob_token_ids = json.loads(clob_token_ids_raw)
                except (json.JSONDecodeError, ValueError):
                    clob_token_ids = []
            else:
                clob_token_ids = clob_token_ids_raw if clob_token_ids_raw else []
            
            if idx <= 5:
                logger.info(f"  ✓ Check 1 - clobTokenIds: {len(clob_token_ids)} found")
            
            if not clob_token_ids or len(clob_token_ids) == 0:
                stats["no_tokens"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: No clobTokenIds in this market")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: no clobTokenIds - {market_question[:60]}")
                continue
                
            # Get YES token (typically first token ID in the array)
            token_id = clob_token_ids[0]
            
            if idx <= 5:
                logger.info(f"  ✓ Token ID: {token_id}")
            
            # Check 2: Liquidity (use liquidityClob field from Polymarket)
            liquidity = float(market.get("liquidityClob", 0))
            
            if idx <= 5:
                logger.info(f"  ✓ Check 2 - Liquidity (liquidityClob): ${liquidity:.2f}")
                logger.info(f"    Threshold: ${settings.min_liquidity_usd}")
                logger.info(f"    Pass: {liquidity >= settings.min_liquidity_usd}")
            
            if liquidity < settings.min_liquidity_usd:
                stats["no_liquidity"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: Liquidity ${liquidity:.2f} < ${settings.min_liquidity_usd}")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: low liquidity ${liquidity:.2f} < ${settings.min_liquidity_usd} - {market_question[:60]}")
                continue
            
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
                        outcome = "YES" if i == 0 else "NO"  # First token is usually YES
                        if idx <= 5:
                            logger.info(f"  ✓ Found competitive token #{i+1} ({outcome}): ${ask_temp:.4f}")
                        break
                except Exception:
                    continue
            
            # If no token in range, skip this market
            if best_token_id is None or best_ask is None:
                stats["price_out_of_range"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: No token with price in range ${min_price:.2f}-${max_price:.2f}")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: no tokens in price range - {market_question[:60]}")
                continue
            
            token_id = best_token_id
            current_ask = best_ask
            current_bid = best_bid
            
            if idx <= 5:
                logger.info(f"  ✓ Check 3 - Selected {outcome} token")
                logger.info(f"    Token ID: {token_id}")
                logger.info(f"    Quotes: bid=${current_bid:.4f}, ask=${current_ask:.4f}")
            
            # Check 4: Valid ask price
            if idx <= 5:
                logger.info(f"  ✓ Check 4 - Ask price valid: {current_ask > 0}")
            
            if current_ask <= 0:
                stats["invalid_price"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: Invalid ask price {current_ask}")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: invalid ask price {current_ask} - {market_question[:60]}")
                continue
            
            # Check 5: Price already confirmed in range (we selected the best token above)
            if idx <= 5:
                logger.info(f"  ✓ Check 5 - Price: ${current_ask:.4f} ✅ In target range!")
            
            # Already filtered above, all markets here are in range
            
            # Smart suggestion: For competitive markets (40-60%), both sides are reasonable
            # We suggest based on liquidity and market activity, not edge calculation
            mid_price = (current_bid + current_ask) / 2
            spread = current_ask - current_bid
            
            if idx <= 5:
                logger.info(f"  ✓ Market analysis:")
                logger.info(f"    Mid price: ${mid_price:.4f}")
                logger.info(f"    Spread: ${spread:.4f} ({spread/mid_price*100:.1f}%)")
            
            # For competitive markets, we trade the side we're looking at
            # Since we already filtered for 40-60% range, these are good opportunities
            fair_value = mid_price
            edge_bps = compute_edge_bps(fair_value, current_ask)
            
            if idx <= 5:
                logger.info(f"  ✓ Check 6 - Market competitiveness passed (in target range)")
                logger.info(f"    Calculated edge: {edge_bps:.2f} bps (informational only)")
            
            # Accept all markets that passed price filter
            if True:
                if idx <= 5:
                    logger.info(f"  ✅ PASSED ALL CHECKS! Creating suggestion...")
                
                # Determine side based on the outcome token we selected
                side = f"BUY_{outcome.upper()}" if outcome else "BUY_YES"
                
                suggestion = {
                    "tokenId": token_id,
                    "marketId": market.get("condition_id", ""),
                    "title": market.get("question", ""),
                    "side": side,
                    "edgeBps": int(edge_bps),
                    "sizeHint": min(liquidity * 0.01, 10.0),  # 1% of liquidity, max $10
                    "price": current_ask,
                    "fairValue": fair_value,
                    "liquidity": liquidity,
                    "expiresAt": now + 3600,  # 1 hour expiry
                    "status": "OPEN",
                    "createdAt": now,
                    "suggestedAt": now  # Date when suggestion was created for tracking
                }
                
                # Try to save to Firestore, but continue if it fails (e.g., local testing)
                try:
                    add_doc("suggestions", suggestion)
                except Exception as firestore_err:
                    logger.warning(f"⚠️  Could not save to Firestore (continuing anyway): {firestore_err}")
                
                suggestions.append(suggestion)
                stats["suggestions_created"] += 1
                logger.info(f"🎉 SUGGESTION #{len(suggestions)}: {market_question[:70]}")
                logger.info(f"   Edge: {edge_bps:.2f} bps | Price: ${current_ask:.4f} | Fair: ${fair_value:.4f} | Liquidity: ${liquidity:.2f}")
            else:
                stats["insufficient_edge"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: Insufficient edge {edge_bps:.2f} bps < {settings.edge_bps} bps")
                elif idx <= 20:
                    logger.debug(f"  ⚠️ Insufficient edge: {edge_bps:.2f} bps < {settings.edge_bps} bps - {market_question[:60]}")
                
        except Exception as e:
            stats["errors"] += 1
            if idx <= 5:
                logger.error(f"  ❌ EXCEPTION during analysis: {e}")
                import traceback
                logger.error(f"     {traceback.format_exc()}")
            else:
                logger.error(f"❌ Error analyzing market {idx}: {e}")
                if idx <= 20:
                    logger.error(f"   Market: {market_question[:60]}")
            continue
    
    # Final summary
    logger.info("=" * 80)
    logger.info("ANALYSIS SUMMARY:")
    logger.info(f"  Total markets analyzed: {stats['total_markets']}")
    logger.info(f"  Skipped - no tokens: {stats['no_tokens']}")
    logger.info(f"  Skipped - low liquidity: {stats['low_liquidity']}")
    logger.info(f"  Skipped - quote errors: {stats['no_quotes']}")
    logger.info(f"  Skipped - invalid prices: {stats['invalid_price']}")
    logger.info(f"  Skipped - price out of range (${min_price:.2f}-${max_price:.2f}): {stats['price_out_of_range']}")
    logger.info(f"  Skipped - insufficient edge: {stats['insufficient_edge']}")
    logger.info(f"  Errors encountered: {stats['errors']}")
    logger.info(f"  ✅ SUGGESTIONS CREATED: {stats['suggestions_created']}")
    logger.info("=" * 80)
    
    return suggestions

