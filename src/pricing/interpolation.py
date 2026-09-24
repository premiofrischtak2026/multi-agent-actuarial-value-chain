"""IDW interpolation over the airport graph (article section 4.7)."""

from __future__ import annotations

from dataclasses import dataclass

from pricing.idw import idw_weights, weighted_mean
from pricing.network import Anchor


@dataclass(frozen=True)
class InterpolationResult:
    freq_cancel: float
    freq_rain: float
    weights: list[float]
    anchors: list[Anchor]

    @property
    def neighbours(self) -> list[tuple[Anchor, float]]:
        return list(zip(self.anchors, self.weights, strict=True))


def interpolate_values(values: list[float], distances_km: list[float], gammas: list[float], power: float = 2.0) -> tuple[float, list[float]]:
    weights = idw_weights(distances_km, gammas, power)
    return weighted_mean(values, weights), weights


def interpolate_frequency(anchors: list[Anchor], power: float = 2.0) -> InterpolationResult:
    if not anchors:
        raise ValueError("Sem âncoras para interpolar")
    distances = [a.distancia_km for a in anchors]
    gammas = [a.gamma for a in anchors]
    weights = idw_weights(distances, gammas, power)
    freq_cancel = weighted_mean([a.freq_cancel for a in anchors], weights)
    freq_rain = weighted_mean([a.freq_rain for a in anchors], weights)
    return InterpolationResult(
        freq_cancel=freq_cancel, freq_rain=freq_rain, weights=weights, anchors=anchors
    )
