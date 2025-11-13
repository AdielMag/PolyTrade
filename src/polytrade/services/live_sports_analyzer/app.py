from __future__ import annotations

from fastapi import FastAPI, Body
from loguru import logger
from typing import Any

from .live_sports_analysis import run_live_sports_analysis
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()


@app.post("/run")
def run(
    max_workers: int = Body(default=10, embed=True),
    lookback_hours: float = Body(default=4.0, embed=True),
    min_liquidity: float = Body(default=500.0, embed=True),
    min_ask_price: float = Body(default=0.93, embed=True),
    max_ask_price: float = Body(default=0.96, embed=True)
) -> dict[str, Any]:
    """Run the live sports market analysis.
    
    Args (all optional, passed in request body):
        max_workers: Number of concurrent threads (default: 10)
        lookback_hours: Hours to look back for live games (default: 4.0)
        min_liquidity: Minimum liquidity in USD (default: 500.0)
        min_ask_price: Minimum ask price 0-1 (default: 0.93 for 93%)
        max_ask_price: Maximum ask price 0-1 (default: 0.96 for 96%)
    
    Returns:
        Dictionary with count of filtered markets found
    """
    logger.info("Received POST /run request - starting live sports analysis")
    logger.info(f"Parameters: max_workers={max_workers}, lookback_hours={lookback_hours}, "
                f"min_liquidity={min_liquidity}, min_ask_price={min_ask_price}, max_ask_price={max_ask_price}")
    
    filtered_markets = run_live_sports_analysis(
        max_workers=max_workers,
        lookback_hours=lookback_hours,
        min_liquidity=min_liquidity,
        min_ask_price=min_ask_price,
        max_ask_price=max_ask_price
    )
    logger.info(f"Analysis complete - found {len(filtered_markets)} filtered markets")
    return {
        "filtered_markets_found": len(filtered_markets),
        "parameters": {
            "max_workers": max_workers,
            "lookback_hours": lookback_hours,
            "min_liquidity": min_liquidity,
            "min_ask_price": min_ask_price,
            "max_ask_price": max_ask_price
        }
    }


@app.get("/health")
def health() -> dict[str, bool]:
    """Health check endpoint.
    
    Returns:
        Dictionary indicating service is healthy
    """
    logger.debug("Health check requested")
    return {"ok": True}

