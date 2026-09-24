"""Assumption-impact analysis (article 7.3): repricing under a parameter change."""

from __future__ import annotations

from statistics import mean

from pricing.engine import PriceEngine
from schemas import BookingInput


def repricing_impact(
    bookings: list[BookingInput],
    base_engine: PriceEngine,
    new_engine: PriceEngine,
) -> dict:
    """Compare premiums under two engine configurations (e.g. changed θ/p/K/M)."""
    deltas: list[float] = []
    changed = 0
    for booking in bookings:
        base = base_engine.price(booking).premium_brl
        new = new_engine.price(booking).premium_brl
        delta = new - base
        deltas.append(delta)
        if abs(delta) > 1e-6:
            changed += 1
    if not deltas:
        return {"n": 0}
    abs_deltas = [abs(d) for d in deltas]
    return {
        "n": len(deltas),
        "alterados": changed,
        "delta_medio_brl": round(mean(deltas), 4),
        "delta_medio_abs_brl": round(mean(abs_deltas), 4),
        "delta_max_abs_brl": round(max(abs_deltas), 4),
        "pct_alterados": round(changed / len(deltas), 4),
    }
