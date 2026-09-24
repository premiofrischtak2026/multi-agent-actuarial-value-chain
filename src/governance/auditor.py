"""Agente Auditor (article section 4.8): automatic blocks and opinion."""

from __future__ import annotations

from dataclasses import dataclass, field

from config import DEFAULT_ASSUMPTIONS, ActuarialAssumptions
from schemas import BookingInput, PricingResult


@dataclass
class AuditOpinion:
    bloqueado: bool
    motivos: list[str] = field(default_factory=list)
    parecer: str = ""


def review(
    pricing: PricingResult,
    booking: BookingInput | None = None,
    assumptions: ActuarialAssumptions | None = None,
) -> AuditOpinion:
    a = assumptions or DEFAULT_ASSUMPTIONS
    motivos: list[str] = []

    if not (a.theta_min <= pricing.theta <= a.theta_max):
        motivos.append(f"θ fora da faixa aprovada [{a.theta_min:.0%}, {a.theta_max:.0%}]")
    if booking is not None and booking.aviso_governamental:
        motivos.append("Viagem contra aviso governamental")
    if pricing.commercial_rate <= 0 or pricing.premium_brl <= 0:
        motivos.append("Prêmio comercial inválido")

    bloqueado = bool(motivos)
    if bloqueado:
        parecer = "PARECER: BLOQUEADO. " + "; ".join(motivos) + "."
    else:
        parecer = (
            "PARECER: CONFORME COM RESSALVAS. A decomposição matemática é reproduzível e os "
            "carregamentos estão dentro das alçadas aprovadas. A emissão automática só é "
            "permitida com fontes, pesos, credibilidade e carregamentos vigentes."
        )
    return AuditOpinion(bloqueado=bloqueado, motivos=motivos, parecer=parecer)
