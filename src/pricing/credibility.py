"""Bühlmann-Straub credibility (article section 4.5).

    Z = n / (n + K),  K = σ²_intra / σ²_inter

Z = 1 once the exposure reaches the sufficiency threshold (500 dias-viagem).
The composed premium blends local experience and the graph interpolation.
"""

from __future__ import annotations

FULL_CREDIBILITY_AT = 500.0


def credibility(exposure: float, k: float, full_at: float = FULL_CREDIBILITY_AT) -> float:
    if k < 0:
        raise ValueError("O parâmetro K de credibilidade não pode ser negativo")
    if exposure >= full_at:
        return 1.0
    if exposure <= 0:
        return 0.0
    return exposure / (exposure + k)


def k_from_variances(var_within: float, var_between: float) -> float:
    """K = σ²_intra / σ²_inter."""
    if var_within < 0 or var_between < 0:
        raise ValueError("As variâncias não podem ser negativas")
    if var_between == 0:
        raise ValueError("A variância entre riscos não pode ser zero")
    return var_within / var_between


def compose(z: float, local_premium: float, interpolated_premium: float) -> float:
    if not 0.0 <= z <= 1.0:
        raise ValueError("Z precisa estar entre 0 e 1")
    return z * local_premium + (1.0 - z) * interpolated_premium
