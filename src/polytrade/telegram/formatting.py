from __future__ import annotations

from . import keyboards as kb
from ..balances import get_current


def balance_header() -> str:
    bal = get_current()
    return f"Balance: ${bal['available_usd']:.2f}\n"


def suggestion_message(title: str, side: str, edge_bps: int) -> str:
    return balance_header() + f"Suggestion: {title}\nSide: {side}\nEdge: {edge_bps} bps"


