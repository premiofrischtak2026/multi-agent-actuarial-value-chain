"""Claim settlement and PPNG pro rata die (article section 05)."""

from __future__ import annotations

from datetime import date

from schemas import ClaimResult, PolicyDocument


def ppng_pro_rata_die(premium_brl: float, start: date, end: date, on_date: date) -> float:
    """Unearned premium: full at the start, zero at the end of the coverage."""
    total_days = (end - start).days
    if total_days <= 0:
        return 0.0
    remaining = (end - on_date).days
    fraction = min(1.0, max(0.0, remaining / total_days))
    return round(premium_brl * fraction, 2)


def settle(claim: ClaimResult, policy: PolicyDocument, *, on_date: date | None = None) -> dict:
    """Liquidate an open claim: PSL to zero, policy closed, insured notified."""
    on_date = on_date or date.today()
    return {
        "sinistro_id": claim.sinistro_id,
        "policy_id": policy.policy_id,
        "psl_brl": 0.0,
        "indenizacao_brl": claim.total_paid_brl,
        "status": "liquidado",
        "ppng_brl": ppng_pro_rata_die(policy.premium_brl, policy.effective_start, policy.effective_end, on_date),
        "comunicacao": f"Sinistro {claim.sinistro_id} liquidado no valor de R$ {claim.total_paid_brl:.2f}.",
    }
