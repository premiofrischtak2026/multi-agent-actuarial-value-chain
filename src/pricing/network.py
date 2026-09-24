"""Airport similarity graph: anchors (high exposure) vs. gaps, and neighbours.

The "risk distance" combines the great-circle distance with a similarity factor
γ (climate, delays/cancellations, airport infrastructure). γ is calibration
input: until a factors table is provided, it defaults to 1.0.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from pricing.geo import Airport, AirportTable, distance_between
from pricing.similarity import ProfileTable, mahalanobis_distance
from pricing.tables import ExposureTable

GammaProvider = Callable[[Airport, Airport], float]


def risk_distance(
    source: Airport,
    target: Airport,
    *,
    profiles: ProfileTable | None = None,
    covariance_inv: Sequence[Sequence[float]] | None = None,
) -> float:
    """Great-circle distance plus a Mahalanobis term when profiles are available."""
    base = distance_between(source, target)
    if profiles is not None and covariance_inv is not None:
        source_profile = profiles.get(source.icao)
        target_profile = profiles.get(target.icao)
        if source_profile is not None and target_profile is not None:
            return base + mahalanobis_distance(source_profile.vector, target_profile.vector, covariance_inv)
    return base


def default_gamma(_source: Airport, _target: Airport) -> float:
    """γ = 1.0 until a calibrated similarity table exists (article section 4.2)."""
    return 1.0


@dataclass(frozen=True)
class Anchor:
    icao: str
    cidade: str
    distancia_km: float
    gamma: float
    freq_cancel: float
    freq_rain: float
    n_flights: int


def _latest_cells_by_dest(df: pd.DataFrame, month: int, min_flights: int) -> pd.DataFrame:
    cells = df[(df["month"] == month) & (df["n_flights"] >= min_flights)]
    if cells.empty:
        return cells
    cells = cells.sort_values(["dest_icao", "year"], ascending=[True, False])
    return cells.drop_duplicates("dest_icao")


def neighborhood(
    dest_icao: str,
    month: int,
    *,
    table: ExposureTable,
    airport_table: AirportTable,
    k: int = 3,
    min_flights: int = 1,
    gamma_provider: GammaProvider | None = None,
) -> list[Anchor]:
    """Return the K nearest anchor destinations (by risk distance) for a gap node."""
    target = airport_table.get(dest_icao)
    if target is None:
        return []
    gamma_of = gamma_provider or default_gamma

    df = table.dataframe
    required = {"month", "year", "dest_icao", "n_flights", "freq_cancellation", "freq_rain_10mm"}
    if not required.issubset(df.columns):
        return []
    cells = _latest_cells_by_dest(df, month, min_flights)

    anchors: list[Anchor] = []
    for _, row in cells.iterrows():
        code = str(row["dest_icao"]).upper()
        if code == target.icao:
            continue
        source = airport_table.get(code)
        if source is None:
            continue
        try:
            distance = distance_between(source, target)
        except (ValueError, TypeError):
            continue
        anchors.append(
            Anchor(
                icao=code,
                cidade=source.cidade,
                distancia_km=round(distance, 1),
                gamma=float(gamma_of(source, target)),
                freq_cancel=0.0 if pd.isna(row["freq_cancellation"]) else float(row["freq_cancellation"]),
                freq_rain=0.0 if pd.isna(row["freq_rain_10mm"]) else float(row["freq_rain_10mm"]),
                n_flights=int(row["n_flights"]),
            )
        )
    anchors.sort(key=lambda a: a.distancia_km)
    return anchors[:k]
