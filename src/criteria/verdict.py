"""Consolidate the acceptance checks into the final verdict (article Table 11)."""

from __future__ import annotations

from config import RULES_VERSION
from criteria.base import AcceptanceContext
from criteria.checks import CHECKS
from schemas import AcceptanceCode, AcceptanceResult, BookingInput, CriterionResult, CriterionStatus


def verdict_from_checks(checks: list[CriterionResult]) -> tuple[AcceptanceCode, str]:
    if any(c.resultado == CriterionStatus.DENY for c in checks):
        denied = ", ".join(c.codigo for c in checks if c.resultado == CriterionStatus.DENY)
        return AcceptanceCode.R, f"Recusa objetiva: {denied}"
    if any(c.resultado == CriterionStatus.INFO for c in checks):
        pending = ", ".join(c.codigo for c in checks if c.resultado == CriterionStatus.INFO)
        return AcceptanceCode.SI, f"Sem informação suficiente: {pending}"
    if any(c.resultado == CriterionStatus.REVIEW for c in checks):
        review = ", ".join(c.codigo for c in checks if c.resultado == CriterionStatus.REVIEW)
        return AcceptanceCode.RH, f"Revisão humana: {review}"
    if any(c.resultado == CriterionStatus.CONDITIONAL for c in checks):
        conditions = ", ".join(c.codigo for c in checks if c.resultado == CriterionStatus.CONDITIONAL)
        return AcceptanceCode.AC, f"Aceitar com condições (ajuste na emissão): {conditions}"
    return AcceptanceCode.A, "Todos os critérios pass; sem ressalva material."


def evaluate_acceptance(booking: BookingInput, context: AcceptanceContext) -> AcceptanceResult:
    checks = [check(booking, context) for check in CHECKS]
    code, justification = verdict_from_checks(checks)
    condicoes = [c.evidencia for c in checks if c.resultado == CriterionStatus.CONDITIONAL]
    return AcceptanceResult(
        politica=context.politica,
        checks=checks,
        veredito=code,
        justificativa=justification,
        versao_regras=context.versao_regras or RULES_VERSION,
        condicoes=condicoes,
    )
