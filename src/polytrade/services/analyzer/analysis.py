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


def run_analysis(max_suggestions: int = 5) -> list[dict[str, Any]]:
    """Analyze sports markets and create value-based trade suggestions."""
    logger.info("=" * 80)
    logger.info("Starting analysis run")
    logger.info(f"Max suggestions: {max_suggestions}")
    logger.info(f"Min liquidity: ${settings.min_liquidity_usd}")
    logger.info(f"Min edge threshold: {settings.edge_bps} bps")
    
    client = PolymarketClient()
    logger.info("Fetching markets from Polymarket...")
    markets = client.list_markets()
    logger.info(f"Fetched {len(markets)} total markets")
    
    suggestions: list[dict[str, Any]] = []
    now = int(time.time())
    
    # Stats tracking
    stats = {
        "total_markets": len(markets),
        "no_tokens": 0,
        "low_liquidity": 0,
        "no_quotes": 0,
        "invalid_price": 0,
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
            
            if idx <= 10:  # Log first 10 markets in detail
                logger.debug(f"[{idx}/{len(markets)}] Analyzing: {market_question[:80]}")
            elif idx % 50 == 0:  # Then log every 50th
                logger.info(f"Progress: analyzed {idx}/{len(markets)} markets so far")
            
            tokens = market.get("tokens", [])
            if not tokens:
                stats["no_tokens"] += 1
                logger.debug(f"  ❌ Skipped: no tokens - {market_question[:60]}")
                continue
                
            # Get YES token (typically first token)
            yes_token = tokens[0]
            token_id = yes_token.get("token_id", "")
            
            # Filter by liquidity
            liquidity = float(market.get("liquidity", 0))
            if liquidity < settings.min_liquidity_usd:
                stats["low_liquidity"] += 1
                if idx <= 10:
                    logger.debug(f"  ❌ Skipped: low liquidity ${liquidity:.2f} < ${settings.min_liquidity_usd} - {market_question[:60]}")
                continue
            
            # Get current market price
            try:
                quotes = client.get_quotes(token_id)
            except Exception as quote_err:
                stats["no_quotes"] += 1
                logger.debug(f"  ❌ Skipped: failed to get quotes - {quote_err}")
                continue
                
            current_ask = quotes["best_ask"]
            current_bid = quotes["best_bid"]
            
            if current_ask <= 0:
                stats["invalid_price"] += 1
                if idx <= 10:
                    logger.debug(f"  ❌ Skipped: invalid ask price {current_ask} - {market_question[:60]}")
                continue
            
            # Value-based analysis: calculate fair value
            # Simple approach: use midpoint adjusted by volume and momentum
            mid_price = (current_bid + current_ask) / 2
            
            if idx <= 10:
                logger.debug(f"  💰 Prices: bid=${current_bid:.4f}, ask=${current_ask:.4f}, mid=${mid_price:.4f}, liq=${liquidity:.2f}")
            
            # Calculate implied probability from market price
            implied_prob = mid_price
            
            # Fair value estimation (simplified)
            # In real implementation, fetch external odds or stats
            fair_value = implied_prob  # Placeholder: use external data source
            
            # Calculate edge in basis points
            edge_bps = compute_edge_bps(fair_value, current_ask)
            
            if idx <= 10:
                logger.debug(f"  📊 Edge calculation: fair={fair_value:.4f}, ask={current_ask:.4f}, edge={edge_bps:.2f} bps")
            
            # Only suggest if edge exceeds threshold
            if edge_bps >= settings.edge_bps:
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
                    "createdAt": now
                }
                add_doc("suggestions", suggestion)
                suggestions.append(suggestion)
                stats["suggestions_created"] += 1
                logger.info(f"✅ SUGGESTION #{len(suggestions)}: {market_question[:70]}")
                logger.info(f"   Edge: {edge_bps:.2f} bps | Price: ${current_ask:.4f} | Fair: ${fair_value:.4f} | Liquidity: ${liquidity:.2f}")
            else:
                stats["insufficient_edge"] += 1
                if idx <= 10:
                    logger.debug(f"  ⚠️ Insufficient edge: {edge_bps:.2f} bps < {settings.edge_bps} bps - {market_question[:60]}")
                
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"❌ Error analyzing market {idx}: {e}")
            if idx <= 10:
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
    logger.info(f"  Skipped - insufficient edge: {stats['insufficient_edge']}")
    logger.info(f"  Errors encountered: {stats['errors']}")
    logger.info(f"  ✅ SUGGESTIONS CREATED: {stats['suggestions_created']}")
    logger.info("=" * 80)
    
    return suggestions

