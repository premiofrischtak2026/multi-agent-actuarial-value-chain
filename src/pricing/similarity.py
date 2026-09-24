"""Multidimensional airport similarity (article section 4.2).

Implements the "risk distance" building blocks beyond geography:
  * cosine similarity between risk-profile vectors;
  * Mahalanobis distance for correlated variables;
  * γ factor combining climate, delays/cancellations and infrastructure.

Weights/scales are calibration inputs (article: "calibrados na base atuarial").
When no profile table is available, γ defaults to 1.0.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

from config import AIRPORT_PROFILE_CSV
from pricing.geo import Airport

FEATURES = ("clima", "atraso", "infra")


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("Vetores de perfil incompatíveis")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def mahalanobis_distance(x: Sequence[float], y: Sequence[float], covariance_inv: Sequence[Sequence[float]]) -> float:
    n = len(x)
    if len(y) != n or len(covariance_inv) != n:
        raise ValueError("Dimensões incompatíveis para Mahalanobis")
    diff = [xi - yi for xi, yi in zip(x, y, strict=True)]
    quad = sum(diff[i] * covariance_inv[i][j] * diff[j] for i in range(n) for j in range(n))
    return math.sqrt(max(0.0, quad))


@dataclass(frozen=True)
class AirportProfile:
    icao: str
    clima: float
    atraso: float
    infra: float

    @property
    def vector(self) -> tuple[float, float, float]:
        return (self.clima, self.atraso, self.infra)


class ProfileTable:
    """Optional per-airport risk profile (data/airport_profile.csv)."""

    def __init__(self, profiles: dict[str, AirportProfile] | None = None):
        self._by_icao = profiles or {}

    @classmethod
    def load(cls, path: Path | None = None) -> "ProfileTable":
        path = path or AIRPORT_PROFILE_CSV
        if not Path(path).exists():
            return cls()
        profiles: dict[str, AirportProfile] = {}
        with Path(path).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                icao = (row.get("icao") or "").strip().upper()
                if not icao:
                    continue
                profiles[icao] = AirportProfile(
                    icao=icao,
                    clima=float(row.get("clima", 0) or 0),
                    atraso=float(row.get("atraso", 0) or 0),
                    infra=float(row.get("infra", 0) or 0),
                )
        return cls(profiles)

    def get(self, icao: str) -> AirportProfile | None:
        return self._by_icao.get((icao or "").strip().upper())

    def __len__(self) -> int:
        return len(self._by_icao)


def gamma_from_features(
    target: AirportProfile,
    source: AirportProfile,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> float:
    """γ = 1 + Σ wᵢ · |Δfeatureᵢ| (features assumed on comparable scales)."""
    if len(weights) != len(FEATURES):
        raise ValueError("Pesos de γ devem ter 3 componentes")
    delta = sum(w * abs(a - b) for w, a, b in zip(weights, target.vector, source.vector, strict=True))
    return 1.0 + delta


def make_gamma_provider(
    profiles: ProfileTable | None = None,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> Callable[[Airport, Airport], float]:
    """Return a γ provider. Falls back to γ=1.0 when profiles are unavailable."""
    table = profiles or ProfileTable.load()

    def provider(source: Airport, target: Airport) -> float:
        source_profile = table.get(source.icao)
        target_profile = table.get(target.icao)
        if source_profile is None or target_profile is None:
            return 1.0
        return gamma_from_features(target_profile, source_profile, weights)

    return provider


@lru_cache(maxsize=1)
def default_gamma_provider() -> Callable[[Airport, Airport], float]:
    return make_gamma_provider()
