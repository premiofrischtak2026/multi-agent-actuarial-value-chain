"""Real index monitoring (article section 05).

Observes precipitation at the contracted point and the flight status, and
builds the claim/trigger from the observation. The backtest keeps using the
deterministic hash outcome in monitoring/claims.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from config import DEFAULT_ASSUMPTIONS
from monitoring.claims import rain_trigger
from schemas import ClaimResult, PolicyDocument


@dataclass(frozen=True)
class Observation:
    precip_mm: float | None = None
    flight_cancelled: bool = False


class ObservationProvider(Protocol):
    def observe(self, policy: PolicyDocument) -> Observation: ...


class StaticObservationProvider:
    """Provider backed by a fixed observation (tests / replay)."""

    def __init__(self, observation: Observation):
        self.observation = observation

    def observe(self, policy: PolicyDocument) -> Observation:  # noqa: ARG002
        return self.observation


def evaluate_index(policy: PolicyDocument, observation: Observation) -> ClaimResult:
    threshold = policy.gatilho_mm or DEFAULT_ASSUMPTIONS.rain_threshold_mm
    rain = observation.precip_mm is not None and rain_trigger(observation.precip_mm, threshold)
    cancel = bool(observation.flight_cancelled)

    if cancel and rain:
        trigger = "both"
    elif cancel:
        trigger = "cancellation"
    elif rain:
        trigger = "rain"
    else:
        trigger = "none"

    reasons: list[str] = []
    if cancel:
        reasons.append("Cancelamento de voo")
    if rain:
        reasons.append(f"Chuva {observation.precip_mm:.1f} mm > {threshold:.1f} mm")

    if trigger == "none":
        return ClaimResult(
            triggered=False,
            trigger="none",
            precip_mm=observation.precip_mm,
            status="closed",
            reasons=["No trigger — policy closed without payout"],
        )

    indemnity = policy.capital_insured_brl
    sinistro_id = f"SIN-{policy.policy_id}"
    paid_cancel = indemnity if cancel else 0.0
    paid_rain = indemnity if (rain and not cancel) else 0.0
    return ClaimResult(
        triggered=True,
        trigger=trigger,
        sinistro_id=sinistro_id,
        precip_mm=observation.precip_mm,
        cancel_paid_brl=paid_cancel,
        rain_paid_brl=paid_rain,
        total_paid_brl=indemnity,
        status="open",
        psl_brl=indemnity,
        quadro_376={"aviso": True, "valor_brl": indemnity, "momento": "gatilho"},
        quadro_377={"psl_brl": indemnity, "momento": "foto_estoque"},
        reasons=reasons,
    )
