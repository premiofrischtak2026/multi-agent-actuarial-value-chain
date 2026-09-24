"""Trigger monitoring and claims (indemnity = flight + accommodation)."""

from __future__ import annotations

import hashlib

from booking_values import trip_loss_brl
from config import DEFAULT_ASSUMPTIONS, ActuarialAssumptions
from schemas import BacktestOutcome, BookingInput, ClaimResult, PolicyDocument


def deterministic_outcome(booking_id: str, freq_cancel: float, freq_rain: float) -> BacktestOutcome:
    """Build a deterministic outcome from booking_id and historical frequencies."""
    digest = hashlib.sha256(booking_id.encode()).hexdigest()
    h1 = int(digest[:8], 16) / 0xFFFFFFFF
    h2 = int(digest[8:16], 16) / 0xFFFFFFFF
    return BacktestOutcome(
        cancelled=h1 < freq_cancel,
        rain_trigger_10mm=h2 < freq_rain,
    )


def rain_trigger(precip_mm: float, threshold_mm: float = 10.0) -> bool:
    """Parametric rain trigger: strictly greater than the threshold.

    The contract states that exactly 10.0 mm does NOT trigger (article Table 15).
    """
    return precip_mm > threshold_mm


class ClaimsEngine:
    def __init__(self, assumptions: ActuarialAssumptions | None = None):
        self.assumptions = assumptions or DEFAULT_ASSUMPTIONS

    def evaluate(
        self,
        policy: PolicyDocument,
        booking: BookingInput,
        freq_cancel: float,
        freq_rain: float,
    ) -> ClaimResult:
        outcome = getattr(booking, "outcome", None)
        if outcome is None:
            outcome = deterministic_outcome(booking.booking_id, freq_cancel, freq_rain)

        trip_loss = trip_loss_brl(booking)
        reasons: list[str] = []
        cancel_paid = 0.0
        rain_paid = 0.0

        if outcome.cancelled:
            cancel_paid = trip_loss
            reasons.append("Flight cancelled — indemnity covers flight + accommodation")
        if outcome.rain_trigger_10mm:
            if outcome.cancelled:
                reasons.append(
                    f"Rain > {self.assumptions.rain_threshold_mm:.0f}mm at destination "
                    "(already covered by cancellation)"
                )
            else:
                rain_paid = trip_loss
                reasons.append(
                    f"Rain > {self.assumptions.rain_threshold_mm:.0f}mm at destination "
                    "— indemnity covers flight + accommodation"
                )

        total = cancel_paid + rain_paid
        return ClaimResult(
            triggered=total > 0,
            cancel_paid_brl=cancel_paid,
            rain_paid_brl=rain_paid,
            total_paid_brl=total,
            reasons=reasons if reasons else ["No trigger — policy closed without payout"],
        )
