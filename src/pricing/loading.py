"""Commercial premium loadings (article section 4.6).

    PC = PP × (1 + θ) / [1 − (comissão + lucro + DA)] × (1 + M_incerteza) × M

θ is the safety margin (3%–12%), proportional to the interpolation spread.
M is the dynamic demand/seasonality multiplier; M_incerteza is the explicit
uncertainty loading.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_ASSUMPTIONS, ActuarialAssumptions


def theta_from_spread(
    spread: float,
    *,
    theta_min: float = 0.03,
    theta_max: float = 0.12,
    spread_ref: float = 0.05,
) -> float:
    """Map an interpolation spread to θ ∈ [theta_min, theta_max] (linear, clipped)."""
    if spread_ref <= 0:
        raise ValueError("spread_ref deve ser positivo")
    scaled = theta_min + (theta_max - theta_min) * (spread / spread_ref)
    return min(theta_max, max(theta_min, scaled))


@dataclass(frozen=True)
class PricingLoading:
    theta: float
    uncertainty: float
    multiplier: float
    premium_brl: float
    capped: bool


def compute_loading(
    premium_pure: float,
    capital_insured: float,
    assumptions: ActuarialAssumptions | None = None,
    *,
    theta: float | None = None,
    multiplier: float = 1.0,
    uncertainty: float = 0.0,
) -> PricingLoading:
    a = assumptions or DEFAULT_ASSUMPTIONS
    theta = a.safety_margin if theta is None else theta
    if not 0.0 <= theta <= 1.0 or multiplier <= 0 or uncertainty < 0:
        raise ValueError("Parâmetros de carregamento inválidos")
    loading = 1.0 - (a.commission + a.profit + a.administrative_expense)
    if loading <= 0:
        raise ValueError("A soma dos carregamentos é maior ou igual a 1")
    premium = premium_pure * (1.0 + theta) / loading * (1.0 + uncertainty) * multiplier
    capped = False
    if capital_insured > 0:
        cap = a.max_premium_to_cs_ratio * capital_insured
        if premium > cap:
            premium = cap
            capped = True
    return PricingLoading(
        theta=theta,
        uncertainty=uncertainty,
        multiplier=multiplier,
        premium_brl=round(premium, 2),
        capped=capped,
    )
