"""Inverse-distance weighting (IDW) — article section 4.4.

    w_i = (d_i ** -p) · γ_i  /  Σ_j (d_j ** -p) · γ_j
"""

from __future__ import annotations


def idw_weights(distances_km: list[float], gammas: list[float], power: float = 2.0) -> list[float]:
    if power <= 0:
        raise ValueError("A potência p do IDW deve ser positiva")
    if not distances_km or len(distances_km) != len(gammas):
        raise ValueError("Distâncias e fatores γ devem ter o mesmo tamanho e não ser vazios")
    terms: list[float] = []
    for distance, gamma in zip(distances_km, gammas, strict=True):
        if distance <= 0:
            raise ValueError("A distância ortodrômica deve ser positiva")
        if gamma < 0:
            raise ValueError("O fator γ não pode ser negativo")
        terms.append((distance ** (-power)) * gamma)
    total = sum(terms)
    if total == 0:
        raise ValueError("Os pesos IDW somam zero")
    return [term / total for term in terms]


def weighted_mean(values: list[float], weights: list[float]) -> float:
    if not values or len(values) != len(weights):
        raise ValueError("Valores e pesos devem ter o mesmo tamanho")
    return sum(value * weight for value, weight in zip(values, weights, strict=True))
