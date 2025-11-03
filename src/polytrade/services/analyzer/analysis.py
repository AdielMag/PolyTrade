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


def run_analysis(max_suggestions: int = 5, min_price: float = 0.01, max_price: float = 0.99) -> list[dict[str, Any]]:
    """Analyze SPORTS markets from Polymarket ONLY and create trade suggestions.
    
    Only analyzes sports-related markets from Polymarket Gamma API.
    Does NOT check external data sources or non-sports markets.
    
    Args:
        max_suggestions: Maximum number of suggestions to return
        min_price: Minimum market price to consider (default 0.01 = 1 cent, essentially no lower limit)
        max_price: Maximum market price to consider (default 0.99 = 99 cents, essentially no upper limit)
    """
    logger.info("=" * 80)
    logger.info("Starting SPORTS MARKETS analysis (Polymarket only)")
    logger.info(f"Max suggestions: {max_suggestions}")
    logger.info(f"Price range filter: ${min_price:.2f} - ${max_price:.2f}")
    logger.info(f"Min liquidity threshold: ${settings.min_liquidity_usd}")
    logger.info(f"Min edge threshold: {settings.edge_bps} bps")
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
                stats["low_liquidity"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: Liquidity ${liquidity:.2f} < ${settings.min_liquidity_usd}")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: low liquidity ${liquidity:.2f} < ${settings.min_liquidity_usd} - {market_question[:60]}")
                continue
            
            # Check 3: Get current market price (quotes)
            if idx <= 5:
                logger.info(f"  ✓ Check 3 - Fetching quotes for token {token_id}...")
            
            try:
                quotes = client.get_quotes(token_id)
            except Exception as quote_err:
                stats["no_quotes"] += 1
                if idx <= 5:
                    logger.error(f"  ❌ FAILED: Could not get quotes - {quote_err}")
                else:
                    logger.debug(f"  ❌ Skipped: failed to get quotes - {quote_err}")
                continue
                
            current_ask = quotes["best_ask"]
            current_bid = quotes["best_bid"]
            
            if idx <= 5:
                logger.info(f"  ✓ Got quotes: bid=${current_bid:.4f}, ask=${current_ask:.4f}")
            
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
            
            # Check 5: Price within target range (70-85 cents)
            if idx <= 5:
                logger.info(f"  ✓ Check 5 - Price range: ${current_ask:.4f} (target: ${min_price:.2f}-${max_price:.2f})")
                logger.info(f"    In range: {min_price <= current_ask <= max_price}")
            
            if not (min_price <= current_ask <= max_price):
                stats["price_out_of_range"] += 1
                if idx <= 5:
                    logger.warning(f"  ❌ FAILED: Price ${current_ask:.4f} outside range ${min_price:.2f}-${max_price:.2f}")
                elif idx <= 20:
                    logger.debug(f"  ❌ Skipped: price ${current_ask:.4f} out of range - {market_question[:60]}")
                continue
            
            # Value-based analysis: calculate fair value using ONLY Polymarket data
            # We use the market mid-price from Polymarket as the fair value
            # No external data sources (bookmakers, stats sites, etc.) are used
            mid_price = (current_bid + current_ask) / 2
            
            if idx <= 5:
                logger.info(f"  ✓ Mid price (from Polymarket): ${mid_price:.4f}")
            
            # Fair value = mid price from Polymarket order book
            # This represents the market consensus on Polymarket
            fair_value = mid_price
            
            if idx <= 5:
                logger.info(f"  ✓ Fair value: ${fair_value:.4f} (using Polymarket mid-price)")
            
            # Calculate edge in basis points
            edge_bps = compute_edge_bps(fair_value, current_ask)
            
            if idx <= 5:
                logger.info(f"  ✓ Check 6 - Edge: {edge_bps:.2f} bps")
                logger.info(f"    Threshold: {settings.edge_bps} bps")
                logger.info(f"    Pass: {edge_bps >= settings.edge_bps}")
            elif idx <= 20:
                logger.debug(f"  📊 Edge: {edge_bps:.2f} bps (threshold: {settings.edge_bps})")
            
            # Only suggest if edge exceeds threshold
            if edge_bps >= settings.edge_bps:
                if idx <= 5:
                    logger.info(f"  ✅ PASSED ALL CHECKS! Creating suggestion...")
                
                suggestion = {
                    "tokenId": token_id,
                    "marketId": market.get("condition_id", ""),
                    "title": market.get("question", ""),
                    "side": "BUY_YES",
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
                add_doc("suggestions", suggestion)
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

