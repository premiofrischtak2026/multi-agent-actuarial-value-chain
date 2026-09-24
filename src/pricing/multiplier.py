"""Data-driven seasonal multiplier M (article section 4.6).

M is the relative intensity of a region×month versus its annual mean, clipped to
the approved bounds. It replaces a hard-coded elasticity/seasonality with a
value derived from the exposure series (and remains bounded/justified).
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from config import DEFAULT_ASSUMPTIONS
from pricing.tables import ExposureTable


def _combined(row) -> float:
    cancel = 0.0 if pd.isna(row["freq_cancellation"]) else float(row["freq_cancellation"])
    rain = 0.0 if pd.isna(row["freq_rain_10mm"]) else float(row["freq_rain_10mm"])
    return cancel + rain


def seasonal_multiplier(
    table: ExposureTable,
    month: int,
    region: str,
    *,
    clip: tuple[float, float] = (0.8, 1.5),
    min_flights: int = 1,
) -> float:
    df = table.dataframe
    if not {"month", "freq_cancellation", "freq_rain_10mm", "n_flights"}.issubset(df.columns):
        return 1.0
    cells = df[df["n_flights"] >= min_flights]
    if region and "dest_region" in cells.columns:
        regional = cells[cells["dest_region"] == region]
        if not regional.empty:
            cells = regional
    if cells.empty:
        return 1.0
    cells = cells.copy()
    cells["_comb"] = cells.apply(_combined, axis=1)
    monthly = cells.groupby("month")["_comb"].mean()
    annual = monthly.mean()
    if annual <= 0 or month not in monthly.index:
        return 1.0
    multiplier = float(monthly.loc[month] / annual)
    return min(clip[1], max(clip[0], multiplier))


def make_multiplier_provider(
    table: ExposureTable,
    airport_table,
    *,
    clip: tuple[float, float] | None = None,
    min_flights: int = 1,
) -> Callable:
    """Return provider(booking, month) -> M, resolving the destination region."""
    clip = clip or (DEFAULT_ASSUMPTIONS.multiplicador_min, DEFAULT_ASSUMPTIONS.multiplicador_max)

    def provider(booking, month: int) -> float:
        airport = airport_table.get(booking.dest_icao)
        region = airport.regiao if airport else ""
        return seasonal_multiplier(table, month, region, clip=clip, min_flights=min_flights)

    return provider
