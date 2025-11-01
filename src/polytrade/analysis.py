from __future__ import annotations

import time
from typing import Any

from loguru import logger

from .config import settings
from .firestore import add_doc
from .polymarket_client import PolymarketClient


def compute_edge_bps(fair: float, ask: float) -> float:
    if ask <= 0:
        return 0.0
    return (fair - ask) * 10000.0 / ask


def run_analysis(max_suggestions: int = 5) -> list[dict[str, Any]]:
    """Analyze sports markets and create value-based trade suggestions."""
    client = PolymarketClient()
    markets = client.list_markets()
    
    suggestions: list[dict[str, Any]] = []
    now = int(time.time())
    
    for market in markets:
        if len(suggestions) >= max_suggestions:
            break
            
        try:
            # Extract market data
            tokens = market.get("tokens", [])
            if not tokens:
                continue
                
            # Get YES token (typically first token)
            yes_token = tokens[0]
            token_id = yes_token.get("token_id", "")
            
            # Filter by liquidity
            liquidity = float(market.get("liquidity", 0))
            if liquidity < settings.min_liquidity_usd:
                continue
            
            # Get current market price
            quotes = client.get_quotes(token_id)
            current_ask = quotes["best_ask"]
            current_bid = quotes["best_bid"]
            
            if current_ask <= 0:
                continue
            
            # Value-based analysis: calculate fair value
            # Simple approach: use midpoint adjusted by volume and momentum
            mid_price = (current_bid + current_ask) / 2
            
            # Calculate implied probability from market price
            implied_prob = mid_price
            
            # Fair value estimation (simplified)
            # In real implementation, fetch external odds or stats
            fair_value = implied_prob  # Placeholder: use external data source
            
            # Calculate edge in basis points
            edge_bps = compute_edge_bps(fair_value, current_ask)
            
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
                logger.info(f"Created suggestion: {suggestion['title']} (edge: {edge_bps} bps)")
                
        except Exception as e:
            logger.error(f"Error analyzing market: {e}")
            continue
    
    logger.info(f"Analysis complete: created {len(suggestions)} suggestions")
    return suggestions


